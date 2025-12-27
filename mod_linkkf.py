#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 3:44 PM
# @Author  : yommi
# @Site    :
# @File    : logic_linkkf
# @Software: PyCharm
import json
import os
import random
import re
import sys
import time
import traceback
import urllib
from datetime import datetime
from urllib.parse import urlparse

# third-party
import requests
from bs4 import BeautifulSoup

# third-party
from flask import jsonify, render_template, request
from flaskfarm.lib.support.expand.ffmpeg import SupportFfmpeg

# sjva 공용
from framework import db, path_data, scheduler
from lxml import html
from plugin import PluginModuleBase
from requests_cache import CachedSession

packages = ["beautifulsoup4", "requests-cache", "cloudscraper"]

for package in packages:
    try:
        import package

    except ModuleNotFoundError:
        if package == "playwright":
            pass
            # os.system(f"pip3 install playwright")
            # os.system(f"playwright install")
    except ImportError:
        # main(["install", package])
        if package == "playwright":
            pass
            # os.system(f"pip3 install {package}")
            # os.system(f"playwright install")
        else:
            os.system(f"pip3 install {package}")

from anime_downloader.lib.ffmpeg_queue_v1 import FfmpegQueue, FfmpegQueueEntity
from anime_downloader.lib.util import Util

# 패키지
# from .plugin import P
from anime_downloader.setup import *

# from linkkf.model import ModelLinkkfProgram

# from linkkf.model import ModelLinkkfProgram

# from tool_base import d


logger = P.logger
name = "linkkf"


