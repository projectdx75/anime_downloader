import os
import sys

# import threading
import traceback
import json
from datetime import datetime
import hashlib
import re
import asyncio
import platform

import PIL.Image

import lxml.etree

# third-party
import requests
from gevent import threading
from lxml import html
from urllib import parse
import urllib

packages = [
    "beautifulsoup4",
    "requests-cache",
    "cloudscraper",
    "selenium_stealth",
    "webdriver_manager",
]
for package in packages:
    try:
        import package

    except ImportError:
        # main(["install", package])
        os.system(f"pip install {package}")

from bs4 import BeautifulSoup
import cloudscraper

# third-party
from flask import request, render_template, jsonify
from sqlalchemy import or_, and_, func, not_, desc

# sjva 공용
from framework import db, scheduler, path_data, socketio
from framework.util import Util
from framework import F
from .mod_base import AnimeModuleBase
from .lib.ffmpeg_queue_v1 import FfmpegQueueEntity, FfmpegQueue
from support.expand.ffmpeg import SupportFfmpeg
from .lib.crawler import Crawler

# from tool_base import d


# 패키지
# from .plugin import P
from .lib.util import Util as AniUtil, yommi_timeit
from typing import Awaitable, TypeVar

T = TypeVar("T")

from .setup import *

logger = P.logger
name = "anilife"


