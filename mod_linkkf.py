#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 3:44 PM
# @Author  : yommi
# @Site    :
# @File    : logic_linkkf
# @Software: PyCharm
import json
import os
import re
import sys
import traceback
from datetime import datetime
import random
import time
import urllib
from urllib.parse import urlparse

import PIL.Image

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

from anime_downloader.lib.ffmpeg_queue_v1 import FfmpegQueueEntity, FfmpegQueue
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
        super(LogicLinkkf, self).__init__(P, "setting", scheduler_desc="linkkf 자동 다운로드")
        self.queue = None
        self.name = name
        self.db_default = {
            "linkkf_db_version": "1",
            "linkkf_url": "https://linkkf.app",
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
            if sub == "request" and req.args.get("content_code") is not None:
                arg["linkkf_current_code"] = req.args.get("content_code")
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
                logger.debug(f"linkkf add_queue routine ===============")
                ret = {}
                info = json.loads(request.form["data"])
                logger.info(f"info:: {info}")
                ret["ret"] = self.add(info)
                return jsonify(ret)
            elif sub == "entity_list":
                pass
            elif sub == "queue_command":
                pass
            elif sub == "add_queue_checked_list":
                pass
            elif sub == "web_list":
                pass
            elif sub == "db_remove":
                pass
            elif sub == "add_whitelist":
                pass

        except Exception as e:
            P.logger.error(f"Exception: {str(e)}")
            P.logger.error(traceback.format_exc())

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

    def setting_save_after(self):
        if self.queue.get_max_ffmpeg_count() != P.ModelSetting.get_int(
            "linkkf_max_ffmpeg_process_count"
        ):
            self.queue.set_max_ffmpeg_count(
                P.ModelSetting.get_int("linkkf_max_ffmpeg_process_count")
            )

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
                time.sleep(3)  # 서버 부하 방지를 위해 단시간에 너무 많은 URL전송을 하면 IP를 차단합니다.
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

            url = f'https://s2.ani1c12.top/player/index.php?data={iframe_info["url"]}'
            html_data = LogicLinkkf.get_html(url)

        return html_data

    def get_anime_info(self, cate, page):
        try:
            if cate == "ing":
                url = f"{P.ModelSetting.get('linkkf_url')}/airing/page/{page}"
                items_xpath = '//div[@class="myui-vodlist__box"]'
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
                items_xpath = '//div[@class="myui-vodlist__box"]'
                title_xpath = './/a[@class="text-fff"]//text()'

            logger.info("url:::> %s", url)
            logger.info("test..........................")
            # logger.info("test..........................")
            if self.referer is None:
                self.referer = "https://linkkf.app"

            data = {"ret": "success", "page": page}
            response_data = LogicLinkkf.get_html(url, timeout=10)
            # P.logger.debug(response_data)
            P.logger.debug("debug.....................")
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
            url = "%s/%s" % (P.ModelSetting.get("linkkf_url"), code)
            logger.info(url)

            logger.debug(LogicLinkkf.headers)
            html_content = LogicLinkkf.get_html(url, cached=False)
            # html_content = LogicLinkkf.get_html_playwright(url)
            # html_content = LogicLinkkf.get_html_cloudflare(url, cached=False)

            sys.setrecursionlimit(10**7)
            # logger.info(html_content)
            tree = html.fromstring(html_content)
            # tree = etree.fromstring(
            #     html_content, parser=etree.XMLParser(huge_tree=True)
            # )
            # tree1 = BeautifulSoup(html_content, "lxml")

            soup = BeautifulSoup(html_content, "html.parser")
            # tree = etree.HTML(str(soup))
            # logger.info(tree)

            tmp2 = soup.select("ul > a")
            if len(tmp2) == 0:
                tmp = soup.select("u > a")
            else:
                tmp = soup.select("ul > a")

            # logger.debug(f"tmp1 size:=> {str(len(tmp))}")

            try:
                tmp = (
                    tree.xpath('//div[@class="hrecipe"]/article/center/strong')[0]
                    .text_content()
                    .strip()
                )
            except IndexError:
                tmp = tree.xpath("//article/center/strong")[0].text_content().strip()

            # logger.info(tmp)
            match = re.compile(r"(?P<season>\d+)기").search(tmp)
            if match:
                data["season"] = match.group("season")
            else:
                data["season"] = "1"

            data["_id"] = str(code)
            data["title"] = tmp.replace(data["season"] + "기", "").strip()
            data["title"] = data["title"].replace("()", "").strip()
            data["title"] = (
                Util.change_text_for_use_filename(data["title"])
                .replace("OVA", "")
                .strip()
            )

            try:
                data["poster_url"] = tree.xpath(
                    '//div[@class="myui-content__thumb"]/a/@data-original'
                )
                # print(tree.xpath('//div[@class="myui-content__detail"]/text()'))
                if len(tree.xpath('//div[@class="myui-content__detail"]/text()')) > 3:
                    data["detail"] = [
                        {
                            "info": str(
                                tree.xpath(
                                    "//div[@class='myui-content__detail']/text()"
                                )[3]
                            )
                        }
                    ]
                else:
                    data["detail"] = [{"정보없음": ""}]
            except Exception as e:
                logger.error(e)
                data["detail"] = [{"정보없음": ""}]
                data["poster_url"] = None

            data["rate"] = tree.xpath('span[@class="tag-score"]')

            tag_score = tree.xpath('//span[@class="taq-score"]')[0].text_content()
            # logger.debug(tag_score)
            tag_count = (
                tree.xpath('//span[contains(@class, "taq-count")]')[0]
                .text_content()
                .strip()
            )
            data_rate = tree.xpath('//div[@class="rating"]/div/@data-rate')

            tmp2 = soup.select("ul > a")
            if len(tmp) == 0:
                tmp = soup.select("u > a")
            else:
                tmp = soup.select("ul > a")

            if tmp is not None:
                data["episode_count"] = str(len(tmp))
            else:
                data["episode_count"] = "0"

            data["episode"] = []
            # tags = tree.xpath(
            #     '//*[@id="syno-nsc-ext-gen3"]/article/div[1]/article/a')
            # tags = tree.xpath("//ul/a")
            tags = soup.select("ul > u > a")
            if len(tags) > 0:
                pass
            else:
                tags = soup.select("ul > a")

            logger.debug(len(tags))

            # logger.info("tags", tags)
            # re1 = re.compile(r'\/(?P<code>\d+)')
            re1 = re.compile(r"\-([^-])+\.")

            data["save_folder"] = data["title"]
            # logger.debug(f"save_folder::> {data['save_folder']}")

            # program = (
            #     db.session.query(ModelLinkkfProgram).filter_by(programcode=code).first()
            # )

            idx = 1
            for t in tags:
                entity = {
                    "_id": data["code"],
                    "program_code": data["code"],
                    "program_title": data["title"],
                    "save_folder": Util.change_text_for_use_filename(
                        data["save_folder"]
                    ),
                    "title": t.text.strip(),
                    # "title": t.text_content().strip(),
                }
                # entity['code'] = re1.search(t.attrib['href']).group('code')

                # logger.debug(f"title ::>{entity['title']}")

                # 고유id임을 알수 없는 말도 안됨..
                # 에피소드 코드가 고유해야 상태값 갱신이 제대로 된 값에 넣어짐
                p = re.compile(r"([0-9]+)화?")
                m_obj = p.match(entity["title"])
                # logger.info(m_obj.group())
                # entity['code'] = data['code'] + '_' +str(idx)

                episode_code = None
                # logger.debug(f"m_obj::> {m_obj}")
                if m_obj is not None:
                    episode_code = m_obj.group(1)
                    entity["code"] = data["code"] + episode_code.zfill(4)
                else:
                    entity["code"] = data["code"]

                aa = t["href"]
                if "/player" in aa:
                    entity["url"] = "https://linkkf.app" + t["href"]
                else:
                    entity["url"] = t["href"]
                entity["season"] = data["season"]

                # 저장 경로 저장
                # Todo: db
                tmp_save_path = P.ModelSetting.get(f"linkkf_download_path")
                if P.ModelSetting.get("linkkf_auto_make_folder") == "True":
                    program_path = os.path.join(tmp_save_path, entity["save_folder"])
                    entity["save_path"] = program_path
                    if P.ModelSetting.get("linkkf_auto_make_season_folder"):
                        entity["save_path"] = os.path.join(
                            entity["save_path"], "Season %s" % int(entity["season"])
                        )

                entity["image"] = data["poster_url"]

                entity["filename"] = LogicLinkkf.get_filename(
                    data["save_folder"], data["season"], entity["title"]
                )
                data["episode"].append(entity)
                idx = idx + 1

            data["ret"] = True
            # logger.info('data', data)
            self.current_data = data

            return data

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            data["log"] = str(e)
            data["ret"] = "error"
            return data
        except IndexError as e:
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
            "referer": f"https://linkkf.app",
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

        LogicLinkkf.referer = "https://linkkf.app"

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
        if self.is_exist(episode_info):
            return "queue_exist"
        else:

            db_entity = ModelLinkkfItem.get_by_linkkf_id(episode_info["_id"])

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
            elif db_entity.status != "completed":
                entity = LinkkfQueueEntity(P, self, episode_info)

                logger.debug("entity:::> %s", entity.as_dict())

                # P.logger.debug(F.config['path_data'])
                # P.logger.debug(self.headers)

                filename = os.path.basename(entity.filepath)
                ffmpeg = SupportFfmpeg(
                    entity.url,
                    entity.filename,
                    callback_function=self.callback_function,
                    max_pf_count=0,
                    save_path=entity.savepath,
                    timeout_minute=60,
                    headers=self.headers,
                )
                ret = {"ret": "success"}
                ret["json"] = ffmpeg.start()

                # self.queue.add_queue(entity)
                return "enqueue_db_exist"
            else:
                return "db_completed"

    # def is_exist(self, info):
    #     print(self.download_queue.entity_list)
    #     for en in self.download_queue.entity_list:
    #         if en.info["_id"] == info["_id"]:
    #             return True

    def is_exist(self, info):
        for _ in self.queue.entity_list:
            if _.info["_id"] == info["_id"]:
                return True
        return False

    def plugin_load(self):
        try:
            logger.debug("%s plugin_load", P.package_name)
            # old version
            self.queue = FfmpegQueue(
                P, P.ModelSetting.get_int("linkkf_max_ffmpeg_process_count")
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
        tmp["linkkf_info"] = self.info
        tmp["epi_queue"] = self.epi_queue
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