class LogicLinkkf(PluginModuleBase):
    current_headers = None
    current_data = None
    referer = None
    download_queue = None
    download_thread = None
    current_download_count = 0

    cache_path = os.path.dirname(__file__)

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/71.0.3578.98 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "",
    }
    useragent = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
    }

    def __init__(self, P):
        super(LogicLinkkf, self).__init__(
            P, "setting", scheduler_desc="linkkf 자동 다운로드"
        )
        self.queue = None
        self.name = name
        self.db_default = {
            "linkkf_db_version": "1",
            "linkkf_url": "https://linkkf.live",
            f"{self.name}_recent_code": "",
            "linkkf_download_path": os.path.join(path_data, P.package_name, "linkkf"),
            "linkkf_save_path": os.path.join(path_data, P.package_name, "linkkf"),
            "linkkf_auto_make_folder": "True",
            "linkkf_auto_make_season_folder": "True",
            "linkkf_finished_insert": "[완결]",
            "linkkf_max_ffmpeg_process_count": "2",
            f"{self.name}_max_download_count": "2",
            f"{self.name}_quality": "720p",
            "linkkf_order_desc": "False",
            "linkkf_auto_start": "False",
            "linkkf_interval": "* 5 * * *",
            "linkkf_auto_mode_all": "False",
            "linkkf_auto_code_list": "all",
            "linkkf_current_code": "",
            "linkkf_uncompleted_auto_enqueue": "False",
            "linkkf_image_url_prefix_series": "",
            "linkkf_image_url_prefix_episode": "",
            "linkkf_discord_notify": "True",
        }
        # default_route_socketio(P, self)
        default_route_socketio_module(self, attach="/setting")
        self.current_data = None

    def process_menu(self, sub, req):
        arg = P.ModelSetting.to_dict()
        arg["sub"] = self.name
        if sub in ["setting", "queue", "category", "list", "request", "search"]:
            if sub == "request" and req.args.get("code") is not None:
                arg["linkkf_current_code"] = req.args.get("code")
            if sub == "setting":
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

    def process_ajax(self, sub, req):
        try:
            if sub == "analysis":
                # code = req.form['code']
                code = request.form["code"]

                wr_id = request.form.get("wr_id", None)
                bo_table = request.form.get("bo_table", None)
                data = []
                # print(code)
                # logger.info("code::: %s", code)
                P.ModelSetting.set("linkkf_current_code", code)
                data = self.get_series_info(code)
                self.current_data = data
                return jsonify({"ret": "success", "data": data, "code": code})
            elif sub == "anime_list":
                data = []
                cate = request.form["type"]
                page = request.form["page"]

                data = self.get_anime_info(cate, page)
                # self.current_data = data
                return jsonify(
                    {"ret": "success", "cate": cate, "page": page, "data": data}
                )
            elif sub == "screen_movie_list":
                try:
                    logger.debug("request:::> %s", request.form["page"])
                    page = request.form["page"]
                    data = self.get_screen_movie_info(page)
                    dummy_data = {"ret": "success", "data": data}
                    return jsonify(data)
                except Exception as e:
                    logger.error(f"Exception: {str(e)}")
                    logger.error(traceback.format_exc())
            elif sub == "complete_list":
                pass
            elif sub == "search":
                data = []
                # cate = request.form["type"]
                # page = request.form["page"]
                cate = request.form["type"]
                query = request.form["query"]
                page = request.form["page"]

                data = self.get_search_result(query, page, cate)
                # self.current_data = data
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
                logger.info("========= add_queue START =========")
                logger.debug("linkkf add_queue routine ===============")
                ret = {}
                try:
                    form_data = request.form.get("data")
                    if not form_data:
                        logger.error(f"No data in form. Form keys: {list(request.form.keys())}")
                        ret["ret"] = "error"
                        ret["log"] = "No data received"
                        return jsonify(ret)
                    info = json.loads(form_data)
                    logger.info(f"info:: {info}")
                    ret["ret"] = self.add(info)
                except Exception as e:
                    logger.error(f"add_queue error: {e}")
                    logger.error(traceback.format_exc())
                    ret["ret"] = "error"
                    ret["log"] = str(e)
                return jsonify(ret)
            elif sub == "entity_list":
                ret = {"list": self.queue.get_entity_list() if self.queue else []}
                return jsonify(ret)
            elif sub == "queue_command":
                cmd = request.form.get("cmd", "")
                entity_id = request.form.get("entity_id", "")
                if self.queue:
                    ret = self.queue.command(cmd, int(entity_id) if entity_id else 0)
                else:
                    ret = {"ret": "error", "log": "Queue not initialized"}
                return jsonify(ret)
            elif sub == "add_queue_checked_list":
                return jsonify({"ret": "not_implemented"})
            elif sub == "web_list":
                return jsonify({"ret": "not_implemented"})
            elif sub == "db_remove":
                return jsonify({"ret": "not_implemented"})
            elif sub == "add_whitelist":
                return jsonify({"ret": "not_implemented"})
            elif sub == "command":
                # command = queue_command와 동일
                cmd = request.form.get("cmd", "")
                entity_id = request.form.get("entity_id", "")
                
                logger.debug(f"command endpoint - cmd: {cmd}, entity_id: {entity_id}")
                
                # list 명령 처리
                if cmd == "list":
                    if self.queue:
                        return jsonify(self.queue.get_entity_list())
                    else:
                        return jsonify([])
                
                # 기타 명령 처리
                if self.queue:
                    ret = self.queue.command(cmd, int(entity_id) if entity_id else 0)
                    if ret is None:
                        ret = {"ret": "success"}
                else:
                    ret = {"ret": "error", "log": "Queue not initialized"}
                return jsonify(ret)
            
            # 매치되는 sub가 없는 경우 기본 응답
            return jsonify({"ret": "error", "log": f"Unknown sub: {sub}"})

        except Exception as e:
            P.logger.error(f"Exception: {str(e)}")
            P.logger.error(traceback.format_exc())
            return jsonify({"ret": "error", "log": str(e)})

    def process_command(self, command, arg1, arg2, arg3, req):
        """
        FlaskFarm 프레임워크가 /command 엔드포인트에서 호출하는 함수
        queue 페이지에서 list, stop 등의 명령을 처리
        """
        ret = {"ret": "success"}
        logger.debug(f"process_command - command: {command}, arg1: {arg1}")
        
        if command == "list":
            # 큐 목록 반환
            if self.queue:
                ret = [x for x in self.queue.get_entity_list()]
            else:
                ret = []
            return jsonify(ret)
        
        elif command == "stop":
            # 다운로드 중지
            if self.queue and arg1:
                try:
                    entity_id = int(arg1)
                    result = self.queue.command("stop", entity_id)
                    if result:
                        ret = result
                except Exception as e:
                    ret = {"ret": "error", "log": str(e)}
            return jsonify(ret)
        
        elif command == "queue_list":
            # 대기 큐 목록
            if self.queue:
                ret = [x for x in self.queue.get_entity_list()]
            else:
                ret = []
            return jsonify(ret)
        
        # 기본 응답
        return jsonify(ret)

    def socketio_callback(self, refresh_type, data):
        """
        socketio를 통해 클라이언트에 상태 업데이트 전송
        refresh_type: 'add', 'status', 'last' 등
        data: entity.as_dict() 데이터
        """
        logger.info(f">>> socketio_callback called: {refresh_type}, {data.get('percent', 'N/A')}%")
        try:
            from flaskfarm.lib.framework.init_main import socketio
            
            # FlaskFarm의 기존 패턴: /framework namespace로 emit
            # queue 페이지의 소켓이 이 메시지를 받아서 처리
            namespace = f"/{P.package_name}/{self.name}/queue"
            
            # 먼저 queue에 직접 emit (기존 방식)
            socketio.emit(refresh_type, data, namespace=namespace)
            
            # /framework namespace로도 notify 이벤트 전송
            notify_data = {
                "type": "success",
                "msg": f"다운로드중 {data.get('percent', 0)}% - {data.get('filename', '')}",
            }
            socketio.emit("notify", notify_data, namespace="/framework")
            logger.info(f">>> socketio.emit completed to /framework")
                
        except Exception as e:
            logger.error(f"socketio_callback error: {e}")

    @staticmethod
    def get_html(url, cached=False):
        try:
            if LogicLinkkf.referer is None:
                LogicLinkkf.referer = f"{ModelSetting.get('linkkf_url')}"

            # return LogicLinkkfYommi.get_html_requests(url)
            return LogicLinkkf.get_html_cloudflare(url)

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_html_cloudflare(url, cached=False):
        logger.debug(f"cloudflare protection bypass {'=' * 30}")

        user_agents_list = [
            "Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.83 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36",
        ]
        # ua = UserAgent(verify_ssl=False)

        LogicLinkkf.headers["User-Agent"] = random.choice(user_agents_list)

        LogicLinkkf.headers["Referer"] = LogicLinkkf.referer

        # logger.debug(f"headers:: {LogicLinkkfYommi.headers}")

        if LogicLinkkf.session is None:
            LogicLinkkf.session = requests.Session()

        # LogicLinkkfYommi.session = requests.Session()
        # re_sess = requests.Session()
        # logger.debug(LogicLinkkfYommi.session)

        # sess = cloudscraper.create_scraper(
        #     # browser={"browser": "firefox", "mobile": False},
        #     browser={"browser": "chrome", "mobile": False},
        #     debug=True,
        #     sess=LogicLinkkfYommi.session,
        #     delay=10,
        # )
        # scraper = cloudscraper.create_scraper(sess=re_sess)
        scraper = cloudscraper.create_scraper(
            # debug=True,
            delay=10,
            sess=LogicLinkkf.session,
            browser={
                "custom": "linkkf",
            },
        )

        # print(scraper.get(url, headers=LogicLinkkfYommi.headers).content)
        # print(scraper.get(url).content)
        # return scraper.get(url, headers=LogicLinkkfYommi.headers).content
        # logger.debug(LogicLinkkfYommi.headers)
        return scraper.get(
            url,
            headers=LogicLinkkf.headers,
            timeout=10,
        ).content.decode("utf8", errors="replace")

    @staticmethod
    def add_whitelist(*args):
        ret = {}

        logger.debug(f"args: {args}")
        try:
            if len(args) == 0:
                code = str(LogicLinkkf.current_data["code"])
            else:
                code = str(args[0])

            print(code)

            whitelist_program = P.ModelSetting.get("linkkf_auto_code_list")
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
                    .filter_by(key="linkkf_auto_code_list")
                    .with_for_update()
                    .first()
                )
                entity.value = whitelist_program
                db.session.commit()
                ret["ret"] = True
                ret["code"] = code
                if len(args) == 0:
                    return LogicLinkkf.current_data
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

    def setting_save_after(self, change_list=None):
        if self.queue.get_max_ffmpeg_count() != P.ModelSetting.get_int(
            "linkkf_max_ffmpeg_process_count"
        ):
            self.queue.set_max_ffmpeg_count(
                P.ModelSetting.get_int("linkkf_max_ffmpeg_process_count")
            )

    @staticmethod
    def extract_video_url_from_playid(playid_url):
        """
        linkkf.live의 playid URL에서 실제 비디오 URL(m3u8)을 추출합니다.
        
        예시:
        - playid_url: https://linkkf.live/playid/403116/?server=12&slug=11
        - iframe: https://play.sub3.top/r2/play.php?id=n8&url=403116s11
        - m3u8: https://n8.hlz3.top/403116s11/index.m3u8
        """
        video_url = None
        referer_url = None
        
        try:
            logger.info(f"Extracting video URL from: {playid_url}")
            
            # Step 1: playid 페이지에서 iframe src 추출
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://linkkf.live/"
            }
            
            response = requests.get(playid_url, headers=headers, timeout=15)
            html_content = response.text
            
            soup = BeautifulSoup(html_content, "html.parser")
            
            # iframe 찾기 (id="video-player-iframe" 또는 play.sub3.top 포함)
            iframe = soup.select_one("iframe#video-player-iframe")
            if not iframe:
                iframe = soup.select_one("iframe[src*='play.sub']")
            if not iframe:
                iframe = soup.select_one("iframe")
            
            if iframe and iframe.get("src"):
                iframe_src = iframe.get("src")
                logger.info(f"Found iframe: {iframe_src}")
                
                # Step 2: iframe 페이지에서 m3u8 URL 추출
                iframe_headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Referer": playid_url
                }
                
                iframe_response = requests.get(iframe_src, headers=iframe_headers, timeout=15)
                iframe_content = iframe_response.text
                
                # m3u8 URL 패턴 찾기
                # 예: url: 'https://n8.hlz3.top/403116s11/index.m3u8'
                m3u8_pattern = re.compile(r"url:\s*['\"]([^'\"]*\.m3u8)['\"]")
                m3u8_match = m3u8_pattern.search(iframe_content)
                
                if m3u8_match:
                    video_url = m3u8_match.group(1)
                    logger.info(f"Found m3u8 URL: {video_url}")
                else:
                    # 대안 패턴: source src
                    source_pattern = re.compile(r"<source[^>]+src=['\"]([^'\"]+)['\"]")
                    source_match = source_pattern.search(iframe_content)
                    if source_match:
                        video_url = source_match.group(1)
                        logger.info(f"Found source URL: {video_url}")
                
                referer_url = iframe_src
            else:
                logger.warning("No iframe found in playid page")
                
        except Exception as e:
            logger.error(f"Error extracting video URL: {e}")
            logger.error(traceback.format_exc())
        
        return video_url, referer_url

    def get_video_url_from_url(url, url2):
        video_url = None
        referer_url = None
        vtt_url = None
        LogicLinkkf.referer = url2
        # logger.info("dx download url : %s , url2 : %s" % (url, url2))
        # logger.debug(LogicLinkkfYommi.referer)

        try:
            if "ani1" in url2:
                # kfani 계열 처리 => 방문해서 m3u8을 받아온다.
                logger.debug("ani1 routine=========================")
                LogicLinkkf.referer = "https://linkkf.app"
                # logger.debug(f"url2: {url2}")
                ani1_html = LogicLinkkf.get_html(url2)

                tree = html.fromstring(ani1_html)
                option_url = tree.xpath("//select[@id='server-list']/option[1]/@value")

                # logger.debug(f"option_url:: {option_url}")

                data = LogicLinkkf.get_html(option_url[0])
                # print(type(data))
                regex2 = r'"([^\"]*m3u8)"|<source[^>]+src=\"([^"]+)'

                temp_url = re.findall(regex2, data)[0]
                video_url = ""
                ref = "https://ani1.app"
                for i in temp_url:
                    if i is None:
                        continue
                    video_url = i
                    # video_url = '{1} -headers \'Referer: "{0}"\' -user_agent "Mozilla/5.0 (Windows NT 10.0; Win64;
                    # x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3554.0 Safari/537.36"'.format(ref,
                    # video_url)

                data_tree = html.fromstring(data)
                # print(data_tree.xpath("//video/source/@src"))
                vtt_elem = data_tree.xpath("//track/@src")[0]
                # vtt_elem = data_tree.xpath("//*[contains(@src, '.vtt']")[0]

                # print(vtt_elem)

                match = re.compile(
                    r"<track.+src=\"(?P<vtt_url>.*?.vtt)\"", re.MULTILINE
                ).search(data)

                vtt_url = match.group("vtt_url")

                referer_url = "https://kfani.me/"

            elif "kfani" in url2:
                # kfani 계열 처리 => 방문해서 m3u8을 받아온다.
                logger.debug("kfani routine=================================")
                LogicLinkkf.referer = url2
                # logger.debug(f"url2: {url2}")
                data = LogicLinkkf.get_html(url2)
                # logger.info("dx: data", data)
                regex2 = r'"([^\"]*m3u8)"|<source[^>]+src=\"([^"]+)'

                temp_url = re.findall(regex2, data)[0]
                video_url = ""
                ref = "https://kfani.me"
                for i in temp_url:
                    if i is None:
                        continue
                    video_url = i
                    # video_url = '{1} -headers \'Referer: "{0}"\' -user_agent "Mozilla/5.0 (Windows NT 10.0; Win64;
                    # x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3554.0 Safari/537.36"'.format(ref,
                    # video_url)

                # @k45734
                vtt_url = None
                try:
                    _match1 = re.compile(
                        r"<track.+src=\"(?P<vtt_url>.*?.vtt)", re.MULTILINE
                    ).search(data)
                    vtt_url = _match1.group("vtt_url")
                except:
                    _match2 = re.compile(
                        r"url: \'(?P<vtt_url>.*?.vtt)", re.MULTILINE
                    ).search(data)
                    vtt_url = _match2.group("vtt_url")

                logger.info("vtt_url: %s", vtt_url)

                referer_url = url2

            elif "kftv" in url2:
                # kftv 계열 처리 => url의 id로 https://yt.kftv.live/getLinkStreamMd5/df6960891d226e24b117b850b44a2290 페이지
                # 접속해서 json 받아오고, json에서 url을 추출해야함
                if "=" in url2:
                    md5 = urlparse.urlparse(url2).query.split("=")[1]
                elif "embedplay" in url2:
                    md5 = url2.split("/")[-1]
                url3 = "https://yt.kftv.live/getLinkStreamMd5/" + md5
                # logger.info("download url : %s , url3 : %s" % (url, url3))
                data3 = LogicLinkkf.get_html(url3)
                data3dict = json.loads(data3)
                # print(data3dict)
                video_url = data3dict[0]["file"]

            elif "k40chan" in url2:
                # k40chan 계열 처리 => 방문해서 m3u8을 받아온다.
                # k45734 님 소스 반영 (확인은 안해봄 잘 동작할꺼라고 믿고,)
                logger.debug("k40chan routine=================================")
                LogicLinkkf.referer = url2
                data = LogicLinkkf.get_html(url2)

                regex2 = r'"([^\"]*m3u8)"|<source[^>]+src=\"([^"]+)'

                temp_url = re.findall(regex2, data)[0]
                video_url = ""
                # ref = "https://kfani.me"
                for i in temp_url:
                    if i is None:
                        continue
                    video_url = i

                match = re.compile(r"<track.+src\=\"(?P<vtt_url>.*?.vtt)").search(data)
                vtt_url = match.group("vtt_url")

                referer_url = url2

            elif "linkkf" in url2:
                logger.deubg("linkkf routine")
                # linkkf 계열 처리 => URL 리스트를 받아오고, 하나 골라 방문 해서 m3u8을 받아온다.
                referer_url = url2
                data2 = LogicLinkkf.get_html(url2)
                # print(data2)
                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                # logger.info("cat: %s", cat)
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("url3: %s", url3)
                # logger.info("download url : %s , url3 : %s" % (url, url3))
                if "kftv" in url3:
                    return LogicLinkkf.get_video_url_from_url(url2, url3)
                elif url3.startswith("/"):
                    url3 = urlparse.urljoin(url2, url3)
                    print("url3 = ", url3)
                    LogicLinkkf.referer = url2
                    data3 = LogicLinkkf.get_html(url3)
                    # logger.info('data3: %s', data3)
                    # regex2 = r'"([^\"]*m3u8)"'
                    regex2 = r'"([^\"]*mp4|m3u8)"'
                    video_url = re.findall(regex2, data3)[0]
                    # logger.info('video_url: %s', video_url)
                    referer_url = url3

                else:
                    logger.error("새로운 유형의 url 발생! %s %s %s" % (url, url2, url3))
            elif "kakao" in url2:
                # kakao 계열 처리, 외부 API 이용
                payload = {"inputUrl": url2}
                kakao_url = (
                    "http://webtool.cusis.net/wp-pages/download-kakaotv-video/video.php"
                )
                data2 = requests.post(
                    kakao_url,
                    json=payload,
                    headers={
                        "referer": "http://webtool.cusis.net/download-kakaotv-video/"
                    },
                ).content
                time.sleep(
                    3
                )  # 서버 부하 방지를 위해 단시간에 너무 많은 URL전송을 하면 IP를 차단합니다.
                url3 = json.loads(data2)
                # logger.info("download url2 : %s , url3 : %s" % (url2, url3))
                video_url = url3
            elif "#V" in url2:  # V 패턴 추가
                print("#v routine")

                data2 = LogicLinkkf.get_html(url2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))
                if "kftv" in url3:
                    return LogicLinkkf.get_video_url_from_url(url2, url3)
                elif url3.startswith("/"):
                    url3 = urlparse.urljoin(url2, url3)
                    LogicLinkkf.referer = url2
                    data3 = LogicLinkkf.get_html(url3)

                    regex2 = r'"([^\"]*mp4)"'
                    video_url = re.findall(regex2, data3)[0]
                else:
                    logger.error("새로운 유형의 url 발생! %s %s %s" % (url, url2, url3))

            elif "#M2" in url2:
                LogicLinkkf.referer = url2
                data2 = LogicLinkkf.get_html(url2)
                # print(data2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))
                if "kftv" in url3:
                    return LogicLinkkf.get_video_url_from_url(url2, url3)
                elif url3.startswith("/"):
                    url3 = urlparse.urljoin(url2, url3)
                    LogicLinkkf.referer = url2
                    data3 = LogicLinkkf.get_html(url3)
                    # print("내용: %s", data3)
                    # logger.info("movie content: %s", data3)
                    # regex2 = r'"([^\"]*m3u8)"'
                    regex2 = r'"([^\"]*mp4)"'
                    video_url = re.findall(regex2, data3)[0]
                else:
                    logger.error("새로운 유형의 url 발생! %s %s %s" % (url, url2, url3))
            elif "😀#i" in url2:
                LogicLinkkf.referer = url2
                data2 = LogicLinkkf.get_html(url2)
                # logger.info(data2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))

            elif "#k" in url2:
                data2 = LogicLinkkf.get_html(url2)
                # logger.info(data2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))

            elif "#k2" in url2:
                data2 = LogicLinkkf.get_html(url2)
                # logger.info(data2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))
            elif "mopipi" in url2:
                LogicLinkkf.referer = url
                data2 = LogicLinkkf.get_html(url2)
                # logger.info(data2)
                match = re.compile(r"src\=\"(?P<video_url>http.*?\.mp4)").search(data2)
                video_url = match.group("video_url")

                match = re.compile(r"src\=\"(?P<vtt_url>http.*?.vtt)").search(data2)
                logger.info("match group: %s", match.group("video_url"))
                vtt_url = match.group("vtt_url")

                # logger.info("download url : %s , url3 : %s" % (url, url3))

            else:
                logger.error("새로운 유형의 url 발생! %s %s" % (url, url2))
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

        return [video_url, referer_url, vtt_url]

    @staticmethod
    def get_html_episode_content(url: str) -> str:
        if url.startswith("http"):
            html_data = LogicLinkkf.get_html(url)
        else:
            url = f"https://linkkf.app{url}"

            logger.info("get_video_url(): url: %s" % url)
            data = LogicLinkkf.get_html(url)

            tree = html.fromstring(data)

            tree = html.fromstring(data)

            pattern = re.compile("var player_data=(.*)")

            js_scripts = tree.xpath("//script")

            iframe_info = None
            index = 0

            for js_script in js_scripts:
                # print(f"{index}.. {js_script.text_content()}")
                if pattern.match(js_script.text_content()):
                    # logger.debug("match::::")
                    match_data = pattern.match(js_script.text_content())
                    iframe_info = json.loads(
                        match_data.groups()[0].replace("path:", '"path":')
                    )
                    # logger.debug(f"iframe_info:: {iframe_info}")

                index += 1

            ##################################################
            # iframe url:: https://s2.ani1c12.top/player/index.php?data='+player_data.url+'
            ####################################################

            url = f"https://s2.ani1c12.top/player/index.php?data={iframe_info['url']}"
            html_data = LogicLinkkf.get_html(url)

        return html_data

    def get_anime_info(self, cate, page):
        try:
            items_xpath = '//div[@class="ext-json-item"]'
            title_xpath = ""

            if cate == "ing":
                # url = f"{P.ModelSetting.get('linkkf_url')}/airing/page/{page}"
                url = "https://linkkf.5imgdarr.top/api/singlefilter.php?categorytagid=1970&page=1&limit=20"
                items_xpath = '//div[@class="ext-json-item"]'
                title_xpath = './/a[@class="text-fff"]//text()'
            elif cate == "movie":
                url = f"{P.ModelSetting.get('linkkf_url')}/ani/page/{page}"
                items_xpath = '//div[@class="myui-vodlist__box"]'
                title_xpath = './/a[@class="text-fff"]//text()'
            elif cate == "complete":
                url = f"{P.ModelSetting.get('linkkf_url')}/anime-list/page/{page}"
                items_xpath = '//div[@class="myui-vodlist__box"]'
                title_xpath = './/a[@class="text-fff"]//text()'
            elif cate == "top_view":
                url = f"{P.ModelSetting.get('linkkf_url')}/topview/page/{page}"
                items_xpath = '//div[@class="ext-json-item"]'
                title_xpath = './/a[@class="text-fff"]//text()'
            else:
                url = "https://linkkf.5imgdarr.top/api/singlefilter.php?categorytagid=1970&page=1&limit=20"

            logger.info("url:::> %s", url)
            logger.info("test..........................")
            # logger.info("test..........................")
            if self.referer is None:
                self.referer = "https://linkkf.live"

            data = {"ret": "success", "page": page}
            response_data = LogicLinkkf.get_html(url, timeout=10)
            # P.logger.debug(response_data)
            P.logger.debug("debug.....................")
            # P.logger.debug(response_data)

            # JSON 응답인지 확인
            try:
                json_data = json.loads(response_data)
                P.logger.debug("Response is JSON format")
                P.logger.debug(json_data)
                # JSON 데이터를 그대로 반환하거나 필요한 형태로 가공
                if isinstance(json_data, dict):
                    return json_data
                else:
                    data["episode"] = json_data if isinstance(json_data, list) else []
                    return data
            except (json.JSONDecodeError, ValueError):
                # HTML 응답인 경우
                P.logger.debug("Response is HTML format, parsing...")
                pass

            tree = html.fromstring(response_data)
            tmp_items = tree.xpath(items_xpath)

            if tree.xpath('//div[@id="wp_page"]//text()'):
                data["total_page"] = tree.xpath('//div[@id="wp_page"]//text()')[-1]
            else:
                data["total_page"] = 0
            data["episode_count"] = len(tmp_items)
            data["episode"] = []

            for item in tmp_items:
                entity = dict()
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["code"] = re.search(r"[0-9]+", entity["link"]).group()
                entity["title"] = item.xpath(title_xpath)[0].strip()
                entity["image_link"] = item.xpath("./a/@data-original")[0]
                entity["chapter"] = (
                    item.xpath("./a/span//text()")[0].strip()
                    if len(item.xpath("./a/span//text()")) > 0
                    else ""
                )
                # logger.info('entity:::', entity['title'])
                data["episode"].append(entity)

            # logger.debug(data)

            return data
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    def get_search_result(self, query, page, cate):
        try:
            _query = urllib.parse.quote(query)
            url = f"{P.ModelSetting.get('linkkf_url')}/search/-------------.html?wd={_query}&page={page}"

            logger.info("get_search_result()::url> %s", url)
            data = {"ret": "success", "page": page}
            response_data = LogicLinkkf.get_html(url, timeout=10)
            tree = html.fromstring(response_data)

            # linkkf 검색 결과는 일반 목록과 동일한 구조
            tmp_items = tree.xpath('//div[@class="myui-vodlist__box"]')

            data["episode_count"] = len(tmp_items)
            data["episode"] = []

            if tree.xpath('//div[@id="wp_page"]//text()'):
                data["total_page"] = tree.xpath('//div[@id="wp_page"]//text()')[-1]
            else:
                data["total_page"] = 0

            for item in tmp_items:
                entity = {}
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["code"] = re.search(r"[0-9]+", entity["link"]).group()
                entity["title"] = item.xpath('.//a[@class="text-fff"]//text()')[
                    0
                ].strip()
                entity["image_link"] = item.xpath("./a/@data-original")[0]
                entity["chapter"] = (
                    item.xpath("./a/span//text()")[0].strip()
                    if len(item.xpath("./a/span//text()")) > 0
                    else ""
                )
                data["episode"].append(entity)

            return data
        except Exception as e:
            P.logger.error(f"Exception: {str(e)}")
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    def get_series_info(self, code):
        data = {"code": code, "ret": False}
        try:
            # 이전 데이터가 있다면, 리턴 (# If you have previous data, return)
            if (
                LogicLinkkf.current_data is not None
                and LogicLinkkf.current_data["code"] == code
                and LogicLinkkf.current_data["ret"]
            ):
                return LogicLinkkf.current_data
            
            url = "%s/%s/" % (P.ModelSetting.get("linkkf_url"), code)
            
            logger.info(f"get_series_info URL: {url}")

            html_content = LogicLinkkf.get_html(url, cached=False)
            
            if not html_content:
                data["log"] = "Failed to fetch page content"
                data["ret"] = "error"
                return data

            soup = BeautifulSoup(html_content, "html.parser")
            
            # === 제목 추출 ===
            # 방법 1: #anime-details > h3 (가장 정확)
            title_elem = soup.select_one("#anime-details > h3")
            if not title_elem:
                # 방법 2: .anime-tab-content > h3
                title_elem = soup.select_one(".anime-tab-content > h3")
            
            title_text = ""
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                # "11/12 - 너와 넘어 사랑이 된다" 형식에서 제목만 추출
                if " - " in title_text:
                    data["title"] = title_text.split(" - ", 1)[1]
                else:
                    data["title"] = title_text
            else:
                # 방법 3: gemini-dark-card__link의 title 속성
                card_link = soup.select_one("a.gemini-dark-card__link")
                if card_link and card_link.get("title"):
                    data["title"] = card_link.get("title")
                else:
                    # 방법 4: 포스터 이미지의 alt 속성
                    poster_img = soup.select_one("img.gemini-dark-card__image")
                    if poster_img and poster_img.get("alt"):
                        data["title"] = poster_img.get("alt")
                    else:
                        # 방법 5: 페이지 title에서 추출
                        page_title = soup.select_one("title")
                        if page_title:
                            title_text = page_title.get_text(strip=True)
                            # "제목 자막 / 더빙 / Linkkf" 형식 처리
                            data["title"] = title_text.split(" 자막")[0].split(" /")[0].strip()
                        else:
                            data["title"] = f"Unknown-{code}"
            
            # 제목 정리
            data["title"] = Util.change_text_for_use_filename(data["title"]).strip()
            data["_id"] = str(code)
            
            # === 시즌 추출 ===
            match = re.compile(r"(?P<season>\d+)기").search(data.get("title", ""))
            if match:
                data["season"] = match.group("season")
                data["title"] = data["title"].replace(data["season"] + "기", "").strip()
            else:
                data["season"] = "1"
            
            # === 포스터 이미지 ===
            poster_elem = soup.select_one("img.gemini-dark-card__image")
            if poster_elem:
                # lazy loading 대응: data-lazy-src (사이트에서 사용하는 속성), data-src, src 순서로 확인
                data["poster_url"] = (
                    poster_elem.get("data-lazy-src") or 
                    poster_elem.get("data-src") or 
                    poster_elem.get("src") or ""
                )
                # placeholder SVG 제외
                if data["poster_url"].startswith("data:image/svg"):
                    data["poster_url"] = poster_elem.get("data-lazy-src") or poster_elem.get("data-src") or ""
            else:
                # 대안 선택자
                poster_alt = soup.select_one("a.gemini-dark-card__link img")
                if poster_alt:
                    data["poster_url"] = (
                        poster_alt.get("data-lazy-src") or 
                        poster_alt.get("data-src") or 
                        poster_alt.get("src") or ""
                    )
                else:
                    data["poster_url"] = None
            
            # === 상세 정보 ===
            data["detail"] = []
            info_items = soup.select("li")
            for item in info_items:
                text = item.get_text(strip=True)
                if any(keyword in text for keyword in ["방영일", "제작사", "장르", "분류", "년"]):
                    data["detail"].append({"info": text})
            
            if not data["detail"]:
                data["detail"] = [{"정보없음": ""}]
            
            # === 에피소드 목록 - API에서 가져오기 ===
            data["episode"] = []
            data["save_folder"] = data["title"]
            
            # 에피소드 API 호출
            episode_api_url = f"https://linkkfep.5imgdarr.top/api2.php?epid={code}"
            try:
                episode_response = requests.get(episode_api_url, timeout=10)
                episode_data = episode_response.json()
                
                logger.debug(f"Episode API response: {len(episode_data)} servers found")
                
                # 첫 번째 서버 (보통 자막-S)의 에피소드 목록 사용
                if episode_data and len(episode_data) > 0:
                    server_data = episode_data[0].get("server_data", [])
                    # 역순 정렬 (최신 에피소드가 위로)
                    server_data = list(reversed(server_data))
                    
                    for idx, ep_info in enumerate(server_data):
                        ep_name = ep_info.get("name", str(idx + 1))
                        ep_slug = ep_info.get("slug", str(idx + 1))
                        ep_link = ep_info.get("link", "")
                        
                        # 화면 표시용 title은 "01화" 형태
                        ep_title = f"{ep_name}화"
                        
                        # 에피소드별 고유 ID 생성 (프로그램코드 + 에피소드번호)
                        episode_unique_id = data["code"] + ep_name.zfill(4)
                        
                        entity = {
                            "_id": episode_unique_id,  # 에피소드별 고유 ID
                            "program_code": data["code"],
                            "program_title": data["title"],
                            "save_folder": Util.change_text_for_use_filename(data["save_folder"]),
                            "title": ep_title,
                            "season": data["season"],
                        }
                        
                        # 에피소드 코드 = _id와 동일
                        entity["code"] = episode_unique_id
                        
                        # URL 생성: playid/{code}/?server=12&slug={slug} 형태
                        entity["url"] = f"https://linkkf.live/playid/{code}/?server=12&slug={ep_slug}"
                        
                        # 저장 경로 설정
                        tmp_save_path = P.ModelSetting.get("linkkf_download_path")
                        if not tmp_save_path:
                            tmp_save_path = "/tmp/anime_downloads"
                            
                        if P.ModelSetting.get("linkkf_auto_make_folder") == "True":
                            program_path = os.path.join(tmp_save_path, entity["save_folder"])
                            entity["save_path"] = program_path
                            if P.ModelSetting.get("linkkf_auto_make_season_folder"):
                                entity["save_path"] = os.path.join(
                                    entity["save_path"], "Season %s" % int(entity["season"])
                                )
                        else:
                            # 기본 경로 설정
                            entity["save_path"] = tmp_save_path
                        
                        entity["image"] = data["poster_url"]
                        # filename 생성 시 숫자만 전달 ("01화" 아님)
                        entity["filename"] = LogicLinkkf.get_filename(
                            data["save_folder"], data["season"], ep_name
                        )
                        
                        data["episode"].append(entity)
                        
            except Exception as ep_error:
                logger.error(f"Episode API error: {ep_error}")
                logger.error(traceback.format_exc())
            
            data["episode_count"] = str(len(data["episode"]))
            data["ret"] = True
            self.current_data = data
            
            logger.info(f"Parsed series: {data['title']}, Episodes: {data['episode_count']}")
            return data

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            data["log"] = str(e)
            data["ret"] = "error"
            return data

    def get_screen_movie_info(self, page):
        try:
            url = f"{P.ModelSetting.get('linkkf_url')}/ani/page/{page}"

            html_content = self.get_html_requests(url, cached=True)
            # html_content = LogicLinkkfYommi.get_html_cloudflare(url, cached=False)
            download_path = P.ModelSetting.get("linkkf_download_path")
            tree = html.fromstring(html_content)
            tmp_items = tree.xpath('//div[@class="myui-vodlist__box"]')
            title_xpath = './/a[@class="text-fff"]//text()'
            # logger.info('tmp_items:::', tmp_items)
            data = dict()
            data = {"ret": "success", "page": page}

            data["episode_count"] = len(tmp_items)
            data["episode"] = []

            for item in tmp_items:
                entity = dict()
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["code"] = re.search(r"[0-9]+", entity["link"]).group()
                entity["title"] = item.xpath(title_xpath)[0].strip()
                if len(item.xpath("./a/@style")) > 0:
                    print(
                        re.search(
                            r"url\(((http|https|ftp|ftps)\:\/\/[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,3}(\/\S*)?)\)",
                            item.xpath("./a/@style")[0],
                        ).group()
                    )

                if item.xpath(".//a/@data-original"):
                    entity["image_link"] = item.xpath(".//a/@data-original")[0]

                else:
                    entity["image_link"] = ""
                # entity["image_link"] = item.xpath("./a/@data-original")[0]
                entity["chapter"] = (
                    item.xpath("./a/span//text()")[0]
                    if len(item.xpath("./a/span//text()")) > 0
                    else ""
                )
                # logger.info('entity:::', entity['title'])
                data["episode"].append(entity)

            # json_file_path = os.path.join(download_path, "airing_list.json")
            # logger.debug("json_file_path:: %s", json_file_path)
            #
            # with open(json_file_path, "w") as outfile:
            #     json.dump(data, outfile)

            return data

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_html(
        url: str,
        referer: str = None,
        cached: bool = False,
        stream: bool = False,
        timeout: int = 5,
    ):
        data = ""
        headers = {
            "referer": "https://linkkf.live",
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

    def get_html_requests(self, url, cached=False):
        if LogicLinkkf.session is None:
            if cached:
                logger.debug("cached===========++++++++++++")

                LogicLinkkf.session = CachedSession(
                    os.path.join(self.cache_path, "linkkf_cache"),
                    backend="sqlite",
                    expire_after=300,
                    cache_control=True,
                )
                # print(f"{cache_path}")
                # print(f"cache_path:: {LogicLinkkfYommi.session.cache}")
            else:
                LogicLinkkf.session = requests.Session()

        LogicLinkkf.referer = "https://linkkf.live"

        LogicLinkkf.headers["Referer"] = LogicLinkkf.referer

        # logger.debug(
        #     f"get_html()::LogicLinkkfYommi.referer = {LogicLinkkfYommi.referer}"
        # )
        page = LogicLinkkf.session.get(url, headers=LogicLinkkf.headers)
        # logger.info(f"page: {page}")

        return page.content.decode("utf8", errors="replace")

    @staticmethod
    def get_filename(maintitle, season, title):
        try:
            # logger.debug("get_filename()===")
            # logger.info("title:: %s", title)
            # logger.info("maintitle:: %s", maintitle)
            match = re.compile(
                r"(?P<title>.*?)\s?((?P<season>\d+)기)?\s?((?P<epi_no>\d+)화?)"
            ).search(title)
            if match:
                epi_no = int(match.group("epi_no"))
                if epi_no < 10:
                    epi_no = "0%s" % epi_no
                else:
                    epi_no = "%s" % epi_no

                if int(season) < 10:
                    season = "0%s" % season
                else:
                    season = "%s" % season

                # title_part = match.group('title').strip()
                # ret = '%s.S%sE%s%s.720p-SA.mp4' % (maintitle, season, epi_no, date_str)
                ret = "%s.S%sE%s.720p-LK.mp4" % (maintitle, season, epi_no)
            else:
                logger.debug("NOT MATCH")
                ret = "%s.720p-SA.mp4" % maintitle

            return Util.change_text_for_use_filename(ret)
        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())

    def add(self, episode_info):
        # 큐가 초기화되지 않았으면 초기화
        if self.queue is None:
            logger.warning("Queue is None in add(), initializing...")
            try:
                self.queue = FfmpegQueue(
                    P, P.ModelSetting.get_int("linkkf_max_ffmpeg_process_count"), "linkkf", caller=self
                )
                self.queue.queue_start()
            except Exception as e:
                logger.error(f"Failed to initialize queue: {e}")
                return "queue_init_error"
        
        # 큐 상태 로깅
        queue_len = len(self.queue.entity_list) if self.queue else 0
        logger.info(f"add() called - Queue length: {queue_len}, episode _id: {episode_info.get('_id')}")
        
        if self.is_exist(episode_info):
            logger.info(f"is_exist returned True for _id: {episode_info.get('_id')}")
            return "queue_exist"
        else:
            db_entity = ModelLinkkfItem.get_by_linkkf_id(episode_info["_id"])
            logger.info(f"db_entity: {db_entity}")

            logger.debug("db_entity:::> %s", db_entity)
            # logger.debug("db_entity.status ::: %s", db_entity.status)
            if db_entity is None:
                entity = LinkkfQueueEntity(P, self, episode_info)
                logger.debug("entity:::> %s", entity.as_dict())
                ModelLinkkfItem.append(entity.as_dict())
                # # logger.debug("entity:: type >> %s", type(entity))
                #

                self.queue.add_queue(entity)
                # self.download_queue.add_queue(entity)

                # P.logger.debug(F.config['path_data'])
                # P.logger.debug(self.headers)

                # filename = os.path.basename(entity.filepath)
                # ffmpeg = SupportFfmpeg(entity.url, entity.filename, callback_function=self.callback_function,
                #                        max_pf_count=0,
                #                        save_path=entity.savepath, timeout_minute=60, headers=self.headers)
                # ret = {'ret': 'success'}
                # ret['json'] = ffmpeg.start()
                return "enqueue_db_append"
            elif db_entity.get("status") != "completed" if isinstance(db_entity, dict) else db_entity.status != "completed":
                # DB에 있지만 완료되지 않은 경우도 큐에 추가
                status = db_entity.get("status") if isinstance(db_entity, dict) else db_entity.status
                logger.info(f"db_entity status: {status}, adding to queue")
                
                try:
                    logger.info("Creating LinkkfQueueEntity...")
                    entity = LinkkfQueueEntity(P, self, episode_info)
                    logger.info(f"LinkkfQueueEntity created, url: {entity.url}, filepath: {entity.filepath}")
                    logger.debug("entity:::> %s", entity.as_dict())
                    
                    logger.info(f"Adding to queue, queue length before: {len(self.queue.entity_list)}")
                    result = self.queue.add_queue(entity)
                    logger.info(f"add_queue result: {result}, queue length after: {len(self.queue.entity_list)}")
                except Exception as e:
                    logger.error(f"Error creating entity or adding to queue: {e}")
                    logger.error(traceback.format_exc())
                    return "entity_creation_error"
                
                return "enqueue_db_exist"
            else:
                return "db_completed"

    # def is_exist(self, info):
    #     print(self.download_queue.entity_list)
    #     for en in self.download_queue.entity_list:
    #         if en.info["_id"] == info["_id"]:
    #             return True

    def is_exist(self, info):
        if self.queue is None:
            return False
            
        for _ in self.queue.entity_list:
            if _.info["_id"] == info["_id"]:
                return True
        return False

    def plugin_load(self):
        try:
            logger.debug("%s plugin_load", P.package_name)
            # old version
            self.queue = FfmpegQueue(
                P, P.ModelSetting.get_int("linkkf_max_ffmpeg_process_count"), "linkkf", caller=self
            )
            self.current_data = None
            self.queue.queue_start()

            # new version Todo:
            # if self.download_queue is None:
            #     self.download_queue = queue.Queue()
            #
            # if self.download_thread is None:
            #     self.download_thread = threading.Thread(target=self.download_thread_function, args=())
            #     self.download_thread.daemon = True
            #     self.download_thread.start()

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    def plugin_unload(self):
        pass

    def download_thread_function(self):
        while True:
            try:
                while True:
                    logger.debug(self.current_download_count)
                    if self.current_download_count < P.ModelSetting.get_int(
                        f"{self.name}_max_download_count"
                    ):
                        break
                    time.sleep(5)

                db_item = self.download_queue.get()
                if db_item.status == "CANCEL":
                    self.download_queue.task_done()
                    continue
                if db_item is None:
                    self.download_queue.task_done()
                    continue

            except Exception as e:
                logger.error(f"Exception: {str(e)}")
                logger.error(traceback.format_exc())


