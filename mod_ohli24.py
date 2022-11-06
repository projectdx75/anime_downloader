#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 3:44 PM
# @Author  : yommi
# @Site    :
# @File    : logic_ohli24
# @Software: PyCharm

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
from urllib import parse

# third-party
import requests
# third-party
from flask import request, render_template, jsonify
from lxml import html
from sqlalchemy import or_, desc

pkgs = ["bs4", "jsbeautifier", "aiohttp"]
for pkg in pkgs:
    try:
        importlib.import_module(pkg)
    # except ImportError:
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'])
        # main(["install", pkg])
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])
        importlib.import_module(pkg)

# third party package
import aiohttp

from bs4 import BeautifulSoup
import jsbeautifier

# sjva 공용
from framework import db, scheduler, path_data, socketio
from framework.util import Util
# from framework.common.util import headers
from framework import F
from plugin import (
    PluginModuleBase
)
from .lib._ffmpeg_queue import FfmpegQueueEntity, FfmpegQueue
from support.expand.ffmpeg import SupportFfmpeg

from .lib.util import Util

from .setup import *

logger = P.logger

print('*=' * 50)


class LogicOhli24(PluginModuleBase):
    db_default = {
        "ohli24_db_version": "1",
        "ohli24_url": "https://ohli24.net",
        "ohli24_download_path": os.path.join(path_data, P.package_name, "ohli24"),
        "ohli24_auto_make_folder": "True",
        "ohli24_auto_make_season_folder": "True",
        "ohli24_finished_insert": "[완결]",
        "ohli24_max_ffmpeg_process_count": "1",
        "ohli24_order_desc": "False",
        "ohli24_auto_start": "False",
        "ohli24_interval": "* 5 * * *",
        "ohli24_auto_mode_all": "False",
        "ohli24_auto_code_list": "all",
        "ohli24_current_code": "",
        "ohli24_uncompleted_auto_enqueue": "False",
        "ohli24_image_url_prefix_series": "https://www.jetcloud.cc/series/",
        "ohli24_image_url_prefix_episode": "https://www.jetcloud-list.cc/thumbnail/",
        "ohli24_discord_notify": "True",
    }
    current_headers = None
    current_data = None

    session = requests.Session()

    headers = {
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.5249.114 Whale/3.17.145.12 Safari/537.36',
        'authority': 'ndoodle.xyz',
        'accept': '*/*',
        'accept-language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'referer': 'https://ndoodle.xyz/video/e6e31529675d0ef99d777d729c423382'

    }
    useragent = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
                      "like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
    }

    def __init__(self, P):
        super(LogicOhli24, self).__init__(P, "setting", scheduler_desc="ohli24 자동 다운로드")
        self.name = "ohli24"
        self.queue = None
        # default_route_socketio(P, self)
        default_route_socketio_module(self, attach='/search')

    @staticmethod
    def db_init():
        pass
        # try:
        #     for key, value in P.Logic.db_default.items():
        #         if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
        #             db.session.add(ModelSetting(key, value))
        #     db.session.commit()
        # except Exception as e:
        #     logger.error('Exception:%s', e)
        #     logger.error(traceback.format_exc())

    def process_menu(self, sub, req):
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
    def process_ajax(self, sub, req):

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
                self.current_data = data
                return jsonify({"ret": "success", "data": data, "code": code})
            elif sub == "anime_list":

                data = self.get_anime_info(cate, page)
                return jsonify(
                    {"ret": "success", "cate": cate, "page": page, "data": data}
                )
            elif sub == "complete_list":

                logger.debug("cate:: %s", cate)
                page = request.form["page"]

                data = self.get_anime_info(cate, page)
                return jsonify(
                    {"ret": "success", "cate": cate, "page": page, "data": data}
                )
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
            elif sub == "entity_list":
                return jsonify(self.queue.get_entity_list())
            elif sub == "queue_command":
                ret = self.queue.command(
                    req.form["command"], int(req.form["entity_id"])
                )
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
                    socketio.emit(
                        "notify", notify, namespace="/framework", broadcast=True
                    )

                thread = threading.Thread(target=func, args=())
                thread.daemon = True
                thread.start()
                return jsonify("")
            elif sub == "web_list":
                return jsonify(ModelOhli24Item.web_list(request))
            elif sub == "db_remove":
                return jsonify(ModelOhli24Item.delete_by_id(req.form["id"]))
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
        except Exception as e:
            P.logger.error(f"Exception: {e}")
            P.logger.error(traceback.format_exc())

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
            whitelist_programs = [
                str(x.strip()) for x in whitelist_program.replace("\n", "|").split("|")
            ]

            if code not in whitelist_programs:
                whitelist_programs.append(code)
                whitelist_programs = filter(
                    lambda x: x != "", whitelist_programs
                )  # remove blank code
                whitelist_program = "|".join(whitelist_programs)
                entity = (
                    db.session.query(P.ModelSetting)
                    .filter_by(key="ohli24_auto_code_list")
                    .with_for_update()
                    .first()
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
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            ret["ret"] = False
            ret["log"] = str(e)
        return ret

    def setting_save_after(self, change_list):
        if self.queue.get_max_ffmpeg_count() != P.ModelSetting.get_int(
                "ohli24_max_ffmpeg_process_count"
        ):
            self.queue.set_max_ffmpeg_count(
                P.ModelSetting.get_int("ohli24_max_ffmpeg_process_count")
            )

    def scheduler_function(self):
        # Todo: 스케쥴링 함수 미구현
        logger.debug(f"ohli24 scheduler_function::=========================")

        content_code_list = P.ModelSetting.get_list("ohli24_auto_code_list", "|")
        logger.debug(f"content_code_list::: {content_code_list}")
        url_list = ["https://www.naver.com/", "https://www.daum.net/"]

        week = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        today = date.today()
        print(today)
        print()
        print(today.weekday())

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
                print("scheduling url: %s", url)
                # ret_data = LogicOhli24.get_auto_anime_info(self, url=url)
                content_info = self.get_series_info(item, "", "")

                for episode_info in content_info["episode"]:
                    add_ret = self.add(episode_info)
                    if add_ret.startswith("enqueue"):
                        self.socketio_callback("list_refresh", "")
                # logger.debug(f"data: {data}")
                # self.current_data = data
                # db에서 다운로드 완료 유무 체크

    @staticmethod
    async def get_data(url) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                content = await response.text()
                # print(response)
                return content

    @staticmethod
    async def main(url_list: list):
        input_coroutines = [LogicOhli24.get_data(url_) for url_ in url_list]
        res = await asyncio.gather(*input_coroutines)
        return res

    def get_series_info(self, code, wr_id, bo_table):
        code_type = "c"

        try:
            if (
                    self.current_data is not None
                    and "code" in self.current_data
                    and self.current_data["code"] == code
            ):
                return self.current_data

            if code.startswith("http"):

                # if code.split('c/')[1] is not None:
                #     code = code.split('c/')[1]
                #     code_type = 'c'
                # elif code.split('e/')[1] is not None:
                #     code_type = 'e'
                #     code = code.split('e/')[1]
                if "/c/" in code:
                    code = code.split("c/")[1]
                    code_type = "c"
                elif "/e/" in code:
                    code = code.split("e/")[1]
                    code_type = "e"

                logger.info(f"code:::: {code}")

            if code_type == "c":
                url = P.ModelSetting.get("ohli24_url") + "/c/" + code
            elif code_type == "e":
                url = P.ModelSetting.get("ohli24_url") + "/e/" + code
            else:
                url = P.ModelSetting.get("ohli24_url") + "/e/" + code

            if wr_id is not None:
                # print(len(wr_id))
                if len(wr_id) > 0:
                    url = (
                            P.ModelSetting.get("ohli24_url")
                            + "/bbs/board.php?bo_table="
                            + bo_table
                            + "&wr_id="
                            + wr_id
                    )
                else:
                    pass

            logger.debug('url:::> %s', url)

            response_data = LogicOhli24.get_html(url, timeout=10)
            tree = html.fromstring(response_data)
            title = tree.xpath('//div[@class="view-title"]/h1/text()')[0]
            # image = tree.xpath('//div[@class="view-info"]/div[@class="image"]/div/img')[0]['src']
            image = tree.xpath('//div[@class="image"]/div/img/@src')[0]
            image = image.replace("..", P.ModelSetting.get("ohli24_url"))
            des_items = tree.xpath('//div[@class="list"]/p')
            des = {}
            des_key = [
                "_otit",
                "_dir",
                "_pub",
                "_tag",
                "_classifi",
                "_country",
                "_grade",
                "_total_chapter",
                "_show_time",
                "_release_year",
            ]
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
            }

            list_body_li = tree.xpath('//ul[@class="list-body"]/li')
            # logger.debug(f"list_body_li:: {list_body_li}")
            episodes = []
            vi = None
            for li in list_body_li:
                # logger.debug(li)
                title = li.xpath(".//a/text()")[0].strip()
                thumbnail = image
                # logger.info(li.xpath('//a[@class="item-subject"]/@href'))
                link = (
                        P.ModelSetting.get("ohli24_url")
                        + li.xpath('.//a[@class="item-subject"]/@href')[0]
                )
                # logger.debug(f"link:: {link}")
                date = li.xpath('.//div[@class="wr-date"]/text()')[0]
                m = hashlib.md5(title.encode("utf-8"))
                # _vi = hashlib.md5(title.encode('utf-8').hexdigest())
                # logger.info(m.hexdigest())
                _vi = m.hexdigest()
                episodes.append(
                    {
                        "title": title,
                        "link": link,
                        "thumbnail": image,
                        "date": date,
                        "day": date,
                        "_id": title,
                        "va": link,
                        "_vi": _vi,
                        "content_code": code,
                    }
                )

            # logger.info("des_items length:: %s", len(des_items))
            for idx, item in enumerate(des_items):
                # key = des_key[idx]
                span = item.xpath(".//span//text()")
                # logger.info(span)
                key = description_dict[span[0]]
                try:
                    des[key] = item.xpath(".//span/text()")[1]
                except IndexError:
                    des[key] = ""

            # logger.info(f"des::>> {des}")
            image = image.replace("..", P.ModelSetting.get("ohli24_url"))
            # logger.info("images:: %s", image)
            logger.info("title:: %s", title)

            ser_description = tree.xpath(
                '//div[@class="view-stocon"]/div[@class="c"]/text()'
            )

            data = {
                "title": title,
                "image": image,
                "date": "2022.01.11 00:30 (화)",
                "ser_description": ser_description,
                "des": des,
                "episode": episodes,
            }

            if P.ModelSetting.get_bool("ohli24_order_desc"):
                data["episode"] = list(reversed(data["episode"]))
                data["list_order"] = "desc"

            return data
            # logger.info(response_text)

        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    def get_anime_info(self, cate, page):
        print(cate, page)
        try:
            if cate == "ing":
                url = (
                        P.ModelSetting.get("ohli24_url")
                        + "/bbs/board.php?bo_table="
                        + cate
                        + "&page="
                        + page
                )
            elif cate == "movie":
                url = (
                        P.ModelSetting.get("ohli24_url")
                        + "/bbs/board.php?bo_table="
                        + cate
                        + "&page="
                        + page
                )
            else:
                url = (
                        P.ModelSetting.get("ohli24_url")
                        + "/bbs/board.php?bo_table="
                        + cate
                        + "&page="
                        + page
                )
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
                entity["title"] = item.xpath(".//div[@class='post-title']/text()")[
                    0
                ].strip()
                entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@src")[
                    0
                ].replace("..", P.ModelSetting.get("ohli24_url"))
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
                entity["title"] = item.xpath(".//div[@class='post-title']/text()")[
                    0
                ].strip()
                entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@src")[
                    0
                ].replace("..", P.ModelSetting.get("ohli24_url"))
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
                entity["title"] = "".join(
                    item.xpath(".//div[@class='post-title']/text()")
                ).strip()
                entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@src")[
                    0
                ].replace("..", P.ModelSetting.get("ohli24_url"))

                entity["code"] = item.xpath(".//div[@class='img-item']/img/@alt")[0]

                data["ret"] = "success"
                data["anime_list"].append(entity)

            return data
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    # @staticmethod
    def plugin_load(self):
        try:
            # ffmpeg_modelsetting = get_model_setting("ffmpeg", logger)
            # SupportFfmpeg.initialize(P.ModelSetting.get('ffmpeg_path'), os.path.join(F.config['path_data'], 'tmp'),
            #                          self.callback_function, P.ModelSetting.get_int('max_pf_count'))
            # P.logger.debug(ffmpeg_modelsetting.get('ffmpeg_path'))
            P.logger.debug(F.config['path_data'])

            # SupportFfmpeg.initialize(ffmpeg_modelsetting.get('ffmpeg_path'), os.path.join(F.config['path_data'], 'tmp'),
            #                          self.callback_function, ffmpeg_modelsetting.get_int('max_pf_count'))

            SupportFfmpeg.initialize("ffmpeg", os.path.join(F.config['path_data'], 'tmp'),
                                     self.callback_function, 1)

            logger.debug("%s plugin_load", P.package_name)
            self.queue = FfmpegQueue(
                P, P.ModelSetting.get_int("ohli24_max_ffmpeg_process_count")
            )
            self.current_data = None
            self.queue.queue_start()

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    # @staticmethod
    def plugin_unload(self):
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
    def get_html(url, referer=None, stream=False, timeout=5):
        data = ""
        headers = {
            "referer": f"https://ohli24.net",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
                          "Mozilla/5.0 (Macintosh; Intel "
                          "Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 "
                          "Whale/3.12.129.46 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:

            if LogicOhli24.session is None:
                LogicOhli24.session = requests.session()

            # logger.debug('get_html :%s', url)
            headers["Referer"] = "" if referer is None else referer
            page_content = LogicOhli24.session.get(
                url, headers=headers, timeout=timeout
            )
            data = page_content.text
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
        return data

    #########################################################
    def add(self, episode_info):
        if self.is_exist(episode_info):
            return "queue_exist"
        else:
            db_entity = ModelOhli24Item.get_by_ohli24_id(episode_info["_id"])
            # logger.debug("db_entity:::> %s", db_entity)
            if db_entity is None:
                entity = Ohli24QueueEntity(P, self, episode_info)
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

                logger.debug("entity:::> %s", entity.as_dict())

                P.logger.debug(F.config['path_data'])
                P.logger.debug(self.headers)

                filename = os.path.basename(entity.filepath)
                ffmpeg = SupportFfmpeg(entity.url, entity.filename, callback_function=self.callback_function,
                                       max_pf_count=0, save_path=entity.savepath, timeout_minute=60,
                                       headers=self.headers)
                ret = {'ret': 'success'}
                ret['json'] = ffmpeg.start()

                # self.queue.add_queue(entity)
                return "enqueue_db_exist"
            else:
                return "db_completed"

    def is_exist(self, info):
        # for en in self.queue.entity_list:
        #     if en.info["_id"] == info["_id"]:
        #         return True
        return False

    def callback_function(self, **args):
        refresh_type = None
        if args['type'] == 'status_change':
            if args['status'] == SupportFfmpeg.Status.DOWNLOADING:
                refresh_type = 'status_change'
            elif args['status'] == SupportFfmpeg.Status.COMPLETED:
                refresh_type = 'status_change'
            elif args['status'] == SupportFfmpeg.Status.READY:
                data = {'type': 'info',
                        'msg': '다운로드중 Duration(%s)' % args['data']['duration_str'] + '<br>' + args['data'][
                            'save_fullpath'], 'url': '/ffmpeg/download/list'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'add'
        elif args['type'] == 'last':
            if args['status'] == SupportFfmpeg.Status.WRONG_URL:
                data = {'type': 'warning', 'msg': '잘못된 URL입니다'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'add'
            elif args['status'] == SupportFfmpeg.Status.WRONG_DIRECTORY:
                data = {'type': 'warning', 'msg': '잘못된 디렉토리입니다.<br>' + args['data']['save_fullpath']}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'add'
            elif args['status'] == SupportFfmpeg.Status.ERROR or args['status'] == SupportFfmpeg.Status.EXCEPTION:
                data = {'type': 'warning', 'msg': '다운로드 시작 실패.<br>' + args['data']['save_fullpath']}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'add'
            elif args['status'] == SupportFfmpeg.Status.USER_STOP:
                data = {'type': 'warning', 'msg': '다운로드가 중지 되었습니다.<br>' + args['data']['save_fullpath'],
                        'url': '/ffmpeg/download/list'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'last'
            elif args['status'] == SupportFfmpeg.Status.COMPLETED:
                data = {'type': 'success', 'msg': '다운로드가 완료 되었습니다.<br>' + args['data']['save_fullpath'],
                        'url': '/ffmpeg/download/list'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'last'
            elif args['status'] == SupportFfmpeg.Status.TIME_OVER:
                data = {'type': 'warning', 'msg': '시간초과로 중단 되었습니다.<br>' + args['data']['save_fullpath'],
                        'url': '/ffmpeg/download/list'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'last'
            elif args['status'] == SupportFfmpeg.Status.PF_STOP:
                data = {'type': 'warning', 'msg': 'PF초과로 중단 되었습니다.<br>' + args['data']['save_fullpath'],
                        'url': '/ffmpeg/download/list'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'last'
            elif args['status'] == SupportFfmpeg.Status.FORCE_STOP:
                data = {'type': 'warning', 'msg': '강제 중단 되었습니다.<br>' + args['data']['save_fullpath'],
                        'url': '/ffmpeg/download/list'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'last'
            elif args['status'] == SupportFfmpeg.Status.HTTP_FORBIDDEN:
                data = {'type': 'warning', 'msg': '403에러로 중단 되었습니다.<br>' + args['data']['save_fullpath'],
                        'url': '/ffmpeg/download/list'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'last'
            elif args['status'] == SupportFfmpeg.Status.ALREADY_DOWNLOADING:
                data = {'type': 'warning', 'msg': '임시파일폴더에 파일이 있습니다.<br>' + args['data']['temp_fullpath'],
                        'url': '/ffmpeg/download/list'}
                socketio.emit("notify", data, namespace='/framework', broadcast=True)
                refresh_type = 'last'
        elif args['type'] == 'normal':
            if args['status'] == SupportFfmpeg.Status.DOWNLOADING:
                refresh_type = 'status'
        # P.logger.info(refresh_type)
        self.socketio_callback(refresh_type, args['data'])


class Ohli24QueueEntity(FfmpegQueueEntity):
    def __init__(self, P, module_logic, info):
        super(Ohli24QueueEntity, self).__init__(P, module_logic, info)
        self._vi = None
        self.url = None
        self.epi_queue = None
        self.filepath = None
        self.savepath = None
        self.quality = None
        self.filename = None
        self.vtt = None
        self.season = 1
        self.content_title = None
        self.srt_url = None
        self.headers = None
        # Todo::: 임시 주석 처리
        self.make_episode_info()

    def refresh_status(self):
        self.module_logic.socketio_callback("status", self.as_dict())

    def info_dict(self, tmp):
        # logger.debug('self.info::> %s', self.info)
        for key, value in self.info.items():
            tmp[key] = value
        tmp["vtt"] = self.vtt
        tmp["season"] = self.season
        tmp["content_title"] = self.content_title
        tmp["ohli24_info"] = self.info
        tmp["epi_queue"] = self.epi_queue
        return tmp

    def donwload_completed(self):
        db_entity = ModelOhli24Item.get_by_ohli24_id(self.info["_id"])
        if db_entity is not None:
            db_entity.status = "completed"
            db_entity.complated_time = datetime.now()
            db_entity.save()

    # Get episode info from OHLI24 site

    def make_episode_info(self):
        try:
            # url = 'https://ohli24.net/e/' + self.info['va']
            base_url = "https://ohli24.net"
            iframe_url = ""

            # https://ohli24.net/e/%EB%85%B9%EC%9D%84%20%EB%A8%B9%EB%8A%94%20%EB%B9%84%EC%8A%A4%EC%BD%94%206%ED%99%94
            url = self.info["va"]

            ourls = parse.urlparse(url)

            headers = {
                "referer": f"{ourls.scheme}://{ourls.netloc}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36",
            }
            logger.debug("make_episode_info()::url==> %s", url)
            logger.info(f"self.info:::> {self.info}")

            text = requests.get(url, headers=headers).text
            # logger.debug(text)
            soup1 = BeautifulSoup(text, "lxml")
            pattern = re.compile(r"url : \"\.\.(.*)\"")
            script = soup1.find("script", text=pattern)

            if script:
                match = pattern.search(script.text)
                if match:
                    iframe_url = match.group(1)
                    logger.info("iframe_url::> %s", iframe_url)

            logger.debug(soup1.find("iframe"))

            iframe_url = soup1.find("iframe")["src"]
            logger.info("iframe_url::> %s", iframe_url)

            print(base_url)
            print(iframe_url)
            # exit()

            # resp = requests.get(iframe_url, headers=headers, timeout=20).text
            # soup2 = BeautifulSoup(resp, "lxml")
            # iframe_src = soup2.find("iframe")["src"]
            iframe_src = iframe_url
            # print(resp1)

            logger.debug(f"iframe_src:::> {iframe_src}")

            resp1 = requests.get(iframe_src, headers=headers, timeout=600).text
            # logger.info('resp1::>> %s', resp1)
            soup3 = BeautifulSoup(resp1, "lxml")
            # packed_pattern = re.compile(r'\\{*(eval.+)*\\}', re.MULTILINE | re.DOTALL)
            s_pattern = re.compile(r"(eval.+)", re.MULTILINE | re.DOTALL)
            packed_pattern = re.compile(
                r"if?.([^{}]+)\{.*(eval.+)\}.+else?.{.(eval.+)\}", re.DOTALL
            )
            packed_script = soup3.find("script", text=s_pattern)
            # packed_script = soup3.find('script')
            logger.info('packed_script>>> %s', packed_script.text)
            unpack_script = None
            if packed_script is not None:
                # logger.debug('zzzzzzzzzzzz')
                # match = packed_pattern.search(packed_script.text)
                # match = re.search(packed_pattern, packed_script.text)
                # logger.debug("match::: %s", match.group())
                # unpack_script = jsbeautifier.beautify(match.group(3))
                unpack_script = jsbeautifier.beautify(packed_script.text)

                # logger.info('match groups:: %s', match.groups())
                # logger.info('match group3:: %s', match.group(3))
                # print('packed_script==>', packed_script)
                # logger.debug(unpack_script)

            p1 = re.compile(r"(\"tracks\".*\])\,\"captions\"", re.MULTILINE | re.DOTALL)
            m2 = re.search(
                r"(\"tracks\".*\]).*\"captions\"",
                unpack_script,
                flags=re.MULTILINE | re.DOTALL,
            )
            # print(m2.group(1))
            dict_string = "{" + m2.group(1) + "}"

            logger.info(f"dict_string::> {dict_string}")
            tracks = json.loads(dict_string)
            self.srt_url = tracks["tracks"][0]["file"]

            logger.debug(f'srt_url::: {tracks["tracks"][0]["file"]}')

            video_hash = iframe_src.split("/")
            video_hashcode = re.sub(r"index\.php\?data=", "", video_hash[-1])
            self._vi = video_hashcode
            video_info_url = f"{video_hash[0]}//{video_hash[2]}/player/index.php?data={video_hashcode}&do=getVideo"
            # print('hash:::', video_hash)
            logger.debug(f"video_info_url::: {video_info_url}")

            headers = {
                "referer": f"{iframe_src}",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
                              "Mozilla/5.0 (Macintosh; Intel "
                              "Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 "
                              "Whale/3.12.129.46 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
            }
            # print(headers)
            payload = {
                "hash": video_hash[-1],
            }
            resp2 = requests.post(
                video_info_url, headers=headers, data=payload, timeout=20
            ).json()

            logger.debug("resp2::> %s", resp2)

            hls_url = resp2["videoSource"]
            logger.debug(f"video_url::> {hls_url}")

            resp3 = requests.get(hls_url, headers=headers).text
            # logger.debug(resp3)

            # stream_url = hls_url.split('\n')[-1].strip()
            stream_info = resp3.split("\n")[-2:]
            # logger.debug('stream_url:: %s', stream_url)
            logger.debug(f"stream_info:: {stream_info}")
            self.headers = {
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/71.0.3554.0 Safari/537.36Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3554.0 Safari/537.36",
                "Referer": "https://ndoodle.xyz/video/03a3655fff3e9bdea48de9f49e938e32",
            }

            self.url = stream_info[1].strip()
            match = re.compile(r'NAME="(?P<quality>.*?)"').search(stream_info[0])
            self.quality = "720P"
            if match is not None:
                self.quality = match.group("quality")
                logger.info(self.quality)

            match = re.compile(
                r"(?P<title>.*?)\s*((?P<season>\d+)%s)?\s*((?P<epi_no>\d+)%s)"
                % ("기", "화")
            ).search(self.info["title"])

            # epi_no 초기값
            epi_no = 1

            if match:
                self.content_title = match.group("title").strip()
                if "season" in match.groupdict() and match.group("season") is not None:
                    self.season = int(match.group("season"))

                # epi_no = 1
                epi_no = int(match.group("epi_no"))
                ret = "%s.S%sE%s.%s-OHNI24.mp4" % (
                    self.content_title,
                    "0%s" % self.season if self.season < 10 else self.season,
                    "0%s" % epi_no if epi_no < 10 else epi_no,
                    self.quality,
                )
            else:
                self.content_title = self.info["title"]
                P.logger.debug("NOT MATCH")
                ret = "%s.720p-OHNI24.mp4" % self.info["title"]

            # logger.info('self.content_title:: %s', self.content_title)
            self.epi_queue = epi_no
            self.filename = Util.change_text_for_use_filename(ret)
            logger.info(f"self.filename::> {self.filename}")
            self.savepath = P.ModelSetting.get("ohli24_download_path")
            logger.info(f"self.savepath::> {self.savepath}")

            # TODO: 완결 처리

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
                    self.savepath = os.path.join(
                        self.savepath, "Season %s" % int(self.season)
                    )
            self.filepath = os.path.join(self.savepath, self.filename)
            if not os.path.exists(self.savepath):
                os.makedirs(self.savepath)

            # from .lib.util import write_file, convert_vtt_to_srt

            srt_filepath = os.path.join(
                self.savepath, self.filename.replace(".mp4", ".ko.srt")
            )

            if self.srt_url is not None and not os.path.exists(srt_filepath):
                if requests.get(self.srt_url, headers=headers).status_code == 200:
                    srt_data = requests.get(self.srt_url, headers=headers).text
                    Util.write_file(srt_data, srt_filepath)

        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())


class ModelOhli24Item(db.Model):
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
            self.completed_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.completed_time is not None
            else None
        )
        return ret

    def save(self):
        db.session.add(self)
        db.session.commit()

    @classmethod
    def get_by_id(cls, idx):
        return db.session.query(cls).filter_by(id=idx).first()

    @classmethod
    def get_by_ohli24_id(cls, ohli24_id):
        return db.session.query(cls).filter_by(ohli24_id=ohli24_id).first()

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
        ret["paging"] = Util.get_paging_info(count, page, page_size)
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

        query = (
            query.order_by(desc(cls.id)) if order == "desc" else query.order_by(cls.id)
        )
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
