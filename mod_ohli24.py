#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 3:44 PM
# @Author  : yommi
# @Site    :
# @File    : logic_ohli24
# @Software: PyCharm
from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import threading
import traceback
import urllib
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple, Union, Callable, TYPE_CHECKING
from urllib import parse

# third-party
import requests

# third-party
from flask import request, render_template, jsonify
from lxml import html
from sqlalchemy import or_, desc

# third-party
import requests

# third party package
import aiohttp

from bs4 import BeautifulSoup
import jsbeautifier

# sjva 공용
from framework import db, scheduler, path_data, socketio
from framework.util import Util

# from framework.common.util import headers
from framework import F
from plugin import PluginModuleBase
from .lib.ffmpeg_queue_v1 import FfmpegQueueEntity, FfmpegQueue
from support.expand.ffmpeg import SupportFfmpeg

from .lib.util import Util

# from support_site import SupportKakaotv

from .setup import *

logger = P.logger

print("*=" * 50)
name = "ohli24"


class LogicOhli24(PluginModuleBase):
    current_headers: Optional[Dict[str, str]] = None
    current_data: Optional[Dict[str, Any]] = None
    referer: Optional[str] = None
    origin_url: Optional[str] = None
    episode_url: Optional[str] = None
    cookies: Optional[requests.cookies.RequestsCookieJar] = None
    
    # proxy = "http://192.168.0.2:3138"
    # proxies = {
    #     "http": proxy,
    #     "https": proxy,
    # }

    @classmethod
    def get_proxy(cls) -> str:
        return P.ModelSetting.get("ohli24_proxy_url")

    @classmethod
    def get_proxies(cls) -> Optional[Dict[str, str]]:
        proxy = cls.get_proxy()
        if proxy:
            return {"http": proxy, "https": proxy}
        return None

    session = requests.Session()

    headers = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.5249.114 Whale/3.17.145.12 Safari/537.36",
        "authority": "ndoodle.xyz",
        "accept": "*/*",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://ndoodle.xyz/video/e6e31529675d0ef99d777d729c423382",
    }
    useragent = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
    }

    download_queue = None
    download_thread = None
    current_download_count = 0

    def __init__(self, P: Any) -> None:
        super(LogicOhli24, self).__init__(P, "setting", scheduler_desc="ohli24 자동 다운로드")
        self.name: str = name

        self.db_default = {
            "ohli24_db_version": "1",
            "ohli24_proxy_url": "",
            "ohli24_discord_webhook_url": "",
            "ohli24_url": "https://ani.ohli24.com",
            "ohli24_download_path": os.path.join(path_data, P.package_name, "ohli24"),
            "ohli24_auto_make_folder": "True",
            f"{self.name}_recent_code": "",
            "ohli24_auto_make_season_folder": "True",
            "ohli24_finished_insert": "[완결]",
            "ohli24_max_ffmpeg_process_count": "1",
            f"{self.name}_download_method": "cdndania",  # cdndania (default), ffmpeg, ytdlp, aria2c
            "ohli24_download_threads": "2",  # 기본값 2 (안정성 권장)
            "ohli24_order_desc": "False",
            "ohli24_auto_start": "False",
            "ohli24_interval": "* 5 * * *",
            "ohli24_auto_mode_all": "False",
            "ohli24_auto_code_list": "",
            "ohli24_current_code": "",
            "ohli24_uncompleted_auto_enqueue": "False",
            "ohli24_image_url_prefix_series": "https://www.jetcloud.cc/series/",
            "ohli24_image_url_prefix_episode": "https://www.jetcloud-list.cc/thumbnail/",
            "ohli24_discord_notify": "True",
        }
        self.queue = None
        # default_route_socketio(P, self)
        self.web_list_model = ModelOhli24Item
        default_route_socketio_module(self, attach="/queue")

    def cleanup_stale_temps(self) -> None:
        """서버 시작 시 잔여 tmp 폴더 정리"""
        try:
            download_path = P.ModelSetting.get("ohli24_download_path")
            if not download_path or not os.path.exists(download_path):
                return
            
            logger.info(f"Checking for stale temp directories in: {download_path}")
            
            # 다운로드 경로 순회 (1 depth만 확인해도 충분할 듯 하나, 시즌 폴더 고려하여 recursively)
            for root, dirs, files in os.walk(download_path):
                for dir_name in dirs:
                    if dir_name.startswith("tmp") and len(dir_name) > 3:
                        full_path = os.path.join(root, dir_name)
                        try:
                            import shutil
                            logger.info(f"Removing stale temp directory: {full_path}")
                            shutil.rmtree(full_path)
                        except Exception as e:
                            logger.error(f"Failed to remove stale temp dir {full_path}: {e}")
                            
        except Exception as e:
            logger.error(f"Error during stale temp cleanup: {e}")

    @staticmethod
    def db_init() -> None:
        pass
        # try:
        #     for key, value in P.Logic.db_default.items():
        #         if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
        #             db.session.add(ModelSetting(key, value))
        #     db.session.commit()
        # except Exception as e:
        #     logger.error('Exception:%s', e)
        #     logger.error(traceback.format_exc())

    def process_menu(self, sub: str, req: Any) -> str:
        arg = P.ModelSetting.to_dict()
        arg["sub"] = self.name
        if sub in ["setting", "queue", "list", "category", "request", "search"]:
            if sub == "request" and req.args.get("content_code") is not None:
                arg["ohli24_current_code"] = req.args.get("content_code")
            elif sub == "setting":
                job_id = "%s_%s" % (self.P.package_name, self.name)
                arg["scheduler"] = str(scheduler.is_include(job_id))
                arg["is_running"] = str(scheduler.is_running(job_id))
            return render_template(
                "{package_name}_{module_name}_{sub}.html".format(
                    package_name=P.package_name, module_name=self.name, sub=sub
                ),
                arg=arg,
            )
        return render_template("sample.html", title="%s - %s" % (P.package_name, sub))

    # @staticmethod
    def process_ajax(self, sub: str, req: Any) -> Any:
        try:
            data = []
            cate = request.form.get("type", None)
            page = request.form.get("page", None)

            if sub == "analysis":
                code = request.form["code"]
                # cate = request.form["type"]
                wr_id = request.form.get("wr_id", None)
                bo_table = request.form.get("bo_table", None)
                P.ModelSetting.set("ohli24_current_code", code)
                data = self.get_series_info(code, wr_id, bo_table)
                P.ModelSetting.set(f"{self.name}_recent_code", code)
                self.current_data = data
                return jsonify({"ret": "success", "data": data, "code": code})
            elif sub == "anime_list":

                data = self.get_anime_info(cate, page)
                return jsonify({"ret": "success", "cate": cate, "page": page, "data": data})
            elif sub == "complete_list":

                logger.debug("cate:: %s", cate)
                page = request.form["page"]

                data = self.get_anime_info(cate, page)
                return jsonify({"ret": "success", "cate": cate, "page": page, "data": data})
            elif sub == "search":

                query = request.form["query"]
                page = request.form["page"]

                data = self.get_search_result(query, page, cate)
                return jsonify(
                    {
                        "ret": "success",
                        "cate": cate,
                        "page": page,
                        "query": query,
                        "data": data,
                    }
                )
            elif sub == "add_queue":
                ret = {}
                info = json.loads(request.form["data"])
                logger.info(f"info:: {info}")
                ret["ret"] = self.add(info)
                return jsonify(ret)

                # todo: new version
                # info = json.loads(request.form["data"])
                # logger.info(info)
                # logger.info(self.current_data)
                # # 1. db 조회
                # db_item = ModelOhli24Program.get(info['_id'])
                # logger.debug(db_item)
                #
                # if db_item is not None:
                #     print(f"db_item is not None")
                #     pass
                # else:
                #     if db_item == None:
                #         db_item = ModelOhli24Program(info['_id'], self.get_episode(info['_id']))
                #         db_item.save()
            elif sub == "entity_list":
                return jsonify(self.queue.get_entity_list())
            elif sub == "queue_list":
                print(sub)
                return {"test"}
            elif sub == "queue_command":
                ret = self.queue.command(req.form["command"], int(req.form["entity_id"]))
                return jsonify(ret)
            elif sub == "add_queue_checked_list":
                data = json.loads(request.form["data"])

                def func():
                    count = 0
                    for tmp in data:
                        add_ret = self.add(tmp)
                        if add_ret.startswith("enqueue"):
                            self.socketio_callback("list_refresh", "")
                            count += 1
                    notify = {
                        "type": "success",
                        "msg": "%s 개의 에피소드를 큐에 추가 하였습니다." % count,
                    }
                    socketio.emit("notify", notify, namespace="/framework", broadcast=True)

                thread = threading.Thread(target=func, args=())
                thread.daemon = True
                thread.start()
                return jsonify("")
            elif sub == "web_list3":
                # print("web_list3")
                # print(request)
                # P.logger.debug(req)
                # P.logger.debug("web_list3")
                ret = ModelOhli24Item.web_list(req)
                # print(ret)
                return jsonify(ret)

            elif sub == "web_list2":

                logger.debug("web_list2")
                return jsonify(ModelOhli24Item.web_list(request))

            elif sub == "db_remove":
                db_id = request.form.get("id")
                if not db_id:
                    return jsonify({"ret": "error", "log": "No ID provided"})
                return jsonify(ModelOhli24Item.delete_by_id(db_id))
            elif sub == "add_whitelist":
                try:
                    # params = request.get_data()
                    # logger.debug(f"params: {params}")
                    # data_code = request.args.get("data_code")
                    params = request.get_json()
                    logger.debug(f"params:: {params}")
                    if params is not None:
                        code = params["data_code"]
                        logger.debug(f"params: {code}")
                        ret = LogicOhli24.add_whitelist(code)
                    else:
                        ret = LogicOhli24.add_whitelist()
                    return jsonify(ret)
                except Exception as e:
                    logger.error(f"Exception: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"error": str(e)}), 500
            
            elif sub == "stream_video":
                # 비디오 스트리밍 (MP4 파일 직접 서빙)
                try:
                    from flask import send_file, Response
                    import mimetypes
                    
                    file_path = request.args.get("path", "")
                    logger.info(f"Stream video request: {file_path}")
                    
                    if not file_path or not os.path.exists(file_path):
                        return jsonify({"error": "File not found"}), 404
                    
                    # 보안 체크: 다운로드 폴더 내부인지 확인
                    download_path = P.ModelSetting.get("ohli24_download_path")
                    if not file_path.startswith(download_path):
                        return jsonify({"error": "Access denied"}), 403
                    
                    # Range 요청 지원 (비디오 시킹)
                    file_size = os.path.getsize(file_path)
                    range_header = request.headers.get('Range', None)
                    
                    if range_header:
                        byte_start, byte_end = 0, None
                        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
                        if match:
                            byte_start = int(match.group(1))
                            byte_end = int(match.group(2)) if match.group(2) else file_size - 1
                        
                        if byte_end is None or byte_end >= file_size:
                            byte_end = file_size - 1
                        
                        length = byte_end - byte_start + 1
                        
                        def generate():
                            with open(file_path, 'rb') as f:
                                f.seek(byte_start)
                                remaining = length
                                while remaining > 0:
                                    chunk_size = min(8192, remaining)
                                    data = f.read(chunk_size)
                                    if not data:
                                        break
                                    remaining -= len(data)
                                    yield data
                        
                        resp = Response(
                            generate(),
                            status=206,
                            mimetype=mimetypes.guess_type(file_path)[0] or 'video/mp4',
                            direct_passthrough=True
                        )
                        resp.headers.add('Content-Range', f'bytes {byte_start}-{byte_end}/{file_size}')
                        resp.headers.add('Accept-Ranges', 'bytes')
                        resp.headers.add('Content-Length', length)
                        return resp
                    else:
                        return send_file(file_path, mimetype=mimetypes.guess_type(file_path)[0] or 'video/mp4')
                        
                except Exception as e:
                    logger.error(f"Stream video error: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"error": str(e)}), 500
            
            elif sub == "get_playlist":
                # 현재 파일과 같은 폴더에서 다음 에피소드들 찾기
                try:
                    file_path = request.args.get("path", "")
                    if not file_path or not os.path.exists(file_path):
                        return jsonify({"error": "File not found", "playlist": [], "current_index": 0}), 404
                    
                    # 보안 체크
                    download_path = P.ModelSetting.get("ohli24_download_path")
                    if not file_path.startswith(download_path):
                        return jsonify({"error": "Access denied", "playlist": [], "current_index": 0}), 403
                    
                    folder = os.path.dirname(file_path)
                    current_file = os.path.basename(file_path)
                    
                    # 파일명에서 SxxExx 패턴 추출
                    ep_match = re.search(r'\.S(\d+)E(\d+)\.', current_file, re.IGNORECASE)
                    if not ep_match:
                        # 패턴 없으면 현재 파일만 반환
                        return jsonify({
                            "playlist": [{"path": file_path, "name": current_file}],
                            "current_index": 0
                        })
                    
                    current_season = int(ep_match.group(1))
                    current_episode = int(ep_match.group(2))
                    
                    # 같은 폴더의 모든 mp4 파일 가져오기
                    all_files = []
                    for f in os.listdir(folder):
                        if f.endswith('.mp4'):
                            match = re.search(r'\.S(\d+)E(\d+)\.', f, re.IGNORECASE)
                            if match:
                                s = int(match.group(1))
                                e = int(match.group(2))
                                all_files.append({
                                    "path": os.path.join(folder, f),
                                    "name": f,
                                    "season": s,
                                    "episode": e
                                })
                    
                    # 시즌/에피소드 순으로 정렬
                    all_files.sort(key=lambda x: (x["season"], x["episode"]))
                    
                    # 현재 에피소드 이상인 것만 필터링 (현재 + 다음 에피소드들)
                    playlist = []
                    current_index = 0
                    for i, f in enumerate(all_files):
                        if f["season"] == current_season and f["episode"] >= current_episode:
                            entry = {"path": f["path"], "name": f["name"]}
                            if f["episode"] == current_episode:
                                current_index = len(playlist)
                            playlist.append(entry)
                    
                    logger.info(f"Playlist: {len(playlist)} items, current_index: {current_index}")
                    return jsonify({
                        "playlist": playlist,
                        "current_index": current_index
                    })
                    
                except Exception as e:
                    logger.error(f"Get playlist error: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"error": str(e), "playlist": [], "current_index": 0}), 500
                    
        except Exception as e:
            P.logger.error(f"Exception: {e}")
            P.logger.error(traceback.format_exc())
            return jsonify({"error": str(e)}), 500
        
        # 매칭되지 않는 sub 요청에 대한 기본 응답
        return jsonify({"error": f"Unknown sub: {sub}"}), 404

    def get_episode(self, clip_id):
        for _ in self.current_data["episode"]:
            if _["title"] == clip_id:
                return _

    def process_command(self, command, arg1, arg2, arg3, req):
        ret = {"ret": "success"}

        if command == "queue_list":
            logger.debug("queue_list")
            logger.debug(f"self.queue.get_entity_list():: {self.queue.get_entity_list()}")
            ret = [x for x in self.queue.get_entity_list()]

            return ret
        elif command == "download_program":
            _pass = arg2
            db_item = ModelOhli24Program.get(arg1)
            if _pass == "false" and db_item is not None:
                ret["ret"] = "warning"
                ret["msg"] = "이미 DB에 있는 항목 입니다."
            elif (
                _pass == "true"
                and db_item is not None
                and ModelOhli24Program.get_by_id_in_queue(db_item.id) is not None
            ):
                ret["ret"] = "warning"
                ret["msg"] = "이미 큐에 있는 항목 입니다."
            else:
                if db_item is None:
                    db_item = ModelOhli24Program(arg1, self.get_episode(arg1))
                    db_item.save()
                db_item.init_for_queue()
                self.download_queue.put(db_item)
                ret["msg"] = "다운로드를 추가 하였습니다."

        elif command == "list":
            ret = []
            for ins in SupportFfmpeg.get_list():
                ret.append(ins.get_data())

        elif command == "queue_command":
            if arg1 == "cancel":
                pass
            elif arg1 == "reset":
                logger.debug("reset")
                # if self.queue is not None:
                #     with self.queue.mutex:
                #         self.queue.queue.clear()

                if self.download_queue is not None:
                    with self.download_queue.mutex:
                        self.download_queue.queue.clear()

        return jsonify(ret)

    @staticmethod
    def add_whitelist(*args):
        ret = {}

        logger.debug(f"args: {args}")
        try:

            if len(args) == 0:
                code = str(LogicOhli24.current_data["code"])
            else:
                code = str(args[0])

            print(code)

            whitelist_program = P.ModelSetting.get("ohli24_auto_code_list")
            # whitelist_programs = [
            #     str(x.strip().replace(" ", ""))
            #     for x in whitelist_program.replace("\n", "|").split("|")
            # ]
            whitelist_programs = [str(x.strip()) for x in whitelist_program.replace("\n", "|").split("|")]

            if code not in whitelist_programs:
                whitelist_programs.append(code)
                whitelist_programs = filter(lambda x: x != "", whitelist_programs)  # remove blank code
                whitelist_program = "|".join(whitelist_programs)
                entity = (
                    db.session.query(P.ModelSetting).filter_by(key="ohli24_auto_code_list").with_for_update().first()
                )
                entity.value = whitelist_program
                db.session.commit()
                ret["ret"] = True
                ret["code"] = code
                if len(args) == 0:
                    return LogicOhli24.current_data
                else:
                    return ret
            else:
                ret["ret"] = False
                ret["log"] = "이미 추가되어 있습니다."
        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())
            ret["ret"] = False
            ret["log"] = str(e)
        return ret

    def setting_save_after(self, change_list):
        if self.queue.get_max_ffmpeg_count() != P.ModelSetting.get_int("ohli24_max_ffmpeg_process_count"):
            self.queue.set_max_ffmpeg_count(P.ModelSetting.get_int("ohli24_max_ffmpeg_process_count"))

    def scheduler_function(self):
        # Todo: 스케쥴링 함수 미구현
        logger.debug(f"ohli24 scheduler_function::=========================")

        content_code_list = P.ModelSetting.get_list("ohli24_auto_code_list", "|")
        logger.debug(f"content_code_list::: {content_code_list}")
        url_list = ["https://www.naver.com/", "https://www.daum.net/"]

        week = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        today = date.today()
        # print(today)
        # print()
        # print(today.weekday())

        url = f'{P.ModelSetting.get("ohli24_url")}/bbs/board.php?bo_table=ing&sca={week[today.weekday()]}'

        # print(url)

        if "all" in content_code_list:
            ret_data = LogicOhli24.get_auto_anime_info(self, url=url)

            logger.debug(f"today_info:: {ret_data}")

            for item in ret_data["anime_list"]:
                # wr_id = request.form.get("wr_id", None)
                # bo_table = request.form.get("bo_table", None)
                wr_id = None
                bo_table = None
                data = []
                # print(code)
                # logger.info("code::: %s", code)
                # logger.debug(item)

                # 잠시 중지
                # data = self.get_series_info(item["code"], wr_id, bo_table)
                # logger.debug(data)

        # result = asyncio.run(LogicOhli24.main(url_list))
        # logger.debug(f"result:: {result}")

        elif len(content_code_list) > 0:
            for item in content_code_list:
                url = P.ModelSetting.get("ohli24_url") + "/c/" + item
                logger.debug(f"scheduling url: {url}")
                # ret_data = LogicOhli24.get_auto_anime_info(self, url=url)
                content_info = self.get_series_info(item, "", "")

                # logger.debug(content_info)

                for episode_info in content_info["episode"]:
                    add_ret = self.add(episode_info)
                    if add_ret.startswith("enqueue"):
                        self.socketio_callback("list_refresh", "")
                # logger.debug(f"data: {data}")
                # self.current_data = data
                # db 에서 다운로드 완료 유무 체크

    @staticmethod
    async def get_data(url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                content = await response.text()
                # print(response)
                return content

    @staticmethod
    async def main(url_list: List[str]) -> List[str]:
        input_coroutines = [LogicOhli24.get_data(url_) for url_ in url_list]
        res = await asyncio.gather(*input_coroutines)
        return res

    def get_series_info(self, code: str, wr_id: Optional[str], bo_table: Optional[str]) -> Dict[str, Any]:
        code_type = "c"
        code = urllib.parse.quote(code)

        try:
            # 캐시 기능을 제거하여 분석 버튼 클릭 시 항상 최신 설정으로 다시 분석하도록 함
            # if self.current_data is not None and "code" in self.current_data and self.current_data["code"] == code:
            #     return self.current_data

            if code.startswith("http"):
                if "/c/" in code:
                    code = code.split("c/")[1]
                    code_type = "c"
                elif "/e/" in code:
                    code = code.split("e/")[1]
                    code_type = "e"

                logger.info(f"code:::: {code}")

            base_url = P.ModelSetting.get("ohli24_url").rstrip("/")  # 뒤에 슬래시 제거
            
            if code_type == "c":
                url = base_url + "/c/" + code
            elif code_type == "e":
                url = base_url + "/e/" + code
            else:
                url = base_url + "/e/" + code

            if wr_id is not None:
                if len(wr_id) > 0:
                    url = base_url + "/bbs/board.php?bo_table=" + bo_table + "&wr_id=" + wr_id

            logger.debug("url:::> %s", url)

            response_data = LogicOhli24.get_html(url, timeout=10)
            logger.debug(f"HTML length: {len(response_data)}")
            # 디버깅: HTML 일부 출력
            if len(response_data) < 1000:
                logger.warning(f"Short HTML response: {response_data[:500]}")
            else:
                # item-subject 있는지 확인
                if "item-subject" in response_data:
                    logger.info("Found item-subject in HTML")
                else:
                    logger.warning("item-subject NOT found in HTML")
                if "itemprop=\"image\"" in response_data:
                    logger.info("Found itemprop=image in HTML")
                else:
                    logger.warning("itemprop=image NOT found in HTML")
            
            tree = html.fromstring(response_data)
            
            # 제목 추출 - h1[itemprop="headline"] 또는 기타 h1
            title = ""
            title_xpaths = [
                '//h1[@itemprop="headline"]/text()',
                '//h1[@itemprop="headline"]//text()',
                '//div[@class="view-wrap"]//h1/text()',
                '//h1/text()',
            ]
            for xpath in title_xpaths:
                result = tree.xpath(xpath)
                if result:
                    title = "".join(result).strip()
                    if title and title != "OHLI24":
                        break
            
            if not title or "OHLI24" in title:
                title = urllib.parse.unquote(code)
            
            logger.info(f"title:: {title}")
            
            # 이미지 추출 - img[itemprop="image"] 또는 img.img-tag
            image = ""
            image_xpaths = [
                '//img[@itemprop="image"]/@src',
                '//img[@class="img-tag"]/@src',
                '//div[@class="view-wrap"]//img/@src',
                '//div[contains(@class, "view-img")]//img/@src',
            ]
            for xpath in image_xpaths:
                result = tree.xpath(xpath)
                if result:
                    image = result[0]
                    if image and not "logo" in image.lower():
                        break
            
            if image:
                if image.startswith(".."):
                    image = image.replace("..", P.ModelSetting.get("ohli24_url"))
                elif not image.startswith("http"):
                    image = P.ModelSetting.get("ohli24_url") + image
            
            logger.info(f"image:: {image}")
            
            # 설명 정보 추출
            des = {}
            description_dict = {
                "원제": "_otit",
                "원작": "_org",
                "감독": "_dir",
                "각본": "_scr",
                "캐릭터 디자인": "_character_design",
                "음악": "_sound",
                "제작사": "_pub",
                "장르": "_tag",
                "분류": "_classifi",
                "제작국가": "_country",
                "방영일": "_date",
                "등급": "_grade",
                "총화수": "_total_chapter",
                "상영시간": "_show_time",
                "상영일": "_release_date",
                "개봉년도": "_release_year",
                "개봉일": "_opening_date",
                "런타임": "_run_time",
                "작화": "_drawing",
            }
            
            # view-fields에서 메타데이터 추출 시도
            des_items = tree.xpath('//div[@class="list"]/p')
            if not des_items:
                des_items = tree.xpath('//div[contains(@class, "view-field")]')
            
            for item in des_items:
                try:
                    span = item.xpath(".//span//text()")
                    if span and span[0] in description_dict:
                        key = description_dict[span[0]]
                        value = item.xpath(".//span/text()")
                        des[key] = value[1] if len(value) > 1 else ""
                except Exception:
                    pass

            # 에피소드 목록 추출 - a.item-subject
            episodes = []
            episode_links = tree.xpath('//a[@class="item-subject"]')
            
            for a_elem in episode_links:
                try:
                    ep_title = "".join(a_elem.xpath(".//text()")).strip()
                    href = a_elem.get("href", "")
                    
                    if not href.startswith("http"):
                        href = P.ModelSetting.get("ohli24_url").rstrip("/") + href
                    
                    # 부모에서 날짜 찾기
                    parent = a_elem.getparent()
                    _date = ""
                    if parent is not None:
                        grandparent = parent.getparent()
                        if grandparent is not None:
                            date_result = grandparent.xpath('.//div[@class="wr-date"]/text()')
                            if not date_result:
                                date_result = grandparent.xpath('.//*[contains(@class, "date")]/text()')
                            _date = date_result[0].strip() if date_result else ""
                    
                    m = hashlib.md5(ep_title.encode("utf-8"))
                    _vi = m.hexdigest()
                    
                    episodes.append({
                        "title": ep_title,
                        "link": href,
                        "thumbnail": image,
                        "date": _date,
                        "day": _date,
                        "_id": ep_title,
                        "va": href,
                        "_vi": _vi,
                        "content_code": code,
                    })
                except Exception as ep_err:
                    logger.warning(f"Episode parse error: {ep_err}")
                    continue
            
            logger.info(f"Found {len(episodes)} episodes")
            # 디버깅: 원본 순서 확인 (첫번째 에피소드 제목)
            if episodes:
                logger.info(f"First parsed episode: {episodes[0]['title']}")

            # 줄거리 추출
            ser_description_result = tree.xpath('//div[@class="view-stocon"]/div[@class="c"]/text()')
            if not ser_description_result:
                ser_description_result = tree.xpath('//div[contains(@class, "view-story")]//text()')
            ser_description = ser_description_result if ser_description_result else []

            data = {
                "title": title,
                "image": image,
                "date": "",
                "day": "",
                "ser_description": ser_description,
                "des": des,
                "episode": episodes,
                "code": code,
            }

            # 정렬 적용: 사이트 원본은 최신화가 가장 위임 (13, 12, ... 1)
            # ohli24_order_desc가 Off(False)이면 1화부터 나오게 뒤집기
            raw_order_desc = P.ModelSetting.get("ohli24_order_desc")
            order_desc = True if str(raw_order_desc).lower() == 'true' else False
            
            logger.info(f"Sorting - Raw: {raw_order_desc}, Parsed: {order_desc}")
            
            if not order_desc:
                logger.info("Order is set to Ascending (Off), reversing list to show episode 1 first.")
                data["episode"] = list(reversed(data['episode']))
                data["list_order"] = "asc"
            else:
                logger.info("Order is set to Descending (On), keeping site order (Newest first).")
                data["list_order"] = "desc"
            
            if data["episode"]:
                logger.info(f"Final episode list range: {data['episode'][0]['title']} ~ {data['episode'][-1]['title']}")
                
                # [FILE EXISTENCE CHECK FOR UI PLAY BUTTON]
                try:
                    # 1. Calculate Save Path (Replicating Ohli24QueueEntity logic)
                    save_path = P.ModelSetting.get("ohli24_download_path")
                    content_title = data["title"]
                    # Season info might be embedded in title or handled elsewhere, but here we use the base title from analysis
                    # Note: Ohli24QueueEntity extracts season from title regex. We should try that too.
                    
                    season = 1
                    match = re.compile(r"(?P<title>.*?)\s*((?P<season>\d+)%s)?\s*((?P<epi_no>\d+)%s)" % ("기", "화")).search(content_title)
                    if match:
                        content_title_clean = match.group("title").strip()
                        if "season" in match.groupdict() and match.group("season") is not None:
                            season = int(match.group("season"))
                    else:
                        content_title_clean = content_title

                    if P.ModelSetting.get_bool("ohli24_auto_make_folder"):
                        folder_name = content_title_clean
                        if data.get("day", "").find("완결") != -1:
                             folder_name = "%s %s" % (P.ModelSetting.get("ohli24_finished_insert"), content_title_clean)
                        
                        folder_name = Util.change_text_for_use_filename(folder_name.strip())
                        save_path = os.path.join(save_path, folder_name)
                        
                        if P.ModelSetting.get_bool("ohli24_auto_make_season_folder"):
                            save_path = os.path.join(save_path, "Season %s" % int(season))
                            
                    # 2. Check for first available file
                    if os.path.exists(save_path):
                        import glob
                        # Pattern: Title.S01E01.*.mp4 (Ohli24QueueEntity format)
                        # We need to check available episodes. Let's check the first few to be safe.
                        # Note: file pattern uses content_title_clean
                        
                        for ep in data["episode"]:
                            # Parse episode number from title (e.g., "1화")
                            ep_num = 1
                            ep_match = re.search(r"(\d+)화", ep["title"])
                            if ep_match:
                                ep_num = int(ep_match.group(1))
                            
                            # Construct glob pattern
                            # Pattern from Entity: "%s.S%sE%s.%s-OHNI24.mp4"
                            season_str = "0%s" % season if season < 10 else season
                            ep_str = "0%s" % ep_num if ep_num < 10 else ep_num
                            
                            # Use glob to match any quality
                            glob_pattern = f"{Util.change_text_for_use_filename(content_title_clean)}.S{season_str}E{ep_str}.*-OHNI24.mp4"
                            search_path = os.path.join(save_path, glob_pattern)
                            files = glob.glob(search_path)
                            
                            if files:
                                # Found a file!
                                valid_file = files[0] # Pick first match
                                data["first_exist_filepath"] = valid_file
                                data["first_exist_filename"] = os.path.basename(valid_file)
                                logger.info(f"Play button enabled: Found {data['first_exist_filename']}")
                                break # Stop after finding one
                                
                except Exception as e:
                    logger.error(f"Error checking file existence: {e}")
                    # Don't fail the whole analysis, just skip play button
            
            self.current_data = data
            return data

        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    def get_anime_info(self, cate, page):
        print(cate, page)
        try:
            if cate == "ing":
                url = P.ModelSetting.get("ohli24_url") + "/bbs/board.php?bo_table=" + cate + "&page=" + page
            elif cate == "movie":
                url = P.ModelSetting.get("ohli24_url") + "/bbs/board.php?bo_table=" + cate + "&page=" + page
            else:
                url = P.ModelSetting.get("ohli24_url") + "/bbs/board.php?bo_table=" + cate + "&page=" + page
                # cate == "complete":
            logger.info("url:::> %s", url)
            data = {}
            response_data = LogicOhli24.get_html(url, timeout=10)
            tree = html.fromstring(response_data)
            tmp_items = tree.xpath('//div[@class="list-row"]')
            data["anime_count"] = len(tmp_items)
            data["anime_list"] = []

            for item in tmp_items:
                entity = {}
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["code"] = entity["link"].split("/")[-1]
                entity["title"] = item.xpath(".//div[@class='post-title']/text()")[0].strip()
                # logger.debug(item.xpath(".//div[@class='img-item']/img/@src")[0])
                # logger.debug(item.xpath(".//div[@class='img-item']/img/@data-ezsrc")[0])
                # entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@src")[
                #     0
                # ].replace("..", P.ModelSetting.get("ohli24_url"))

                if len(item.xpath(".//div[@class='img-item']/img/@src")) > 0:
                    entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@src")[0].replace(
                        "..", P.ModelSetting.get("ohli24_url")
                    )
                else:
                    entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@data-ezsrc")[0]

                data["ret"] = "success"
                data["anime_list"].append(entity)

            return data
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    def get_auto_anime_info(self, url: str = ""):
        try:

            logger.info("url:::> %s", url)
            data = {}
            response_data = LogicOhli24.get_html(url, timeout=10)
            tree = html.fromstring(response_data)
            tmp_items = tree.xpath('//div[@class="list-row"]')
            data["anime_count"] = len(tmp_items)
            data["anime_list"] = []

            for item in tmp_items:
                entity = {}
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["code"] = entity["link"].split("/")[-1]
                entity["title"] = item.xpath(".//div[@class='post-title']/text()")[0].strip()
                entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@src")[0].replace(
                    "..", P.ModelSetting.get("ohli24_url")
                )
                data["ret"] = "success"
                data["anime_list"].append(entity)

            return data
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    # @staticmethod
    def get_search_result(self, query, page, cate):
        try:
            _query = urllib.parse.quote(query)
            url = (
                P.ModelSetting.get("ohli24_url")
                + "/bbs/search.php?srows=24&gr_id=&sfl=wr_subject&stx="
                + _query
                + "&page="
                + page
            )

            logger.info("get_search_result()::url> %s", url)
            data = {}
            response_data = LogicOhli24.get_html(url, timeout=10)
            tree = html.fromstring(response_data)
            tmp_items = tree.xpath('//div[@class="list-row"]')
            data["anime_count"] = len(tmp_items)
            data["anime_list"] = []

            for item in tmp_items:
                entity = {}
                entity["link"] = item.xpath(".//a/@href")[0]
                # entity["code"] = entity["link"].split("/")[-1]
                entity["wr_id"] = entity["link"].split("=")[-1]
                # logger.debug(item.xpath(".//div[@class='post-title']/text()").join())
                entity["title"] = "".join(item.xpath(".//div[@class='post-title']/text()")).strip()
                entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@src")[0].replace(
                    "..", P.ModelSetting.get("ohli24_url")
                )

                entity["code"] = item.xpath(".//div[@class='img-item']/img/@alt")[0]

                data["ret"] = "success"
                data["anime_list"].append(entity)

            return data
        except Exception as e:
            P.logger.error(f"Exception: {str(e)}")
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    # @staticmethod
    def plugin_load(self) -> None:
        try:
            # SupportFfmpeg.initialize(ffmpeg_modelsetting.get('ffmpeg_path'), os.path.join(F.config['path_data'], 'tmp'),
            #                          self.callback_function, ffmpeg_modelsetting.get_int('max_pf_count'))

            # plugin loading download_queue 가 없으면 생성
            # if self.download_queue is None:
            #     self.download_queue = queue.Queue()

            SupportFfmpeg.initialize(
                "ffmpeg",
                os.path.join(F.config["path_data"], "tmp"),
                self.callback_function,
                P.ModelSetting.get(f"{name}_max_ffmpeg_process_count"),
            )

            logger.debug("%s plugin_load", P.package_name)
            self.queue = FfmpegQueue(
                P,
                P.ModelSetting.get_int(f"{name}_max_ffmpeg_process_count"),
                name,
                self,
            )
            self.current_data = None
            self.queue.queue_start()
            
            # 잔여 Temp 폴더 정리
            self.cleanup_stale_temps()

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    # @staticmethod
    def plugin_unload(self) -> None:
        try:
            logger.debug("%s plugin_unload", P.package_name)
            scheduler.remove_job("%s_recent" % P.package_name)
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    @staticmethod
    def reset_db() -> bool:
        db.session.query(ModelOhli24Item).delete()
        db.session.commit()
        return True

    @staticmethod
    def get_html(
        url: str,
        headers: Optional[Dict[str, str]] = None,
        referer: Optional[str] = None,
        stream: bool = False,
        timeout: int = 60,
        stealth: bool = False,
        data: Optional[Dict[str, Any]] = None,
        method: str = 'GET'
    ) -> str:
        """별도 스레드에서 curl_cffi 실행하여 gevent SSL 충돌 및 Cloudflare 우회"""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        import time
        from urllib import parse
        
        # URL 인코딩 (한글 주소 대응)
        if '://' in url:
            try:
                scheme, netloc, path, params, query, fragment = parse.urlparse(url)
                # 이미 인코딩된 경우를 대비해 unquote 후 다시 quote
                path = parse.quote(parse.unquote(path), safe='/')
                query = parse.quote(parse.unquote(query), safe='=&%')
                url = parse.urlunparse((scheme, netloc, path, params, query, fragment))
            except:
                pass

        def fetch_url_with_cffi(url, headers, timeout, data, method):
            """별도 스레드에서 curl_cffi로 실행"""
            from curl_cffi import requests
            
            # 프록시 설정
            proxies = LogicOhli24.get_proxies()
            
            with requests.Session(impersonate="chrome120") as session:
                # 헤더 설정
                if headers:
                    session.headers.update(headers)
                
                if method.upper() == 'POST':
                    response = session.post(url, data=data, timeout=timeout, proxies=proxies)
                else:
                    response = session.get(url, timeout=timeout, proxies=proxies)
                return response.text
        
        response_data = ""
        
        if headers is None:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        
        if referer:
            if '://' in referer:
                try:
                    scheme, netloc, path, params, query, fragment = parse.urlparse(referer)
                    path = parse.quote(parse.unquote(path), safe='/')
                    query = parse.quote(parse.unquote(query), safe='=&%')
                    referer = parse.urlunparse((scheme, netloc, path, params, query, fragment))
                except:
                    pass
            headers["Referer"] = referer
        elif "Referer" not in headers and "referer" not in headers:
            headers["Referer"] = "https://ani.ohli24.com"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.debug(f"get_html (curl_cffi in thread) {method} attempt {attempt + 1}: {url}")
                
                # ThreadPoolExecutor로 별도 스레드에서 실행
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(fetch_url_with_cffi, url, headers, timeout, data, method)
                    response_data = future.result(timeout=timeout + 10)
                
                if response_data and (len(response_data) > 10 or method.upper() == 'POST'):
                    logger.debug(f"get_html success, length: {len(response_data)}")
                    return response_data
                else:
                    logger.warning(f"Short response (len={len(response_data) if response_data else 0})")
                
            except FuturesTimeoutError:
                logger.warning(f"get_html attempt {attempt + 1} timed out")
            except Exception as e:
                logger.warning(f"get_html attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(3)
        
        return response_data

    #########################################################
    def add(self, episode_info: Dict[str, Any]) -> str:
        if self.is_exist(episode_info):
            return "queue_exist"
        else:
            logger.debug(f"episode_info:: {episode_info}")
            db_entity = ModelOhli24Item.get_by_ohli24_id(episode_info["_id"])

            logger.debug("db_entity:::> %s", db_entity)
            # logger.debug("db_entity.status ::: %s", db_entity.status)
            if db_entity is None:
                entity = Ohli24QueueEntity(P, self, episode_info)
                entity.proxy = LogicOhli24.get_proxy()
                logger.debug("entity:::> %s", entity.as_dict())
                ModelOhli24Item.append(entity.as_dict())
                # # logger.debug("entity:: type >> %s", type(entity))
                #
                self.queue.add_queue(entity)

                # P.logger.debug(F.config['path_data'])
                # P.logger.debug(self.headers)

                # filename = os.path.basename(entity.filepath)
                # ffmpeg = SupportFfmpeg(entity.url, entity.filename, callback_function=self.callback_function,
                #                        max_pf_count=0,
                #                        save_path=entity.savepath, timeout_minute=60, headers=self.headers)
                # ret = {'ret': 'success'}
                # ret['json'] = ffmpeg.start()
                return "enqueue_db_append"
            elif db_entity.status != "completed":
                entity = Ohli24QueueEntity(P, self, episode_info)
                entity.proxy = LogicOhli24.get_proxy()
                logger.debug("entity:::> %s", entity.as_dict())

                # P.logger.debug(F.config['path_data'])
                # P.logger.debug(self.headers)

                # filename = os.path.basename(entity.filepath)
                # ffmpeg = SupportFfmpeg(entity.url, entity.filename, callback_function=self.callback_function,
                #                        max_pf_count=0, save_path=entity.savepath, timeout_minute=60,
                #                        headers=self.headers)
                # ret = {'ret': 'success'}
                # ret['json'] = ffmpeg.start()

                self.queue.add_queue(entity)
                return "enqueue_db_exist"
            else:
                return "db_completed"

    def is_exist(self, info: Dict[str, Any]) -> bool:
        # print(self.queue)
        # print(self.queue.entity_list)
        for en in self.queue.entity_list:
            if en.info["_id"] == info["_id"]:
                return True
        return False

    def callback_function(self, **args: Any) -> None:
        logger.debug(f"callback_function invoked with args: {args}")
        if 'status' in args:
            logger.debug(f"Status: {args['status']}")
            
        refresh_type = None
        if args["type"] == "status_change":
            if args["status"] == SupportFfmpeg.Status.DOWNLOADING:
                refresh_type = "status_change"
            elif args["status"] == SupportFfmpeg.Status.COMPLETED:
                refresh_type = "status_change"
                logger.debug("mod_ohli24.py:: download completed........")
            elif args["status"] == SupportFfmpeg.Status.READY:
                data = {
                    "type": "info",
                    "msg": "다운로드중 Duration(%s)" % args["data"]["duration_str"]
                    + "<br>"
                    + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                # socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = "add"
        elif args["type"] == "last":
            entity = self.queue.get_entity_by_entity_id(args['data']['callback_id'])
            
            if args["status"] == SupportFfmpeg.Status.WRONG_URL:
                if entity: entity.download_failed("WRONG_URL")
                data = {"type": "warning", "msg": "잘못된 URL입니다"}
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "add"
            elif args["status"] == SupportFfmpeg.Status.WRONG_DIRECTORY:
                if entity: entity.download_failed("WRONG_DIRECTORY")
                data = {
                    "type": "warning",
                    "msg": "잘못된 디렉토리입니다.<br>" + args["data"]["save_fullpath"],
                }
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "add"
            elif args["status"] == SupportFfmpeg.Status.ERROR or args["status"] == SupportFfmpeg.Status.EXCEPTION:
                if entity: entity.download_failed("ERROR/EXCEPTION")
                data = {
                    "type": "warning",
                    "msg": "다운로드 시작 실패.<br>" + args["data"]["save_fullpath"],
                }
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "add"
            elif args["status"] == SupportFfmpeg.Status.USER_STOP:
                if entity: entity.download_failed("USER_STOP")
                data = {
                    "type": "warning",
                    "msg": "다운로드가 중지 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.COMPLETED:
                logger.debug("download completed........")
                data = {
                    "type": "success",
                    "msg": "다운로드가 완료 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }

                socketio.emit("notify", data, namespace="/framework", broadcast=True)

                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.TIME_OVER:
                if entity: entity.download_failed("TIME_OVER")
                data = {
                    "type": "warning",
                    "msg": "시간초과로 중단 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.PF_STOP:
                if entity: entity.download_failed("PF_STOP")
                data = {
                    "type": "warning",
                    "msg": "PF초과로 중단 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.FORCE_STOP:
                if entity: entity.download_failed("FORCE_STOP")
                data = {
                    "type": "warning",
                    "msg": "강제 중단 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.HTTP_FORBIDDEN:
                if entity: entity.download_failed("HTTP_FORBIDDEN")
                data = {
                    "type": "warning",
                    "msg": "403에러로 중단 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.ALREADY_DOWNLOADING:
                # Already downloading usually means logic error or race condition, maybe not fail DB?
                # Keeping as is for now unless requested.
                data = {
                    "type": "warning",
                    "msg": "임시파일폴더에 파일이 있습니다.<br>" + args["data"]["temp_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework", broadcast=True)
                refresh_type = "last"
        elif args["type"] == "normal":
            if args["status"] == SupportFfmpeg.Status.DOWNLOADING:
                refresh_type = "status"
                # Discord Notification
                try:
                    title = args['data'].get('title', 'Unknown Title')
                    filename = args['data'].get('filename', 'Unknown File')
                    poster_url = entity.info.get('image_link', '') if entity and entity.info else ''
                    msg = "다운로드를 시작합니다."
                    self.send_discord_notification(msg, title, filename, poster_url)
                except Exception as e:
                    logger.error(f"Failed to send discord notification: {e}")
        # P.logger.info(refresh_type)
        self.socketio_callback(refresh_type, args["data"])


    def send_discord_notification(
        self,
        title: str,
        desc: str,
        filename: str,
        image_url: str = ""
    ) -> None:
        try:
            webhook_url = P.ModelSetting.get("ohli24_discord_webhook_url")
            if not webhook_url:
                logger.debug("Discord webhook URL is empty.")
                return
            
            logger.info(f"Sending Discord notification to: {webhook_url}")
            
            # 에피소드/시즌 정보 추출 (배지용)
            import re
            season_ep_str = ""
            match = re.search(r"(?P<season>\d+)기\s*(?P<episode>\d+)화", title)
            if not match:
                 match = re.search(r"(?P<season>\d+)기", title)
            if not match:
                 match = re.search(r"(?P<episode>\d+)화", title)
                 
            if match:
                parts = []
                gd = match.groupdict()
                if "season" in gd and gd["season"]:
                    parts.append(f"S{int(gd['season']):02d}")
                if "episode" in gd and gd["episode"]:
                    parts.append(f"E{int(gd['episode']):02d}")
                if parts:
                    season_ep_str = " | ".join(parts)
            
            author_name = "Ohli24 Downloader"
            if season_ep_str:
                author_name = f"{season_ep_str} • Ohli24"

            embed = {
                "title": f"📺 {title}",
                "description": desc,
                "color": 0x5865F2,  # Discord Blurple
                "author": {
                    "name": author_name,
                    "icon_url": "https://i.imgur.com/4M34hi2.png"
                },
                "fields": [
                    {
                        "name": "📁 파일명",
                        "value": f"`{filename}`" if filename else "알 수 없음",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "FlaskFarm Ohli24",
                    "icon_url": "https://i.imgur.com/4M34hi2.png"
                },
                "timestamp": datetime.now().isoformat()
            }
            
            if image_url:
                # image는 큰 이미지 (하단 전체 너비)
                embed["image"] = {"url": image_url}
                # thumbnail은 작은 우측 상단 이미지 (선택적)
                # embed["thumbnail"] = {"url": image_url}

            message = {
                "username": "Ohli24 Downloader",
                "avatar_url": "https://i.imgur.com/4M34hi2.png",
                "embeds": [embed]
            }

            import requests
            headers = {"Content-Type": "application/json"}
            response = requests.post(webhook_url, json=message, headers=headers)
            
            if response.status_code == 204:
                logger.info("Discord notification sent successfully.")
            else:
                logger.error(f"Failed to send Discord notification. Status Code: {response.status_code}, Response: {response.text}")

        except Exception as e:
            logger.error(f"Exception in send_discord_notification: {e}")
            logger.error(traceback.format_exc())


class Ohli24QueueEntity(FfmpegQueueEntity):
    def __init__(self, P: Any, module_logic: LogicOhli24, info: Dict[str, Any]) -> None:
        super(Ohli24QueueEntity, self).__init__(P, module_logic, info)
        self._vi: Optional[Any] = None
        self.url: Optional[str] = None
        self.epi_queue: Optional[str] = None
        self.filepath: Optional[str] = None
        self.savepath: Optional[str] = None
        self.quality: Optional[str] = None
        self.filename: Optional[str] = None
        self.vtt: Optional[str] = None
        self.season: int = 1
        self.content_title: Optional[str] = None
        self.srt_url: Optional[str] = None
        self.headers: Optional[Dict[str, str]] = None
        self.cookies_file: Optional[str] = None  # yt-dlp용 CDN 세션 쿠키 파일 경로
        self.need_special_downloader: bool = False # CDN 보안 우회 다운로더 필요 여부
        self._discord_sent: bool = False # Discord 알림 발송 여부
        # Todo::: 임시 주석 처리
        self.make_episode_info()


    def refresh_status(self) -> None:
        # ffmpeg_queue_v1.py에서 실패 처리(-1)된 경우 DB 업데이트 트리거
        if getattr(self, 'ffmpeg_status', 0) == -1:
             reason = getattr(self, 'ffmpeg_status_kor', 'Unknown Error')
             self.download_failed(reason)
            
        self.module_logic.socketio_callback("status", self.as_dict())
        
        # Discord Notification Trigger (All downloaders)
        try:
            if getattr(self, 'ffmpeg_status', 0) == 5: # DOWNLOADING
                 if not getattr(self, '_discord_sent', False):
                     self._discord_sent = True
                     title = self.info.get('title', 'Unknown Title')
                     filename = getattr(self, 'filename', 'Unknown File')
                     # 썸네일 이미지 - image_link 또는 thumbnail 필드에서 가져옴
                     poster_url = self.info.get('image_link', '') or self.info.get('thumbnail', '')
                     logger.debug(f"Discord poster_url: {poster_url}")
                     self.module_logic.send_discord_notification("다운로드 시작", title, filename, poster_url)
        except Exception as e:
            logger.error(f"Failed to check/send discord notification in refresh_status: {e}")
        # 추가: /queue 네임스페이스로도 명시적으로 전송
        try:
            from framework import socketio
            namespace = f"/{self.P.package_name}/{self.module_logic.name}/queue"
            socketio.emit("status", self.as_dict(), namespace=namespace)
        except:
            pass

    def info_dict(self, tmp: Dict[str, Any]) -> Dict[str, Any]:
        # logger.debug('self.info::> %s', self.info)
        for key, value in self.info.items():
            tmp[key] = value
        tmp["vtt"] = self.vtt
        tmp["season"] = self.season
        tmp["content_title"] = self.content_title
        tmp["ohli24_info"] = self.info
        tmp["epi_queue"] = self.epi_queue
        return tmp

    def download_completed(self) -> None:
        logger.debug("download completed.......!!")
        db_entity = ModelOhli24Item.get_by_ohli24_id(self.info["_id"])
        if db_entity is not None:
            db_entity.status = "completed"
            db_entity.completed_time = datetime.now()
            db_entity.save()

    def download_failed(self, reason: str) -> None:
        logger.debug(f"download failed.......!! reason: {reason}")
        db_entity = ModelOhli24Item.get_by_ohli24_id(self.info["_id"])
        if db_entity is not None:
            db_entity.status = "failed"
            db_entity.save()

    # Get episode info from OHLI24 site
    def make_episode_info(self):
        try:
            base_url = P.ModelSetting.get("ohli24_url")
            
            # 에피소드 페이지 URL (예: https://ani.ohli24.com/e/원펀맨 3기 1화)
            url = self.info["va"]
            if "//e/" in url:
                url = url.replace("//e/", "/e/")
            
            ourls = parse.urlparse(url)
            
            headers = {
                "Referer": f"{ourls.scheme}://{ourls.netloc}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            logger.debug(f"make_episode_info()::url==> {url}")
            logger.info(f"self.info:::> {self.info}")

            # ------------------------------------------------------------------
            # [METADATA PARSING] - Extract title, season, epi info first!
            # ------------------------------------------------------------------
            # 메타데이터만 먼저 파싱 (파일명 생성은 해상도 감지 후 진행)
            match = re.compile(r"(?P<title>.*?)\s*((?P<season>\d+)%s)?\s*((?P<epi_no>\d+)%s)" % ("기", "화")).search(
                self.info["title"]
            )
            
            epi_no = 1
            self.quality = "720P"  # 기본값 (해상도 감지 시 덮어쓰기)
            
            if match:
                self.content_title = match.group("title").strip()
                if "season" in match.groupdict() and match.group("season") is not None:
                    self.season = int(match.group("season"))
                
                epi_no = int(match.group("epi_no"))
            else:
                self.content_title = self.info["title"]
                logger.debug("NOT MATCH")
            
            self.epi_queue = epi_no
            # NOTE: 파일명은 해상도 감지 후 생성 (아래 Step 2 이후)
            
            # Savepath 생성 (filepath는 파일명 생성 후 설정)
            self.savepath = P.ModelSetting.get("ohli24_download_path")
            
            if P.ModelSetting.get_bool("ohli24_auto_make_folder"):
                if self.info["day"].find("완결") != -1:
                    folder_name = "%s %s" % (
                        P.ModelSetting.get("ohli24_finished_insert"),
                        self.content_title,
                    )
                else:
                    folder_name = self.content_title
                folder_name = Util.change_text_for_use_filename(folder_name.strip())
                self.savepath = os.path.join(self.savepath, folder_name)
                if P.ModelSetting.get_bool("ohli24_auto_make_season_folder"):
                    self.savepath = os.path.join(self.savepath, "Season %s" % int(self.season))
            # NOTE: self.filepath는 파일명 생성 후 설정 (Step 2 이후)
            if not os.path.exists(self.savepath):
                os.makedirs(self.savepath)
            logger.info(f"self.savepath::> {self.savepath}")


            # ------------------------------------------------------------------
            # [VIDEO EXTRACTION]
            # ------------------------------------------------------------------
            # Step 1: 에피소드 페이지에서 cdndania.com iframe 찾기
            text = LogicOhli24.get_html(url, headers=headers, referer=f"{ourls.scheme}://{ourls.netloc}")
            
            # 디버깅: HTML에 cdndania 있는지 확인
            if "cdndania" in text:
                logger.info("cdndania found in HTML")
            else:
                logger.warning("cdndania NOT found in HTML - page may be dynamically loaded")
                # logger.debug(f"HTML snippet: {text[:1000]}")
            
            soup = BeautifulSoup(text, "lxml")
            
            # mcpalyer 클래스 내의 iframe 찾기
            player_div = soup.find("div", class_="mcpalyer")
            # logger.debug(f"player_div (mcpalyer): {player_div is not None}")
            
            if not player_div:
                player_div = soup.find("div", class_="embed-responsive")
                # logger.debug(f"player_div (embed-responsive): {player_div is not None}")
            
            iframe = None
            if player_div:
                iframe = player_div.find("iframe")
                # logger.debug(f"iframe in player_div: {iframe is not None}")
            if not iframe:
                iframe = soup.find("iframe", src=re.compile(r"cdndania\.com"))
                # logger.debug(f"iframe with cdndania src: {iframe is not None}")
            if not iframe:
                # 모든 iframe 찾기
                all_iframes = soup.find_all("iframe")
                # logger.debug(f"Total iframes found: {len(all_iframes)}")
                if all_iframes:
                    iframe = all_iframes[0]
            
            if not iframe or not iframe.get("src"):
                logger.error("No iframe found on episode page")
                return
            
            iframe_src = iframe.get("src")
            logger.info(f"Found cdndania iframe: {iframe_src}")
            self.iframe_src = iframe_src
            # CDN 보안 우회 다운로더 필요 여부 - 설정에 따름
            # self.need_special_downloader = True  # 설정값 존중 (ffmpeg/ytdlp/aria2c 테스트 가능)
            self.need_special_downloader = False
            
            # Step 2: cdndania.com 페이지에서 m3u8 URL 및 해상도 추출
            video_url, vtt_url, cookies_file, detected_resolution = self.extract_video_from_cdndania(iframe_src, url)
            
            # 해상도 설정 (감지된 값 또는 기본값 720)
            if detected_resolution:
                self.quality = f"{detected_resolution}P"
                logger.info(f"Quality set from m3u8: {self.quality}")
            
            # [FILENAME GENERATION] - 해상도 감지 후 파일명 생성
            if hasattr(self, 'epi_queue'):
                epi_no = self.epi_queue
                ret = "%s.S%sE%s.%s-OHNI24.mp4" % (
                    self.content_title,
                    "0%s" % self.season if self.season < 10 else self.season,
                    "0%s" % epi_no if epi_no < 10 else epi_no,
                    self.quality,
                )
                self.filename = Util.change_text_for_use_filename(ret)
                self.filepath = os.path.join(self.savepath, self.filename)
                logger.info(f"self.filename::> {self.filename}")
            
            if not video_url:
                logger.error("Failed to extract video URL from cdndania")
                return
            
            self.url = video_url
            self.srt_url = vtt_url
            self.cookies_file = cookies_file  # yt-dlp용 세션 쿠키 파일
            self.iframe_src = iframe_src  # CdndaniaDownloader용 원본 iframe URL
            logger.info(f"Video URL: {self.url}")
            if self.srt_url:
                logger.info(f"Subtitle URL: {self.srt_url}")
            if self.cookies_file:
                logger.info(f"Cookies file: {self.cookies_file}")
            
            # 헤더 설정 (Video Download용)
            self.headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": iframe_src,
            }

            # ------------------------------------------------------------------
            # [SUBTITLE DOWNLOAD]
            # ------------------------------------------------------------------
            if self.srt_url and "thumbnails.vtt" not in self.srt_url:
                try:
                    srt_filepath = os.path.join(self.savepath, self.filename.replace(".mp4", ".ko.srt"))
                    if not os.path.exists(srt_filepath):
                        srt_resp = requests.get(self.srt_url, headers=self.headers, timeout=30)
                        if srt_resp.status_code == 200:
                            Util.write_file(srt_resp.text, srt_filepath)
                            logger.info(f"Subtitle saved: {srt_filepath}")
                except Exception as srt_err:
                    logger.warning(f"Subtitle download failed: {srt_err}")
            
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
    
    def extract_video_from_cdndania(self, iframe_src, referer_url):
        """cdndania.com 플레이어에서 API 호출을 통해 비디오(m3u8) 및 자막(vtt) URL 추출
        
        Returns:
            tuple: (video_url, vtt_url, cookies_file, resolution) - resolution은 720, 1080 등
        """
        video_url = None
        vtt_url = None
        cookies_file = None
        resolution = None  # 해상도 (height: 720, 1080 등)
        
        try:

            from curl_cffi import requests
            import tempfile
            import json
            
            logger.debug(f"Extracting from cdndania: {iframe_src}")
            
            # iframe URL에서 비디오 ID(hash) 추출
            video_id = ""
            if "/video/" in iframe_src:
                video_id = iframe_src.split("/video/")[1].split("?")[0].split("&")[0]
            elif "/v/" in iframe_src:
                video_id = iframe_src.split("/v/")[1].split("?")[0].split("&")[0]
            
            if not video_id:
                logger.error(f"Could not find video ID in iframe URL: {iframe_src}")
                return video_url, vtt_url, cookies_file
            
            # curl_cffi 세션 생성 (Chrome 120 TLS Fingerprint)
            scraper = requests.Session(impersonate="chrome120")
            proxies = LogicOhli24.get_proxies()
            if proxies:
                scraper.proxies = {"http": proxies["http"], "https": proxies["https"]}
            
            # iframe 도메인 자동 감지 (cdndania.com -> michealcdn.com 등)
            parsed_iframe = parse.urlparse(iframe_src)
            iframe_domain = f"{parsed_iframe.scheme}://{parsed_iframe.netloc}"
            
            # [CRITICAL] iframe 페이지 먼저 방문하여 세션 쿠키 획득
            encoded_referer = parse.quote(referer_url, safe=":/?#[]@!$&'()*+,;=%")
            iframe_headers = {
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "referer": encoded_referer,
            }
            logger.debug(f"Visiting iframe page for cookies: {iframe_src}")
            scraper.get(iframe_src, headers=iframe_headers, timeout=30, proxies=proxies)
            
            # getVideo API 호출
            api_url = f"{iframe_domain}/player/index.php?data={video_id}&do=getVideo"
            headers = {
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "x-requested-with": "XMLHttpRequest",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "referer": iframe_src,
                "origin": iframe_domain
            }
            post_data = {
                "hash": video_id,
                "r": "https://ani.ohli24.com/"
            }
            
            logger.debug(f"Calling video API with session: {api_url}")
            response = scraper.post(api_url, headers=headers, data=post_data, timeout=30, proxies=proxies)
            json_text = response.text
            
            if json_text:
                try:
                    data = json.loads(json_text)
                    video_url = data.get("videoSource")
                    if not video_url:
                        video_url = data.get("securedLink")
                    
                    if video_url:
                        logger.info(f"Found video URL via API: {video_url}")
                        
                        # [RESOLUTION PARSING] - 같은 세션으로 m3u8 파싱 (쿠키 유지)
                        try:
                            m3u8_headers = {
                                "referer": iframe_src,
                                "origin": iframe_domain,
                                "accept": "*/*",
                            }
                            m3u8_resp = scraper.get(video_url, headers=m3u8_headers, timeout=10, proxies=proxies)
                            m3u8_content = m3u8_resp.text
                            logger.debug(f"m3u8 content (first 300 chars): {m3u8_content[:300]}")
                            
                            if "#EXT-X-STREAM-INF" in m3u8_content:
                                for line in m3u8_content.strip().split('\n'):
                                    if line.startswith('#EXT-X-STREAM-INF'):
                                        res_match = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                                        if res_match:
                                            resolution = int(res_match.group(2))  # height
                                if resolution:
                                    logger.info(f"Detected resolution from m3u8: {resolution}p")
                        except Exception as res_err:
                            logger.warning(f"Resolution parsing failed: {res_err}")
                        
                        # VTT 자막 확인 (있는 경우)
                        vtt_url = data.get("videoSubtitle")
                        if vtt_url:
                            logger.info(f"Found subtitle URL via API: {vtt_url}")
                        
                        # 세션 쿠키를 파일로 저장 (yt-dlp용)
                        try:
                            # Netscape 형식 쿠키 파일 생성
                            fd, cookies_file = tempfile.mkstemp(suffix='.txt', prefix='cdndania_cookies_')
                            with os.fdopen(fd, 'w') as f:
                                f.write("# Netscape HTTP Cookie File\n")
                                f.write("# https://curl.haxx.se/docs/http-cookies.html\n\n")
                                for cookie in scraper.cookies:
                                    # 형식: domain, flag, path, secure, expiry, name, value
                                    domain = cookie.domain
                                    flag = "TRUE" if domain.startswith('.') else "FALSE"
                                    path = cookie.path or "/"
                                    secure = "TRUE" if cookie.secure else "FALSE"
                                    expiry = str(int(cookie.expires)) if cookie.expires else "0"
                                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{cookie.name}\t{cookie.value}\n")
                            logger.info(f"Saved {len(scraper.cookies)} cookies to: {cookies_file}")
                        except Exception as cookie_err:
                            logger.warning(f"Failed to save cookies: {cookie_err}")
                            cookies_file = None
                            
                except Exception as json_err:
                    logger.warning(f"Failed to parse API JSON: {json_err}")
                    logger.debug(f"API Response Text (First 1000 chars): {json_text[:1000] if json_text else 'Empty'}")
            
            # API 실패 시 기존 방식(정규식)으로 폴백
            if not video_url:
                logger.info("API extraction failed, falling back to regex")
                # Ensure referer is percent-encoded for headers (avoids UnicodeEncodeError)
                encoded_referer = parse.quote(referer_url, safe=":/?#[]@!$&'()*+,;=%")
                html_response = scraper.get(iframe_src, headers={"referer": encoded_referer}, timeout=30, proxies=proxies)
                html_content = html_response.text
                if html_content:
                    # m3u8 URL 패턴 찾기
                    m3u8_patterns = [
                        re.compile(r"file:\s*['\"]([^'\"]*(?:\.m3u8|master\.txt)[^'\"]*)['\"]"),
                        re.compile(r"['\"]([^'\"]*(?:\.m3u8|master\.txt)[^'\"]*)['\"]"),
                    ]
                    for pattern in m3u8_patterns:
                        match = pattern.search(html_content)
                        if match:
                            tmp_url = match.group(1)
                            if tmp_url.startswith("//"): tmp_url = "https:" + tmp_url
                            elif tmp_url.startswith("/"):
                                parsed = parse.urlparse(iframe_src)
                                tmp_url = f"{parsed.scheme}://{parsed.netloc}{tmp_url}"
                            video_url = tmp_url
                            logger.info(f"Found video URL via regex: {video_url}")
                            break
                    
                    if not video_url:
                        logger.warning("Regex extraction failed. Dumping HTML content.")
                        logger.debug(f"HTML Content (First 2000 chars): {html_content[:2000]}")
                    
                    if not vtt_url:
                        vtt_match = re.search(r"['\"]([^'\"]*\.vtt[^'\"]*)['\"]", html_content)
                        if vtt_match:
                            vtt_url = vtt_match.group(1)
                            if vtt_url.startswith("//"): vtt_url = "https:" + vtt_url
                            elif vtt_url.startswith("/"):
                                parsed = parse.urlparse(iframe_src)
                                vtt_url = f"{parsed.scheme}://{parsed.netloc}{vtt_url}"

        except Exception as e:
            logger.error(f"Error in extract_video_from_cdndania: {e}")
            logger.error(traceback.format_exc())
        
        return video_url, vtt_url, cookies_file, resolution


    # def callback_function(self, **args):
    #     refresh_type = None
    #     # entity = self.get_entity_by_entity_id(arg['plugin_id'])
    #     entity = self.get_entity_by_entity_id(args['data']['callback_id'])
    #
    #     if args['type'] == 'status_change':
    #         if args['status'] == SupportFfmpeg.Status.DOWNLOADING:
    #             refresh_type = 'status_change'
    #         elif args['status'] == SupportFfmpeg.Status.COMPLETED:
    #             refresh_type = 'status_change'
    #             logger.debug('ffmpeg_queue_v1.py:: download completed........')
    #         elif args['status'] == SupportFfmpeg.Status.READY:
    #             data = {'type': 'info',
    #                     'msg': '다운로드중 Duration(%s)' % args['data']['duration_str'] + '<br>' + args['data'][
    #                         'save_fullpath'], 'url': '/ffmpeg/download/list'}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'add'
    #     elif args['type'] == 'last':
    #         if args['status'] == SupportFfmpeg.Status.WRONG_URL:
    #             data = {'type': 'warning', 'msg': '잘못된 URL입니다'}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'add'
    #         elif args['status'] == SupportFfmpeg.Status.WRONG_DIRECTORY:
    #             data = {'type': 'warning', 'msg': '잘못된 디렉토리입니다.<br>' + args['data']['save_fullpath']}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'add'
    #         elif args['status'] == SupportFfmpeg.Status.ERROR or args['status'] == SupportFfmpeg.Status.EXCEPTION:
    #             data = {'type': 'warning', 'msg': '다운로드 시작 실패.<br>' + args['data']['save_fullpath']}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'add'
    #         elif args['status'] == SupportFfmpeg.Status.USER_STOP:
    #             data = {'type': 'warning', 'msg': '다운로드가 중지 되었습니다.<br>' + args['data']['save_fullpath'],
    #                     'url': '/ffmpeg/download/list'}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'last'
    #         elif args['status'] == SupportFfmpeg.Status.COMPLETED:
    #             logger.debug('ffmpeg download completed......')
    #             entity.download_completed()
    #             data = {'type': 'success', 'msg': '다운로드가 완료 되었습니다.<br>' + args['data']['save_fullpath'],
    #                     'url': '/ffmpeg/download/list'}
    #
    #
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'last'
    #         elif args['status'] == SupportFfmpeg.Status.TIME_OVER:
    #             data = {'type': 'warning', 'msg': '시간초과로 중단 되었습니다.<br>' + args['data']['save_fullpath'],
    #                     'url': '/ffmpeg/download/list'}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'last'
    #         elif args['status'] == SupportFfmpeg.Status.PF_STOP:
    #             data = {'type': 'warning', 'msg': 'PF초과로 중단 되었습니다.<br>' + args['data']['save_fullpath'],
    #                     'url': '/ffmpeg/download/list'}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'last'
    #         elif args['status'] == SupportFfmpeg.Status.FORCE_STOP:
    #             data = {'type': 'warning', 'msg': '강제 중단 되었습니다.<br>' + args['data']['save_fullpath'],
    #                     'url': '/ffmpeg/download/list'}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'last'
    #         elif args['status'] == SupportFfmpeg.Status.HTTP_FORBIDDEN:
    #             data = {'type': 'warning', 'msg': '403에러로 중단 되었습니다.<br>' + args['data']['save_fullpath'],
    #                     'url': '/ffmpeg/download/list'}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'last'
    #         elif args['status'] == SupportFfmpeg.Status.ALREADY_DOWNLOADING:
    #             data = {'type': 'warning', 'msg': '임시파일폴더에 파일이 있습니다.<br>' + args['data']['temp_fullpath'],
    #                     'url': '/ffmpeg/download/list'}
    #             socketio.emit("notify", data, namespace='/framework', broadcast=True)
    #             refresh_type = 'last'
    #     elif args['type'] == 'normal':
    #         if args['status'] == SupportFfmpeg.Status.DOWNLOADING:
    #             refresh_type = 'status'
    #     # P.logger.info(refresh_type)
    #     # Todo:
    #     self.socketio_callback(refresh_type, args['data'])





class ModelOhli24Item(ModelBase):
    P = P
    __tablename__ = "{package_name}_ohli24_item".format(package_name=P.package_name)
    __table_args__ = {"mysql_collate": "utf8_general_ci"}
    __bind_key__ = P.package_name
    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)
    completed_time = db.Column(db.DateTime)
    reserved = db.Column(db.JSON)
    content_code = db.Column(db.String)
    season = db.Column(db.Integer)
    episode_no = db.Column(db.Integer)
    title = db.Column(db.String)
    episode_title = db.Column(db.String)
    ohli24_va = db.Column(db.String)
    ohli24_vi = db.Column(db.String)
    ohli24_id = db.Column(db.String)
    quality = db.Column(db.String)
    filepath = db.Column(db.String)
    filename = db.Column(db.String)
    savepath = db.Column(db.String)
    video_url = db.Column(db.String)
    vtt_url = db.Column(db.String)
    thumbnail = db.Column(db.String)
    status = db.Column(db.String)
    ohli24_info = db.Column(db.JSON)

    def __init__(self):
        self.created_time = datetime.now()

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret["created_time"] = self.created_time.strftime("%Y-%m-%d %H:%M:%S")
        ret["completed_time"] = (
            self.completed_time.strftime("%Y-%m-%d %H:%M:%S") if self.completed_time is not None else None
        )
        return ret

    def save(self):
        try:
            with F.app.app_context():
                F.db.session.add(self)
                F.db.session.commit()
                return self
        except Exception as e:
            self.P.logger.error(f"Exception:{str(e)}")
            self.P.logger.error(traceback.format_exc())

    @classmethod
    def get_by_id(cls, id):
        try:
            with F.app.app_context():
                return F.db.session.query(cls).filter_by(id=int(id)).first()
        except Exception as e:
            cls.P.logger.error(f"Exception:{str(e)}")
            cls.P.logger.error(traceback.format_exc())

    @classmethod
    def get_by_ohli24_id(cls, ohli24_id):
        try:
            with F.app.app_context():
                return F.db.session.query(cls).filter_by(ohli24_id=ohli24_id).first()
        except Exception as e:
            cls.P.logger.error(f"Exception:{str(e)}")
            cls.P.logger.error(traceback.format_exc())

    @classmethod
    def delete_by_id(cls, idx):
        db.session.query(cls).filter_by(id=idx).delete()
        db.session.commit()
        return True

    @classmethod
    def web_list(cls, req):
        ret = {}
        page = int(req.form["page"]) if "page" in req.form else 1
        page_size = 30
        job_id = ""
        search = req.form["search_word"] if "search_word" in req.form else ""
        option = req.form["option"] if "option" in req.form else "all"
        order = req.form["order"] if "order" in req.form else "desc"
        query = cls.make_query(search=search, order=order, option=option)
        count = query.count()
        query = query.limit(page_size).offset((page - 1) * page_size)
        lists = query.all()
        ret["list"] = [item.as_dict() for item in lists]
        ret["paging"] = cls.get_paging_info(count, page, page_size)
        return ret

    @classmethod
    def make_query(cls, search="", order="desc", option="all"):
        query = db.session.query(cls)
        if search is not None and search != "":
            if search.find("|") != -1:
                tmp = search.split("|")
                conditions = []
                for tt in tmp:
                    if tt != "":
                        conditions.append(cls.filename.like("%" + tt.strip() + "%"))
                query = query.filter(or_(*conditions))
            elif search.find(",") != -1:
                tmp = search.split(",")
                for tt in tmp:
                    if tt != "":
                        query = query.filter(cls.filename.like("%" + tt.strip() + "%"))
            else:
                query = query.filter(cls.filename.like("%" + search + "%"))
        if option == "completed":
            query = query.filter(cls.status == "completed")

        query = query.order_by(desc(cls.id)) if order == "desc" else query.order_by(cls.id)
        return query

    @classmethod
    def get_list_uncompleted(cls):
        return db.session.query(cls).filter(cls.status != "completed").all()

    @classmethod
    def append(cls, q):
        item = ModelOhli24Item()
        item.content_code = q["content_code"]
        item.season = q["season"]
        item.episode_no = q["epi_queue"]
        item.title = q["content_title"]
        item.episode_title = q["title"]
        item.ohli24_va = q["va"]
        item.ohli24_vi = q["_vi"]
        item.ohli24_id = q["_id"]
        item.quality = q["quality"]
        item.filepath = q["filepath"]
        item.filename = q["filename"]
        item.savepath = q["savepath"]
        item.video_url = q["url"]
        item.vtt_url = q["vtt"]
        item.thumbnail = q["thumbnail"]
        item.status = "wait"
        item.ohli24_info = q["ohli24_info"]
        item.save()


class ModelOhli24Program(ModelBase):
    P = P
    __tablename__ = f"{P.package_name}_{name}_program"
    __table_args__ = {"mysql_collate": "utf8_general_ci"}
    __bind_key__ = P.package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime, nullable=False)
    completed_time = db.Column(db.DateTime)
    completed = db.Column(db.Boolean)

    clip_id = db.Column(db.String)
    info = db.Column(db.String)
    status = db.Column(db.String)
    call = db.Column(db.String)
    queue_list = []

    def __init__(self, clip_id, info, call="user"):
        self.clip_id = clip_id
        self.info = info
        self.completed = False
        self.created_time = datetime.now()
        self.status = "READY"
        self.call = call

    def init_for_queue(self):
        self.status = "READY"
        self.queue_list.append(self)

    @classmethod
    def get(cls, clip_id):
        with F.app.app_context():
            return (
                db.session.query(cls)
                .filter_by(
                    clip_id=clip_id,
                )
                .order_by(desc(cls.id))
                .first()
            )

    @classmethod
    def is_duplicate(cls, clip_id):
        return cls.get(clip_id) is not None

    # 오버라이딩
    @classmethod
    def make_query(cls, req, order="desc", search="", option1="all", option2="all"):
        with F.app.app_context():
            query = F.db.session.query(cls)
            # query = cls.make_query_search(query, search, cls.program_title)
            query = query.filter(cls.info["channel_name"].like("%" + search + "%"))
            if option1 == "completed":
                query = query.filter_by(completed=True)
            elif option1 == "incompleted":
                query = query.filter_by(completed=False)
            elif option1 == "auto":
                query = query.filter_by(call="user")

            if order == "desc":
                query = query.order_by(desc(cls.id))
            else:
                query = query.order_by(cls.id)
            return query

    @classmethod
    def remove_all(cls, is_completed=True):  # to remove_all(True/False)
        with F.app.app_context():
            count = db.session.query(cls).filter_by(completed=is_completed).delete()
            db.session.commit()
            return count

    @classmethod
    def get_failed(cls):
        with F.app.app_context():
            return db.session.query(cls).filter_by(completed=False).all()

    # only for queue

    @classmethod
    def get_by_id_in_queue(cls, id):
        for _ in cls.queue_list:
            if _.id == int(id):
                return _

    # only for queue END