class LogicAniLife(AnimeModuleBase):
    db_default = {
        "anilife_db_version": "1",
        "anilife_url": "https://anilife.live",
        "anilife_download_path": os.path.join(path_data, P.package_name, "ohli24"),
        "anilife_auto_make_folder": "True",
        "anilife_auto_make_season_folder": "True",
        "anilife_finished_insert": "[완결]",
        "anilife_max_ffmpeg_process_count": "1",
        "anilife_download_method": "ffmpeg",  # ffmpeg or ytdlp
        "anilife_download_threads": "16",     # yt-dlp/aria2c 병렬 쓰레드 수
        "anilife_order_desc": "False",
        "anilife_auto_start": "False",
        "anilife_interval": "* 5 * * *",
        "anilife_auto_mode_all": "False",
        "anilife_auto_code_list": "all",
        "anilife_current_code": "",
        "anilife_uncompleted_auto_enqueue": "False",
        "anilife_image_url_prefix_series": "https://www.jetcloud.cc/series/",
        "anilife_image_url_prefix_episode": "https://www.jetcloud-list.cc/thumbnail/",
        "anilife_camoufox_installed": "False",
    }

    current_headers = None
    current_data = None
    referer = None
    origin_url = None
    episode_url = None
    cookies = None
    OS_PLATFORM = None
    response_data = None
    camoufox_setup_done = False

    def ensure_camoufox_installed(self):
        """Camoufox 및 필수 시스템 패키지(xvfb) 설치 확인 및 자동 설치 (백그라운드 실행 가능)"""
        # 1. 메모리상 플래그 확인 (이미 이번 세션에서 확인됨)
        if LogicAniLife.camoufox_setup_done:
            return True

        import importlib.util
        import subprocess as sp
        import shutil
        
        # 2. DB상 설치 여부 확인 및 실제 라이브러리 존재 여부 퀵체크
        # DB에 설치됨으로 되어 있고 실제로 임포트 가능하다면 바이패스
        lib_exists = importlib.util.find_spec("camoufox") is not None
        if P.ModelSetting.get_bool("anilife_camoufox_installed") and lib_exists:
            LogicAniLife.camoufox_setup_done = True
            return True

        # 3. 실제 설치/패치 과정 진행
        try:
            # 시스템 패키지 xvfb 설치 확인 (Linux/Docker 전용)
            if platform.system() == 'Linux' and shutil.which('Xvfb') is None:
                logger.info("Xvfb not found. Attempting to background install system package...")
                try:
                    sp.run(['apt-get', 'update', '-qq'], capture_output=True)
                    sp.run(['apt-get', 'install', '-y', 'xvfb', '-qq'], capture_output=True)
                except Exception as e:
                    logger.error(f"Failed to install xvfb system package: {e}")

            # Camoufox 패키지 확인 및 설치
            if not lib_exists:
                logger.info("Camoufox NOT found in DB or system. Installing in background...")
                cmd = [sys.executable, "-m", "pip", "install", "camoufox[geoip]", "-q"]
                sp.run(cmd, capture_output=True, text=True, timeout=120)
            
            logger.info("Ensuring Camoufox browser binary is fetched (pre-warming)...")
            sp.run([sys.executable, "-m", "camoufox", "fetch"], capture_output=True, text=True, timeout=300)
            
            # 성공 시 DB에 기록하여 다음 재시작 시에는 아예 이 과정을 건너뜀
            LogicAniLife.camoufox_setup_done = True
            P.ModelSetting.set("anilife_camoufox_installed", "True")
            logger.info("Camoufox setup finished and persisted to DB")
            return True
        except Exception as install_err:
            logger.error(f"Failed during Camoufox setup: {install_err}")
            return lib_exists

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "",
        "Cookie": "SPSI=ef307b8c976fac3363cdf420c9ca40a9; SPSE=+PhK0/uGUBMCZIgXplNjzqW3K2kXLybiElDTtOOiboHiBXO7Tp/9roMW7FplGZuGCUo3i4Fwx5VIUG57Zj6VVw==; anilife_csrf=b1eb92529839d7486169cd91e4e60cd2; UTGv2=h45f897818578a5664b31004b95a9992d273; _ga=GA1.1.281412913.1662803695; _ga_56VYJJ7FTM=GS1.1.1662803695.1.0.1662803707.0.0.0; DCST=pE9; DSR=w2XdPUpwLWDqkLpWXfs/5TiO4mtNv5O3hqNhEr7GP1kFoRBBzbFRpR+xsJd9A+E29M+we7qIvJxQmHQTjDNLuQ==; DCSS=696763EB4EA5A67C4E39CFA510FE36F19B0912C; DGCC=RgP; spcsrf=8a6b943005d711258f2f145a8404d873; sp_lit=F9PWLXyxvZbOyk3eVmtTlg==; PRLST=wW; adOtr=70fbCc39867"
        # "Cookie": ""
        # "Cookie": "_ga=GA1.1.578607927.1660813724; __gads=ID=10abb8b98b6828ae-2281c943a9d500fd:T=1660813741:RT=1660813741:S=ALNI_MYU_iB2lBgSrEQUBwhKpNsToaqQ8A; SL_G_WPT_TO=ko; SL_GWPT_Show_Hide_tmp=1; SL_wptGlobTipTmp=1; SPSI=944c237cdd8606d80e5e330a0f332d03; SPSE=itZcXMDuso0ktWnDkV2G0HVwWEctCgDjrcFMlEQ5C745wqvp1pEEddrsAsjPUBjl6/8+9Njpq1IG3wt/tVag7w==; sbtsck=jav9aILa6Ofn0dEQr5DhDq5rpbd1JUoNgKwxBpZrqYd+CM=; anilife_csrf=54ee9d15c87864ee5e2538a63d894ad6; UTGv2=h46b326af644f4ac5d0eb1502881136b3750; DCST=pE9; __gpi=UID=000008ba227e99e0:T=1660813741:RT=1661170429:S=ALNI_MaJHIVJIGpQ5nTE9lvypKQxJnn10A; DSR=GWyTLTvSMF/lQD77ojQkGyl+7JvTudkSwV1GKeNVUcWEBa/msln9zzsBj7lj+89ywSRBM34Ol73AKf+KHZ9bZA==; DCSS=9D44115EC4CE12CADB88A005DC65A3CD74A211E; DGCC=zdV; spcsrf=fba136251afc6b5283109fc920322c70; sp_lit=kw0Xkp66eQ7bV0f0tNClhg==; PRLST=gt; adOtr=2C4H9c4d78d; _ga_56VYJJ7FTM=GS1.1.1661168661.18.1.1661173389.0.0.0",
    }
    useragent = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
    }

    def __init__(self, P):
        super(LogicAniLife, self).__init__(P, setup_default=self.db_default, name=name, first_menu='setting', scheduler_desc="애니라이프 자동 다운로드")
        self.queue = None
        self.web_list_model = ModelAniLifeItem
        self.OS_PLATFORM = platform.system()
        default_route_socketio_module(self, attach="/search")

    def process_command(self, command, arg1, arg2, arg3, req):
        try:
            if command == "list":
                ret = self.queue.get_entity_list() if self.queue else []
                return jsonify(ret)
            elif command == "stop":
                entity_id = int(arg1) if arg1 else -1
                result = self.queue.command("cancel", entity_id) if self.queue else {"ret": "error"}
                return jsonify(result)
            elif command == "remove":
                entity_id = int(arg1) if arg1 else -1
                result = self.queue.command("remove", entity_id) if self.queue else {"ret": "error"}
                return jsonify(result)
            elif command in ["reset", "delete_completed"]:
                result = self.queue.command(command, 0) if self.queue else {"ret": "error"}
                return jsonify(result)
            elif command == "merge_subtitle":
                # AniUtil already imported at module level
                db_id = int(arg1)
                db_item = ModelAniLifeItem.get_by_id(db_id)
                if db_item and db_item.status == 'completed':
                    import threading
                    threading.Thread(target=AniUtil.merge_subtitle, args=(self.P, db_item)).start()
                    return jsonify({"ret": "success", "log": "자막 합칩을 시작합니다."})
                return jsonify({"ret": "fail", "log": "파일을 찾을 수 없거나 완료된 상태가 아닙니다."})
            
            return jsonify({"ret": "fail", "log": f"Unknown command: {command}"})
        except Exception as e:
            self.P.logger.error(f"process_command Error: {e}")
            self.P.logger.error(traceback.format_exc())
            return jsonify({'ret': 'fail', 'log': str(e)})

    # @staticmethod
    def get_html(
        self,
        url: str,
        referer: str = None,
        stream: bool = False,
        is_stealth: bool = False,
        timeout: int = 5,
        headless: bool = False,
    ):
        data = ""
        try:
            print("cloudflare protection bypass ==================")
            # print(self)
            # return LogicAniLife.get_html_cloudflare(url)
            # return self.get_html_selenium(url=url, referer=referer, is_stealth=is_stealth)
            # url: str,
            # headless: bool = False,
            # referer: str = None,
            # engine: str = "chrome",
            # stealth: bool = False,
            # return asyncio.run(LogicAniLife.get_html_playwright(url, engine="chrome", headless=True))
            return asyncio.run(
                LogicAniLife.get_html_playwright(
                    url, engine="chromium", headless=headless
                )
            )
            # return LogicAniLife.get_html_playwright_sync(url, engine="chrome", headless=True)

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
        return data

    @staticmethod
    async def get_vod_url_v1(
        url, headless=False, referer=None, engine="chrome", stealth=False
    ):
        from playwright.sync_api import sync_playwright
        from playwright.async_api import async_playwright
        from playwright_har_tracer import HarTracer
        from playwright_stealth import stealth_sync, stealth_async

        import time

        # scraper = cloudscraper.create_scraper(
        #     browser={"browser": "chrome", "platform": "windows", "desktop": True},
        #     debug=False,
        #     # sess=LogicAniLife.session,
        #     delay=10,
        # )
        #
        # cookie_value, user_agent = scraper.get_cookie_string(url)
        #
        # logger.debug(f"cookie_value:: {cookie_value}")

        start = time.time()
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/69.0.3497.100 Safari/537.36"
        )
        # from playwright_stealth import stealth_sync
        cookie = None

        def set_cookie(req):
            nonlocal cookie
            if "cookie" in req.headers:
                cookie = req.headers["cookie"]

        async with async_playwright() as p:
            if engine == "chrome":
                browser = await p.chromium.launch(channel="chrome", headless=headless)
            elif engine == "webkit":
                browser = await p.webkit.launch(headless=headless)
            else:
                browser = await p.firefox.launch(headless=headless)

            LogicAniLife.headers["Referer"] = "https://anilife.live/detail/id/471"
            # print(LogicAniLife.headers)

            LogicAniLife.headers["Referer"] = LogicAniLife.episode_url

            if referer is not None:
                LogicAniLife.headers["Referer"] = referer

            logger.debug(f"LogicAniLife.headers::: {LogicAniLife.headers}")
            context = await browser.new_context(extra_http_headers=LogicAniLife.headers)
            await context.add_cookies(LogicAniLife.cookies)

            # LogicAniLife.headers["Cookie"] = cookie_value

            # context.set_extra_http_headers(LogicAniLife.headers)
            tracer = HarTracer(context=context, browser_name=p.webkit.name)

            page = await context.new_page()

            # page.set_extra_http_headers(LogicAniLife.headers)

            if stealth:
                await stealth_async(page)

            # page.on("request", set_cookie)
            # stealth_sync(page)
            print(LogicAniLife.headers["Referer"])

            page.on("request", set_cookie)

            print(f'Referer:: {LogicAniLife.headers["Referer"]}')
            # await page.set_extra_http_headers(LogicAniLife.headers)

            await page.goto(
                url, wait_until="load", referer=LogicAniLife.headers["Referer"]
            )

            har = await tracer.flush()
            # page.wait_for_timeout(10000)
            await asyncio.sleep(10)

            # await page.reload()

            # time.sleep(10)
            # cookies = context.cookies
            # print(cookies)

            print(f"page.url:: {page.url}")
            LogicAniLife.origin_url = page.url

            # print(page.content())

            print(f"run at {time.time() - start} sec")

            return await page.content()

    @staticmethod
    async def get_vod_url(url: str, headless: bool = False) -> str:
        from playwright.sync_api import sync_playwright
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async
        import html_to_json
        from playwright_har_tracer import HarTracer
        import time

        # scraper = cloudscraper.create_scraper(
        #     browser={"browser": "chrome", "platform": "windows", "desktop": True},
        #     debug=False,
        #     # sess=LogicAniLife.session,
        #     delay=10,
        # )
        #
        # cookie_value, user_agent = scraper.get_cookie_string(url)
        #
        # logger.debug(f"cookie_value:: {cookie_value}")
        browser_args = [
            "--window-size=1300,570",
            "--window-position=000,000",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-web-security",
            "--disable-features=site-per-process",
            "--disable-setuid-sandbox",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            # "--single-process",
            "--disable-gpu",
            "--use-gl=egl",
            "--disable-blink-features=AutomationControlled",
            "--disable-background-networking",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-client-side-phishing-detection",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-features=Translate",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-renderer-backgrounding",
            "--disable-sync",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--enable-automation",
            "--password-store=basic",
            "--use-mock-keychain",
            "--hide-scrollbars",
            "--mute-audio",
        ]

        start = time.time()
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/69.0.3497.100 Safari/537.36"
        )
        # from playwright_stealth import stealth_sync

        async with async_playwright() as p:
            try:
                # browser = await p.chromium.launch(headless=headless, args=browser_args)
                browser = await p.chromium.launch(headless=headless, args=browser_args)

                # browser = await p.webkit.launch(headless=headless)
                # context = browser.new_context(
                #     user_agent=ua,
                # )

                LogicAniLife.headers[
                    "Referer"
                ] = "https://anilife.live/g/l?id=14344143-040a-4e40-9399-a7d22d94554b"
                # print(LogicAniLife.headers)

                # context = await browser.new_context(extra_http_headers=LogicAniLife.headers)
                context = await browser.new_context()
                await context.set_extra_http_headers(LogicAniLife.headers)

                # await context.add_cookies(LogicAniLife.cookies)

                # tracer = HarTracer(context=context, browser_name=p.chromium.name)
                tracer = HarTracer(context=context, browser_name=p.webkit.name)

                # LogicAniLife.headers["Cookie"] = cookie_value

                # context.set_extra_http_headers(LogicAniLife.headers)

                page = await context.new_page()

                # await page.set_extra_http_headers(LogicAniLife.headers)

                # await stealth_async(page)
                # logger.debug(url)

                # page.on("request", set_cookie)
                # stealth_sync(page)
                # await page.goto(
                #     url, wait_until="load", referer=LogicAniLife.headers["Referer"]
                # )
                # await page.goto(url, wait_until="load")
                await page.goto(url, wait_until="domcontentloaded")

                har = await tracer.flush()

                # page.wait_for_timeout(10000)
                await asyncio.sleep(2)

                # logger.debug(har)
                # page.reload()

                # time.sleep(10)
                # cookies = context.cookies
                # print(cookies)

                # print(page.content())
                # vod_url = page.evaluate(
                #     """() => {
                #     return console.log(vodUrl_1080p) }"""
                # )

                # vod_url = page.evaluate(
                #     """async () =>{
                # return _0x55265f(0x99) + alJson[_0x55265f(0x91)]
                # }"""
                # )
                result_har_json = har.to_json()
                result_har_dict = har.to_dict()
                # logger.debug(result_har_dict)

                tmp_video_url = []
                for i, elem in enumerate(result_har_dict["log"]["entries"]):
                    if "m3u8" in elem["request"]["url"]:
                        logger.debug(elem["request"]["url"])
                        tmp_video_url.append(elem["request"]["url"])

                vod_url = tmp_video_url[-1]

                logger.debug(f"vod_url:: {vod_url}")

                logger.debug(f"run at {time.time() - start} sec")

                return vod_url
            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())
            finally:
                await browser.close()

    @staticmethod
    def get_vod_url_v2(url: str, headless: bool = False) -> str:
        try:
            import json

            post_data = {
                "url": url,
                "headless": headless,
                "engine": "webkit",
                "stealth": True,
            }
            payload = json.dumps(post_data)
            logger.debug(payload)
            response_data = requests.post(
                url="http://localhost:7070/get_vod_url", data=payload
            )

            logger.debug(response_data.text)

            return response_data.text
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    @staticmethod
    def db_init():
        pass



    def process_ajax(self, sub, req):
        try:
            if sub == "analysis":
                # code = req.form['code']
                logger.debug(req)
                code = request.form["code"]

                wr_id = request.form.get("wr_id", None)
                bo_table = request.form.get("bo_table", None)
                data = []

                # logger.info("code::: %s", code)
                P.ModelSetting.set("anilife_current_code", code)
                data = self.get_series_info(code)
                self.current_data = data
                return jsonify({"ret": "success", "data": data, "code": code})
            elif sub == "anime_list":
                data = []
                cate = request.form["type"]
                page = request.form["page"]
                try:
                    data = self.get_anime_info(cate, page)
                    logger.debug(data)
                    if data is not None:
                        return jsonify(
                            {"ret": "success", "cate": cate, "page": page, "data": data}
                        )
                    else:
                        return jsonify({"ret": "error", "data": data})

                except Exception as e:
                    print("error catch")
                    return jsonify({"ret": "error", "data": data})
            elif sub == "complete_list":
                data = []

                cate = request.form["type"]
                logger.debug("cate:: %s", cate)
                page = request.form["page"]

                data = self.get_anime_info(cate, page)
                # self.current_data = data
                return jsonify(
                    {"ret": "success", "cate": cate, "page": page, "data": data}
                )
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
                logger.debug(f"anilife add_queue routine ===============")
                ret = {}
                info = json.loads(request.form["data"])
                logger.info(f"info:: {info}")
                ret["ret"] = self.add(info)
                # 성공적으로 큐에 추가되면 UI 새로고침 트리거
                if ret["ret"].startswith("enqueue"):
                    self.socketio_callback("list_refresh", "")
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
            elif sub == "proxy_image":
                image_url = request.args.get("url") or request.args.get("image_url")
                return self.proxy_image(image_url)
            elif sub == "entity_list":
                if self.queue is not None:
                    return jsonify(self.queue.get_entity_list())
                else:
                    return jsonify([])
            elif sub == "web_list":
                return jsonify(ModelAniLifeItem.web_list(request))
            elif sub == "db_remove":
                return jsonify(ModelAniLifeItem.delete_by_id(req.form["id"]))
            elif sub == "proxy_image":
                # 이미지 프록시: CDN hotlink 보호 우회
                from flask import Response
                # 'image_url' 또는 'url' 파라미터 둘 다 지원
                image_url = request.args.get("image_url") or request.args.get("url", "")
                if not image_url or not image_url.startswith("http"):
                    return Response("Invalid URL", status=400)
                try:
                    # cloudscraper 사용하여 Cloudflare 우회
                    scraper = cloudscraper.create_scraper(
                        browser={
                            "browser": "chrome",
                            "platform": "windows",
                            "desktop": True
                        }
                    )
                    headers = {
                        "Referer": "https://anilife.live/",
                    }
                    img_response = scraper.get(image_url, headers=headers, timeout=10)
                    logger.debug(f"Image proxy: {image_url} -> status {img_response.status_code}")
                    if img_response.status_code == 200:
                        content_type = img_response.headers.get("Content-Type", "image/jpeg")
                        return Response(img_response.content, mimetype=content_type)
                    else:
                        logger.warning(f"Image proxy failed: {image_url} -> {img_response.status_code}")
                        return Response("Image not found", status=404)
                except Exception as img_err:
                    logger.error(f"Image proxy error for {image_url}: {img_err}")
                    return Response("Proxy error", status=500)
            elif sub == "add_whitelist":
                try:
                    params = request.get_json()
                    logger.debug(f"add_whitelist params: {params}")
                    if params and "data_code" in params:
                        code = params["data_code"]
                        ret = LogicAniLife.add_whitelist(code)
                    else:
                        ret = LogicAniLife.add_whitelist()
                    return jsonify(ret)
                except Exception as e:
                    logger.error(f"Exception: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"ret": False, "log": str(e)})
            elif sub == "browse_dir":
                try:
                    path = request.form.get("path", "")
                    if not path or not os.path.exists(path):
                        path = P.ModelSetting.get("anilife_download_path") or os.path.expanduser("~")
                    path = os.path.abspath(path)
                    if not os.path.isdir(path):
                        path = os.path.dirname(path)
                    directories = []
                    try:
                        for item in sorted(os.listdir(path)):
                            item_path = os.path.join(path, item)
                            if os.path.isdir(item_path) and not item.startswith('.'):
                                directories.append({"name": item, "path": item_path})
                    except PermissionError:
                        pass
                    parent = os.path.dirname(path) if path != "/" else None
                    return jsonify({
                        "ret": "success",
                        "current_path": path,
                        "parent_path": parent,
                        "directories": directories
                    })
                except Exception as e:
                    logger.error(f"browse_dir error: {e}")
                    return jsonify({"ret": "error", "error": str(e)}), 500
            
            
            # Fallback to base class for common subs (queue_command, entity_list, browse_dir, command, etc.)
            return super().process_ajax(sub, req)


        except Exception as e:
            P.logger.error("AniLife process_ajax Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return jsonify({"ret": "exception", "log": str(e)})


    @staticmethod
    def add_whitelist(*args):
        ret = {}

        logger.debug(f"args: {args}")
        try:

            if len(args) == 0:
                code = str(LogicAniLife.current_data["code"])
            else:
                code = str(args[0])

            print(code)

            whitelist_program = P.ModelSetting.get("anilife_auto_code_list")
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
                    .filter_by(key="anilife_auto_code_list")
                    .with_for_update()
                    .first()
                )
                entity.value = whitelist_program
                db.session.commit()
                ret["ret"] = True
                ret["code"] = code
                if len(args) == 0:
                    return LogicAniLife.current_data
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
            "anilife_max_ffmpeg_process_count"
        ):
            self.queue.set_max_ffmpeg_count(
                P.ModelSetting.get_int("anilife_max_ffmpeg_process_count")
            )

    def plugin_load(self):
        self.queue = FfmpegQueue(
            P, P.ModelSetting.get_int("anilife_max_ffmpeg_process_count"), name, self
        )
        self.queue.queue_start()

        # 데이터 마이그레이션/동기화: 파일명이 비어있는 항목들 처리
        from framework import app
        with app.app_context():
            try:
                items = ModelAniLifeItem.get_list_uncompleted()
                for item in items:
                    if not item.filename or item.filename == item.title:
                        # 임시로 Entity를 만들어 파일명 생성 로직 활용
                        tmp_info = item.anilife_info if item.anilife_info else {}
                        # dict가 아닐 경우 처리 (문자열 등)
                        if isinstance(tmp_info, str):
                            try: tmp_info = json.loads(tmp_info)
                            except: tmp_info = {}
                        
                        tmp_entity = AniLifeQueueEntity(P, self, tmp_info)
                        if tmp_entity.filename:
                            item.filename = tmp_entity.filename
                            item.save()
                            logger.info(f"Synced filename for item {item.id}: {item.filename}")
            except Exception as e:
                logger.error(f"Data sync error: {e}")
                logger.error(traceback.format_exc())

        self.current_data = None
        self.queue.queue_start()

        # Camoufox 미리 준비 (백그라운드에서 설치 및 바이너리 다운로드)
        threading.Thread(target=self.ensure_camoufox_installed, daemon=True).start()

    def db_delete(self, day):
        try:
            # 전체 삭제 (일수 기준 또는 전체)
            return ModelAniLifeItem.delete_all()
        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def scheduler_function(self):
        logger.debug(f"ohli24 scheduler_function::=========================")

        content_code_list = P.ModelSetting.get_list("anilife_auto_code_list", "|")
        url = f'{P.ModelSetting.get("anilife_url")}/dailyani'
        if "all" in content_code_list:
            ret_data = LogicAniLife.get_auto_anime_info(self, url=url)

    def reset_db(self):
        db.session.query(ModelAniLifeItem).delete()
        db.session.commit()
        return True

    # 시리즈 정보를 가져오는 함수 (cloudscraper 버전)
    def get_series_info(self, code):
        try:
            if code.isdigit():
                url = P.ModelSetting.get("anilife_url") + "/detail/id/" + code
            else:
                url = P.ModelSetting.get("anilife_url") + "/g/l?id=" + code

            logger.debug("get_series_info()::url > %s", url)

            # cloudscraper를 사용하여 Cloudflare 우회
            scraper = cloudscraper.create_scraper(
                browser={
                    "browser": "chrome",
                    "platform": "windows",
                    "desktop": True
                }
            )
            
            # 리다이렉트 자동 처리 (숫자 ID → UUID 페이지로 리다이렉트됨)
            response = scraper.get(url, timeout=15, allow_redirects=True)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch series info: HTTP {response.status_code}")
                return {"ret": "error", "log": f"HTTP {response.status_code}"}
            
            # 최종 URL 로깅 (리다이렉트된 경우)
            logger.debug(f"Final URL after redirect: {response.url}")

            tree = html.fromstring(response.text)

            # tree = html.fromstring(response_data)
            # logger.debug(response_data)
            main_title = tree.xpath('//div[@class="infox"]/h1/text()')[0]
            image = tree.xpath('//div[@class="thumb"]/img/@src')[0]
            des_items = tree.xpath(
                '//div[@class="info-content"]/div[@class="spe"]/span'
            )
            des_items1 = (
                tree.xpath('//div[@class="info-content"]/div[@class="spe"]')[0]
                .text_content()
                .strip()
            )

            des = {}
            des_key = [
                "_otit",
                "_dir",
                "_pub",
                "_tag",
                "_classifi",
                "_country",
                "_season",
                "_grade",
                "_total_chapter",
                "_show_time",
                "_release_year",
                "_recent_date",
                "_air_date",
            ]
            description_dict = {
                "상태": "_status",
                "원제": "_otit",
                "원작": "_org",
                "감독": "_dir",
                "각본": "_scr",
                "시즌": "_season",
                "캐릭터 디자인": "_character_design",
                "음악": "_sound",
                "제작사": "_pub",
                "장르": "_tag",
                "분류": "_classifi",
                "제작국가": "_country",
                "방영일": "_date",
                "등급": "_grade",
                "유형": "_type",
                "에피소드": "_total_chapter",
                "상영시간": "_show_time",
                "공식 방영일": "_release_date",
                "방영 시작일": "_air_date",
                "최근 방영일": "_recent_date",
                "개봉년도": "_release_year",
            }
            # print(main_title)
            # print(image)
            # print(des_items)

            list_body_li = tree.xpath('//div[@class="eplister"]/ul/li')
            # logger.debug(f"list_body_li:: {list_body_li}")

            episodes = []
            vi = None

            for li in list_body_li:
                # logger.debug(li)
                ep_num = li.xpath('.//a/div[@class="epl-num"]/text()')[0].strip()
                title = li.xpath('.//a/div[@class="epl-title"]/text()')[0].strip()
                thumbnail = image
                link = li.xpath(".//a/@href")[0]
                date = ""
                m = hashlib.md5(title.encode("utf-8"))
                _vi = m.hexdigest()
                # 고유한 _id 생성: content_code + ep_num + link의 조합
                # 같은 시리즈 내에서도 에피소드마다 고유하게 식별
                unique_id = f"{code}_{ep_num}_{link}"
                episodes.append(
                    {
                        "ep_num": ep_num,
                        "title": f"{main_title} {ep_num}화 - {title}",
                        "link": link,
                        "thumbnail": image,
                        "date": date,
                        "day": date,
                        "_id": unique_id,
                        "va": link,
                        "_vi": _vi,
                        "content_code": code,
                        "ep_url": url,
                    }
                )

            # print(lxml.etree.tostring(des_items, method="text"))
            #
            # for idx, item in enumerate(des_items):
            #     span = item.xpath(".//b/text()")
            #     logger.info(f"0: {span[0]}")
            #     key = description_dict[span[0].replace(":", "")]
            #     logger.debug(f"key:: {key}")
            #     try:
            #         print(item.xpath(".//text()")[1].strip())
            #         des[key] = item.xpath(".//text()")[1].strip()
            #     except IndexError:
            #         if item.xpath(".//a"):
            #             des[key] = item.xpath(".//a")[0]
            #         des[key] = ""

            ser_description = "작품 설명 부분"
            des = ""
            des1 = ""
            data = {
                "title": main_title,
                "image": image,
                "date": "2022.01.11 00:30 (화)",
                "ser_description": ser_description,
                # "des": des,
                "des1": des_items1,
                "episode": episodes,
            }

            return data

        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    @staticmethod
    def get_real_link(url):
        response = requests.get(url)
        if response.history:
            print("Request was redirected")
            for resp in response.history:
                print(resp.status_code, resp.url)
            print("Final destination:")
            print(response.status_code, response.url)
            return response.url
        else:
            print("Request was not redirected")

    @staticmethod
    def get_anime_info(cate, page):
        logger.debug(f"get_anime_info() routine")
        logger.debug(f"cate:: {cate}")
        wrapper_xpath = '//div[@class="bsx"]'
        try:
            if cate == "ing":
                url = P.ModelSetting.get("anilife_url")
                wrapper_xpath = (
                    '//div[contains(@class, "listupd")]/*/*/div[@class="bsx"]'
                )
            elif cate == "theater":
                url = (
                    P.ModelSetting.get("anilife_url")
                    + "/vodtype/categorize/Movie/"
                    + page
                )
                wrapper_xpath = '//div[@class="bsx"]'
            else:
                url = (
                    P.ModelSetting.get("anilife_url")
                    + "/vodtype/categorize/Movie/"
                    + page
                )
                # cate == "complete":
            logger.info("url:::> %s", url)
            data = {}

            # cloudscraper를 사용하여 Cloudflare 우회
            scraper = cloudscraper.create_scraper(
                browser={
                    "browser": "chrome",
                    "platform": "windows",
                    "desktop": True
                }
            )
            
            response = scraper.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch anime info: HTTP {response.status_code}")
                return {"ret": "error", "log": f"HTTP {response.status_code}"}

            LogicAniLife.episode_url = response.url
            logger.info(response.url)
            logger.debug(LogicAniLife.episode_url)

            soup_text = BeautifulSoup(response.text, "lxml")

            tree = html.fromstring(response.text)
            tmp_items = tree.xpath(wrapper_xpath)

            logger.debug(tmp_items)
            data["anime_count"] = len(tmp_items)
            data["anime_list"] = []

            for item in tmp_items:
                entity = {}
                link_elem = item.xpath(".//a/@href")
                if not link_elem:
                    continue
                entity["link"] = link_elem[0]
                p = re.compile(r"^[http?s://]+[a-zA-Z0-9-]+/[a-zA-Z0-9-_.?=]+$")

                if p.match(entity["link"]) is None:
                    entity["link"] = P.ModelSetting.get("anilife_url") + entity["link"]

                entity["code"] = entity["link"].split("/")[-1]
                
                # 에피소드 수
                epx_elem = item.xpath(".//span[@class='epx']/text()")
                entity["epx"] = epx_elem[0].strip() if epx_elem else ""
                
                # 제목
                title_elem = item.xpath(".//div[@class='tt']/text()")
                entity["title"] = title_elem[0].strip() if title_elem else ""
                
                # 이미지 URL (img 태그에서 직접 추출)
                img_elem = item.xpath(".//img/@src")
                if not img_elem:
                    img_elem = item.xpath(".//img/@data-src")
                if img_elem:
                    entity["image_link"] = img_elem[0].replace("..", P.ModelSetting.get("anilife_url"))
                else:
                    entity["image_link"] = ""
                    
                data["ret"] = "success"
                data["anime_list"].append(entity)

            return data
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    def get_search_result(self, query, page, cate):
        """
        anilife.live 검색 결과를 가져오는 함수
        cloudscraper 버전(v2)을 직접 사용
        
        Args:
            query: 검색어
            page: 페이지 번호 (현재 미사용)
            cate: 카테고리 (현재 미사용)
        
        Returns:
            dict: 검색 결과 데이터 (anime_count, anime_list)
        """
        # cloudscraper 버전 직접 사용 (외부 playwright API 서버 불필요)
        return self.get_search_result_v2(query, page, cate)

    def get_search_result_v2(self, query, page, cate):
        """
        anilife.live 검색 결과를 가져오는 함수 (cloudscraper 버전)
        외부 playwright API 서버 없이 직접 cloudscraper를 사용
        
        Args:
            query: 검색어
            page: 페이지 번호 (현재 미사용, 향후 페이지네이션 지원용)
            cate: 카테고리 (현재 미사용)
        
        Returns:
            dict: 검색 결과 데이터 (anime_count, anime_list)
        """
        try:
            _query = urllib.parse.quote(query)
            url = P.ModelSetting.get("anilife_url") + "/search?keyword=" + _query

            logger.info("get_search_result_v2()::url> %s", url)
            data = {}

            # cloudscraper를 사용하여 Cloudflare 우회
            scraper = cloudscraper.create_scraper(
                browser={
                    "browser": "chrome",
                    "platform": "windows",
                    "desktop": True
                }
            )
            
            response = scraper.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch search results: HTTP {response.status_code}")
                return {"ret": "error", "log": f"HTTP {response.status_code}"}

            tree = html.fromstring(response.text)
            
            # 검색 결과 항목들 (div.bsx)
            tmp_items = tree.xpath('//div[@class="bsx"]')
            
            data["anime_count"] = len(tmp_items)
            data["anime_list"] = []

            for item in tmp_items:
                entity = {}
                
                # 링크 추출
                link_elem = item.xpath(".//a/@href")
                if link_elem:
                    entity["link"] = link_elem[0]
                    # 상대 경로인 경우 절대 경로로 변환
                    if entity["link"].startswith("/"):
                        entity["link"] = P.ModelSetting.get("anilife_url") + entity["link"]
                else:
                    continue
                
                # 코드 추출 (링크에서 ID 추출)
                # /detail/id/832 -> 832
                code_match = re.search(r'/detail/id/(\d+)', entity["link"])
                if code_match:
                    entity["code"] = code_match.group(1)
                else:
                    entity["code"] = entity["link"].split("/")[-1]
                
                # 에피소드 수
                epx_elem = item.xpath(".//span[@class='epx']/text()")
                entity["epx"] = epx_elem[0].strip() if epx_elem else ""
                
                # 제목 (h2 또는 div.tt에서 추출)
                title_elem = item.xpath(".//h2[@itemprop='headline']/text()")
                if not title_elem:
                    title_elem = item.xpath(".//div[@class='tt']/text()")
                entity["title"] = title_elem[0].strip() if title_elem else ""
                
                # 이미지 URL (img 태그에서 직접 추출)
                img_elem = item.xpath(".//img/@src")
                if not img_elem:
                    # data-src 속성 체크 (lazy loading 대응)
                    img_elem = item.xpath(".//img/@data-src")
                if img_elem:
                    entity["image_link"] = img_elem[0]
                else:
                    entity["image_link"] = ""
                
                # wr_id는 anilife에서는 사용하지 않음
                entity["wr_id"] = ""
                
                data["ret"] = "success"
                data["anime_list"].append(entity)

            logger.info("Found %d search results (v2) for query: %s", len(data["anime_list"]), query)
            return data

        except Exception as e:
            P.logger.error(f"AniLife process_ajax Error: {str(e)}")
            P.logger.error(traceback.format_exc())
            return jsonify({"ret": "exception", "log": str(e)})

    def proxy_image(self, image_url):
        try:
            if not image_url or image_url == "None":
                return ""
            import requests
            headers = {
                'Referer': 'https://anilife.live/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            res = requests.get(image_url, headers=headers, stream=True, timeout=10)
            from flask import Response
            return Response(res.content, mimetype=res.headers.get('content-type', 'image/jpeg'))
        except Exception as e:
            P.logger.error(f"AniLife proxy_image error: {e}")
            return ""

    def vtt_proxy(self, vtt_url):
        try:
            import requests
            headers = {
                'Referer': 'https://anilife.live/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            res = requests.get(vtt_url, headers=headers, timeout=10)
            from flask import Response
            return Response(res.text, mimetype='text/vtt')
        except Exception as e:
            P.logger.error(f"AniLife vtt_proxy error: {e}")
            return ""

    #########################################################
    def add(self, episode_info):
        if self.is_exist(episode_info):
            return "queue_exist"
        else:
            db_entity = ModelAniLifeItem.get_by_anilife_id(episode_info["_id"])

            logger.debug(f"db_entity():: => {db_entity}")

            if db_entity is None:
                logger.debug(f"episode_info:: {episode_info}")
                entity = AniLifeQueueEntity(P, self, episode_info)
                logger.debug("entity:::> %s", entity.as_dict())
                ModelAniLifeItem.append(entity.as_dict())

                self.queue.add_queue(entity)

                return "enqueue_db_append"
            elif db_entity.status != "completed":
                entity = AniLifeQueueEntity(P, self, episode_info)

                self.queue.add_queue(entity)
                return "enqueue_db_exist"
            else:
                return "db_completed"

    def is_exist(self, info):
        for e in self.queue.entity_list:
            if e.info["_id"] == info["_id"]:
                return True
        return False


class AniLifeQueueEntity(FfmpegQueueEntity):
    def __init__(self, P, module_logic, info):
        super(AniLifeQueueEntity, self).__init__(P, module_logic, info)
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
        self.filename = info.get("title")
        self.epi_queue = info.get("ep_num")
        self.content_title = info.get("title")

    def get_downloader(self, video_url, output_file, callback=None, callback_function=None):
        from .lib.downloader_factory import DownloaderFactory
        # Anilife는 설정이 따로 없으면 기본 ytdlp 사용하거나 ffmpeg
        method = self.P.ModelSetting.get("anilife_download_method") or "ffmpeg"
        threads = self.P.ModelSetting.get_int("anilife_download_threads") or 16
        logger.info(f"AniLife get_downloader using method: {method}, threads: {threads}")
        
        return DownloaderFactory.get_downloader(
            method=method,
            video_url=video_url,
            output_file=output_file,
            headers=self.headers,
            callback=callback,
            callback_id="anilife",
            threads=threads,
            callback_function=callback_function
        )

    def refresh_status(self):
        self.module_logic.socketio_callback("status", self.as_dict())

    def info_dict(self, tmp):
        # logger.debug("self.info::> %s", self.info)
        for key, value in self.info.items():
            tmp[key] = value
        tmp["vtt"] = self.vtt
        tmp["season"] = self.season
        tmp["content_title"] = self.content_title
        # 큐 리스트에서 '에피소드 제목'으로 명확히 인지되도록 함
        tmp["episode_title"] = self.info.get("title") 
        tmp["anilife_info"] = self.info
        tmp["epi_queue"] = self.epi_queue
        tmp["filename"] = self.filename
        return tmp

    def download_completed(self):
        """Override to update DB status after download completes."""
        # Call parent's download_completed first (handles file move)
        super().download_completed()
        
        # Update DB status - wrap in app context since this runs in a thread
        from framework import app
        with app.app_context():
            db_entity = ModelAniLifeItem.get_by_anilife_id(self.info["_id"])
            if db_entity is not None:
                db_entity.status = "completed"
                db_entity.completed_time = datetime.now()
                # 메타데이터 동기화
                db_entity.filename = self.filename
                db_entity.save_fullpath = getattr(self, 'save_fullpath', None)
                db_entity.filesize = getattr(self, 'filesize', None)
                db_entity.duration = getattr(self, 'duration', None)
                db_entity.quality = getattr(self, 'quality', None)
                db_entity.save()
                logger.info(f"[Anilife] DB status updated to 'completed': {self.info.get('title', 'Unknown')}")

    def prepare_extra(self):
        """
        [Lazy Extraction] prepare_extra() replaces make_episode_info()
        에피소드 정보를 추출하고 비디오 URL을 가져옵니다.
        Selenium + stealth 기반 구현 (JavaScript 실행 필요)
        
        플로우:
        1. Selenium으로 provider 페이지 접속
        2. _aldata JavaScript 변수에서 Base64 데이터 추출
        3. vid_url_1080 값으로 최종 m3u8 URL 구성
        """
        logger.debug("make_episode_info() routine (Selenium version) ==========")
        try:
            import base64
            import json as json_module
            
            base_url = "https://anilife.live"
            LogicAniLife.episode_url = self.info.get("ep_url", base_url)
            
            # 에피소드 provider 페이지 URL
            provider_url = self.info["va"]
            if provider_url.startswith("/"):
                provider_url = base_url + provider_url
            
            logger.debug(f"Provider URL: {provider_url}")
            logger.info(f"Episode info: {self.info}")
            
            provider_html = None
            aldata_value = None
            
            # Camoufox를 subprocess로 실행
            try:
                import subprocess
                import json as json_module
                
                # 셋업 확인 (이미 완료되었으면 즉시 반환, 아니면 대기)
                if not self.module_logic.ensure_camoufox_installed():
                    logger.error("Camoufox installation failed. Cannot proceed.")
                    return
                
                # camoufox_anilife.py 스크립트 경로
                script_path = os.path.join(os.path.dirname(__file__), "lib", "camoufox_anilife.py")
                
                # detail_url과 episode_num 추출
                detail_url = self.info.get("ep_url", f"https://anilife.live/detail/id/{self.info.get('content_code', '')}")
                episode_num = str(self.info.get("ep_num", "1"))
                provider_url = self.info.get("va") # 직접 진입용 프로바이더 URL
                if provider_url and provider_url.startswith("/"):
                    provider_url = f"https://anilife.live{provider_url}"
                
                logger.debug(f"Running Camoufox subprocess: {script_path}")
                logger.debug(f"Detail URL: {detail_url}, Episode: {episode_num}, Provider: {provider_url}")
                
                # subprocess로 Camoufox 스크립트 실행 (stderr 실시간 로그 연동)
                cmd = [sys.executable, script_path, detail_url, episode_num]
                if provider_url:
                    cmd.append(provider_url)
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # stderr를 실시간으로 logger.info에 기록 (진단 가시성 확보)
                stdout_data = []
                import threading
                def log_stderr(pipe):
                    for line in iter(pipe.readline, ''):
                        if line.strip():
                            # tqdm 진행바나 불필요한 로그는 debug 레벨로 출력하여 로그 도배 방지
                            if '%' in line or '|' in line or 'addon' in line.lower():
                                logger.debug(f"[Camoufox-Progress] {line.strip()}")
                            else:
                                logger.info(f"[Camoufox] {line.strip()}")
                
                stderr_thread = threading.Thread(target=log_stderr, args=(process.stderr,))
                stderr_thread.start()
                
                # stdout 캡처 (JSON 결과)
                for line in iter(process.stdout.readline, ''):
                    stdout_data.append(line)
                
                try:
                    process.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    logger.error("Camoufox subprocess timed out (120s)")
                    process.kill()
                    return
                    
                stderr_thread.join(timeout=5)
                
                stdout_full = "".join(stdout_data)
                
                # JSON 결과 파싱
                try:
                    cf_result = json_module.loads(stdout_full)
                except json_module.JSONDecodeError as e:
                    logger.error(f"Failed to parse Camoufox result: {e}")
                    logger.debug(f"Raw stdout: {stdout_full}")
                    return
                
                elapsed = cf_result.get("elapsed", "?")
                logger.info(f"Camoufox extraction finished in {elapsed}s (success={cf_result.get('success')})")
                
                if not cf_result.get("success"):
                    logger.error(f"Camoufox failed: {cf_result.get('error')}")
                    if cf_result.get("html"):
                        logger.debug(f"Failed page HTML length: {len(cf_result['html'])}")
                    return
                
                # _aldata 추출 성공
                if cf_result.get("aldata"):
                    aldata_value = cf_result["aldata"]
                    logger.debug(f"Got _aldata ({cf_result.get('source', 'unknown')})")
                else:
                    logger.error("Success reported but no aldata returned")
                    return
                    
            except subprocess.TimeoutExpired:
                logger.error("Camoufox subprocess timed out")
                return
            except FileNotFoundError:
                logger.error(f"Camoufox script not found: {script_path}")
                return
            except Exception as cf_err:
                logger.error(f"Camoufox subprocess error: {cf_err}")
                logger.error(traceback.format_exc())
                return
            
            # _aldata 처리
            if aldata_value:
                # JavaScript에서 직접 가져온 경우
                aldata_b64 = aldata_value
            elif provider_html:
                # HTML에서 추출
                aldata_patterns = [
                    r"var\s+_aldata\s*=\s*['\"]([A-Za-z0-9+/=]+)['\"]",
                    r"let\s+_aldata\s*=\s*['\"]([A-Za-z0-9+/=]+)['\"]",
                    r"const\s+_aldata\s*=\s*['\"]([A-Za-z0-9+/=]+)['\"]",
                    r"_aldata\s*=\s*['\"]([A-Za-z0-9+/=]+)['\"]",
                    r"_aldata\s*=\s*'([^']+)'",
                    r'_aldata\s*=\s*"([^"]+)"',
                ]
                
                aldata_match = None
                for pattern in aldata_patterns:
                    aldata_match = re.search(pattern, provider_html)
                    if aldata_match:
                        logger.debug(f"Found _aldata with pattern: {pattern}")
                        break
                
                if not aldata_match:
                    if "_aldata" in provider_html:
                        idx = provider_html.find("_aldata")
                        snippet = provider_html[idx:idx+200]
                        logger.error(f"_aldata found but pattern didn't match. Snippet: {snippet}")
                    else:
                        logger.error("_aldata not found in provider page at all")
                        logger.debug(f"HTML snippet (first 1000 chars): {provider_html[:1000]}")
                    return
                
                aldata_b64 = aldata_match.group(1)
            else:
                logger.error("No provider HTML or _aldata value available")
                return
            
            logger.debug(f"Found _aldata: {aldata_b64[:50]}...")
            
            # Base64 디코딩
            try:
                aldata_json = base64.b64decode(aldata_b64).decode('utf-8')
                aldata = json_module.loads(aldata_json)
                logger.debug(f"Decoded _aldata: {aldata}")
            except Exception as decode_err:
                logger.error(f"Failed to decode _aldata: {decode_err}")
                return
            
            # vid_url_1080 추출
            vid_url_path = aldata.get("vid_url_1080")
            if not vid_url_path or vid_url_path == "none":
                # 720p 폴백
                vid_url_path = aldata.get("vid_url_720")
            
            if not vid_url_path or vid_url_path == "none":
                logger.error("No video URL found in _aldata")
                return
            
            # API URL 구성 (이 URL은 JSON을 반환함)
            api_url = f"https://{vid_url_path}"
            logger.info(f"API URL: {api_url}")
            
            # API에서 실제 m3u8 URL 가져오기
            try:
                api_headers = {
                    "Referer": "https://anilife.live/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                }
                api_response = requests.get(api_url, headers=api_headers, timeout=30)
                api_data = api_response.json()
                
                # JSON 배열에서 URL 추출
                if isinstance(api_data, list) and len(api_data) > 0:
                    vod_url = api_data[0].get("url")
                    logger.info(f"Extracted m3u8 URL from API: {vod_url}")
                else:
                    logger.error(f"Unexpected API response format: {api_data}")
                    return
            except Exception as api_err:
                logger.error(f"Failed to get m3u8 URL from API: {api_err}")
                # 폴백: 원래 URL 사용
                vod_url = api_url
            
            logger.info(f"Video URL: {vod_url}")
            
            # 파일명 및 저장 경로 설정
            match = re.compile(
                r"(?P<title>.*?)\s*((?P<season>\d+)%s)?\s*((?P<epi_no>\d+)%s)"
                % ("기", "화")
            ).search(self.info["title"])

            epi_no = 1
            self.quality = "1080P"

            if match:
                self.content_title = match.group("title").strip()
                if "season" in match.groupdict() and match.group("season") is not None:
                    self.season = int(match.group("season"))

                epi_no = int(match.group("epi_no"))
                ret = "%s.S%sE%s.%s-AL.mp4" % (
                    self.content_title,
                    "0%s" % self.season if self.season < 10 else self.season,
                    "0%s" % epi_no if epi_no < 10 else epi_no,
                    self.quality,
                )
            else:
                self.content_title = self.info["title"]
                P.logger.debug("NOT MATCH")
                ret = "%s.720p-AL.mp4" % self.info["title"]

            self.epi_queue = epi_no

            self.filename = AniUtil.change_text_for_use_filename(ret)
            logger.info(f"Filename: {self.filename}")
            
            # anilife 전용 다운로드 경로 설정
            self.savepath = P.ModelSetting.get("anilife_download_path")
            logger.info(f"Savepath: {self.savepath}")

            if P.ModelSetting.get_bool("anilife_auto_make_folder"):
                if self.info.get("day", "").find("완결") != -1:
                    folder_name = "%s %s" % (
                        P.ModelSetting.get("anilife_finished_insert"),
                        self.content_title,
                    )
                else:
                    folder_name = self.content_title
                folder_name = AniUtil.change_text_for_use_filename(folder_name.strip())
                self.savepath = os.path.join(self.savepath, folder_name)
                
                if P.ModelSetting.get_bool("anilife_auto_make_season_folder"):
                    self.savepath = os.path.join(
                        self.savepath, "Season %s" % int(self.season)
                    )
            
            self.filepath = os.path.join(self.savepath, self.filename)
            if not os.path.exists(self.savepath):
                os.makedirs(self.savepath)

            # 최종 비디오 URL 설정
            self.url = vod_url
            logger.info(f"Final video URL: {self.url}")
            
            # 헤더 설정 (gcdn.app CDN 접근용)
            self.headers = {
                "Referer": "https://anilife.live/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Origin": "https://anilife.live"
            }
            logger.info(f"Headers: {self.headers}")
            
        except Exception as e:
            P.logger.error(f"Exception: {str(e)}")
            P.logger.error(traceback.format_exc())


class ModelAniLifeItem(db.Model):
    __tablename__ = "{package_name}_anilife_item".format(package_name=P.package_name)
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
    anilife_va = db.Column(db.String)
    anilife_vi = db.Column(db.String)
    anilife_id = db.Column(db.String)
    quality = db.Column(db.String)
    filepath = db.Column(db.String)
    filename = db.Column(db.String)
    savepath = db.Column(db.String)
    video_url = db.Column(db.String)
    vtt_url = db.Column(db.String)
    thumbnail = db.Column(db.String)
    status = db.Column(db.String)
    anilife_info = db.Column(db.JSON)

    def __init__(self):
        self.created_time = datetime.now()

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret["created_time"] = self.created_time.strftime("%Y-%m-%d %H:%M:%S") if self.created_time is not None else None
        ret["completed_time"] = (
            self.completed_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.completed_time is not None
            else None
        )
        # 템플릿 호환용 (anilife_list.html)
        ret["image_link"] = self.thumbnail
        ret["ep_num"] = self.episode_no
        # content_title이 없으면 제목(시리즈명)으로 활용
        ret["content_title"] = self.anilife_info.get("content_title") if self.anilife_info else self.title
        return ret

    def save(self):
        db.session.add(self)
        db.session.commit()

    @classmethod
    def get_by_id(cls, idx):
        return db.session.query(cls).filter_by(id=idx).first()

    @classmethod
    def get_by_anilife_id(cls, anilife_id):
        return db.session.query(cls).filter_by(anilife_id=anilife_id).first()

    @classmethod
    def delete_by_id(cls, idx):
        try:
            logger.debug(f"delete_by_id: {idx} (type: {type(idx)})")
            if isinstance(idx, str) and ',' in idx:
                id_list = [int(x.strip()) for x in idx.split(',') if x.strip()]
                logger.debug(f"Batch delete: {id_list}")
                count = db.session.query(cls).filter(cls.id.in_(id_list)).delete(synchronize_session='fetch')
                logger.debug(f"Deleted count: {count}")
            else:
                db.session.query(cls).filter_by(id=int(idx)).delete()
                logger.debug(f"Single delete: {idx}")
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    @classmethod
    def delete_all(cls):
        try:
            db.session.query(cls).delete()
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())
            return False

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
        # 중복 체크
        existing = cls.get_by_anilife_id(q["_id"])
        if existing:
            logger.debug(f"Item already exists in DB: {q['_id']}")
            return existing
            
        item = ModelAniLifeItem()
        item.content_code = q["content_code"]
        item.season = q["season"]
        item.episode_no = q.get("epi_queue")
        item.title = q["content_title"]
        item.episode_title = q["title"]
        item.anilife_va = q.get("va")
        item.anilife_vi = q.get("_vi")
        item.anilife_id = q["_id"]
        item.quality = q["quality"]
        item.filepath = q.get("filepath")
        item.filename = q.get("filename")
        item.savepath = q.get("savepath")
        item.video_url = q.get("url")
        item.vtt_url = q.get("vtt")
        item.thumbnail = q.get("thumbnail")
        item.status = "wait"
        item.anilife_info = q.get("anilife_info")
        item.save()