class LinkkfQueueEntity(FfmpegQueueEntity):
    def __init__(self, P, module_logic, info):
        super(LinkkfQueueEntity, self).__init__(P, module_logic, info)
        self._vi = None
        self.epi_queue = None
        self.vtt = None
        self.srt_url = None
        self.headers = None
        
        # info에서 필요한 정보 설정
        playid_url = info.get("url", "")
        self.filename = info.get("filename", "")
        self.quality = info.get("quality", "720p")
        self.season = info.get("season", "1")
        self.content_title = info.get("program_title", "")
        self.savepath = info.get("save_path", "")
        
        # savepath가 비어있으면 기본값 설정
        if not self.savepath:
            default_path = P.ModelSetting.get("linkkf_download_path")
            logger.info(f"[DEBUG] linkkf_download_path from DB: '{default_path}'")
            logger.info(f"[DEBUG] info save_path: '{info.get('save_path', 'NOT SET')}'")
            logger.info(f"[DEBUG] info save_folder: '{info.get('save_folder', 'NOT SET')}'")
            
            if default_path:
                save_folder = info.get("save_folder", "Unknown")
                self.savepath = os.path.join(default_path, save_folder)
            else:
                self.savepath = "/tmp/anime_downloads"
            logger.info(f"[DEBUG] Final savepath set to: '{self.savepath}'")
        
        # filepath = savepath + filename (전체 경로)
        self.filepath = os.path.join(self.savepath, self.filename) if self.filename else self.savepath
        logger.info(f"[DEBUG] filepath set to: '{self.filepath}'")
        
        # playid URL에서 실제 비디오 URL 추출
        try:
            video_url, referer_url = LogicLinkkf.extract_video_url_from_playid(playid_url)
            
            if video_url:
                self.url = video_url
                # HLS 다운로드를 위한 헤더 설정
                self.headers = {
                    "Referer": referer_url or "https://linkkf.live/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                }
                logger.info(f"Video URL extracted: {self.url}")
            else:
                # 추출 실패 시 원본 URL 사용 (fallback)
                self.url = playid_url
                logger.warning(f"Failed to extract video URL, using playid URL: {playid_url}")
        except Exception as e:
            logger.error(f"Exception in video URL extraction: {e}")
            logger.error(traceback.format_exc())
            self.url = playid_url

    def refresh_status(self):
        try:
            # from framework import socketio (FlaskFarm 표준 방식)
            from framework import socketio
            
            data = self.as_dict()
            
            # /framework namespace로 linkkf_status 이벤트 전송
            socketio.emit("linkkf_status", data, namespace="/framework")
            
        except Exception as e:
            logger.error(f"refresh_status error: {e}")

    def info_dict(self, tmp):
        # logger.debug('self.info::> %s', self.info)
        for key, value in self.info.items():
            tmp[key] = value
        tmp["vtt"] = self.vtt
        tmp["season"] = self.season
        tmp["content_title"] = self.content_title
        tmp["linkkf_info"] = self.info
        tmp["epi_queue"] = self.epi_queue
        
        # 템플릿이 기대하는 필드들 추가
        tmp["idx"] = self.entity_id
        tmp["callback_id"] = f"linkkf_{self.entity_id}"
        tmp["start_time"] = self.created_time.strftime("%m-%d %H:%M") if hasattr(self, 'created_time') and self.created_time and hasattr(self.created_time, 'strftime') else (self.created_time if self.created_time else "")
        tmp["status_kor"] = self.ffmpeg_status_kor if self.ffmpeg_status_kor else "대기중"
        tmp["percent"] = self.ffmpeg_percent if self.ffmpeg_percent else 0
        tmp["duration_str"] = ""
        tmp["current_pf_count"] = 0
        tmp["current_speed"] = self.current_speed if hasattr(self, 'current_speed') and self.current_speed else ""
        tmp["download_time"] = self.download_time if hasattr(self, 'download_time') and self.download_time else ""
        tmp["status_str"] = "WAITING" if not self.ffmpeg_status else ("DOWNLOADING" if self.ffmpeg_status == 5 else "COMPLETED" if self.ffmpeg_status == 7 else "WAITING")
        tmp["temp_fullpath"] = ""
        tmp["save_fullpath"] = self.filepath if self.filepath else ""
        tmp["duration"] = ""
        tmp["current_duration"] = ""
        tmp["current_bitrate"] = ""
        tmp["end_time"] = ""
        tmp["max_pf_count"] = 0
        tmp["exist"] = False
        
        return tmp

    def make_episode_info(self):
        url2s = []
        url = None

        try:
            data = LogicLinkkf.get_html_episode_content(self.url)
            tree = html.fromstring(data)

            xpath_select_query = '//*[@id="body"]/div/span/center/select/option'

            if len(tree.xpath(xpath_select_query)) > 0:
                # by k45734
                print("ok")
                xpath_select_query = '//select[@class="switcher"]/option'
                for tag in tree.xpath(xpath_select_query):
                    url2s2 = tag.attrib["value"]
                    if "k40chan" in url2s2:
                        pass
                    elif "ani1c12" in url2s2:
                        pass
                    else:
                        url2s.append(url2s2)
            else:
                print(":: else ::")

                tt = re.search(r"var player_data=(.*?)<", data, re.S)
                json_string = tt.group(1)
                tt2 = re.search(r'"url":"(.*?)"', json_string, re.S)
                json_string2 = tt2.group(1)
                ttt = "https://s2.ani1c12.top/player/index.php?data=" + json_string2
                response = LogicLinkkf.get_html(ttt)
                tree = html.fromstring(response)
                xpath_select_query = '//select[@id="server-list"]/option'
                for tag in tree.xpath(xpath_select_query):
                    url2s2 = tag.attrib["value"]
                    # if 'k40chan' in url2s2:
                    #    pass
                    # elif 'k39aha' in url2s2:
                    if "ds" in url2s2:
                        pass
                    else:
                        url2s.append(url2s2)

                # logger.info('dx: url', url)
                logger.info("dx: urls2:: %s", url2s)

                video_url = None
                referer_url = None  # dx

                for url2 in url2s:
                    try:
                        if video_url is not None:
                            continue
                        # logger.debug(f"url: {url}, url2: {url2}")
                        ret = LogicLinkkf.get_video_url_from_url(url, url2)
                        logger.debug(f"ret::::> {ret}")

                        if ret is not None:
                            video_url = ret
                            referer_url = url2
                    except Exception as e:
                        logger.error("Exception:%s", e)
                        logger.error(traceback.format_exc())

                # logger.info(video_url)
                # return [video_url, referer_url]
                return video_url
            logger.info("dx: urls2:: %s", url2s)

            video_url = None
            referer_url = None  # dx

        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())


class ModelLinkkfItem(db.Model):
    __tablename__ = "{package_name}_linkkf_item".format(package_name=P.package_name)
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
    # linkkf_va = db.Column(db.String)
    linkkf_vi = db.Column(db.String)
    linkkf_id = db.Column(db.String)
    quality = db.Column(db.String)
    filepath = db.Column(db.String)
    filename = db.Column(db.String)
    savepath = db.Column(db.String)
    video_url = db.Column(db.String)
    vtt_url = db.Column(db.String)
    thumbnail = db.Column(db.String)
    status = db.Column(db.String)
    linkkf_info = db.Column(db.JSON)

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
    def get_by_linkkf_id(cls, linkkf_id):
        return db.session.query(cls).filter_by(linkkf_id=linkkf_id).first()

    @classmethod
    def append(cls, q):
        logger.debug(q)
        item = ModelLinkkfItem()
        item.content_code = q["program_code"]
        item.season = q["season"]
        item.episode_no = q["epi_queue"]
        item.title = q["content_title"]
        item.episode_title = q["title"]
        # item.linkkf_va = q["va"]
        item.linkkf_code = q["code"]
        item.linkkf_id = q["_id"]
        item.quality = q["quality"]
        item.filepath = q["filepath"]
        item.filename = q["filename"]
        item.savepath = q["savepath"]
        item.video_url = q["url"]
        item.vtt_url = q["vtt"]
        item.thumbnail = q["image"][0]
        item.status = "wait"
        item.linkkf_info = q["linkkf_info"]
        item.save()
