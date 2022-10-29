import os
import sys
import threading
import traceback
import json
from datetime import datetime
import hashlib
import re
import asyncio
import platform

import lxml.etree

# third-party
import requests
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
from plugin import (
    PluginModuleBase
)
from flaskfarm.lib.plugin._ffmpeg_queue import FfmpegQueueEntity, FfmpegQueue

# from tool_base import d

# 패키지
# from .plugin import P
from .setup import *

logger = P.logger


# =================================================================#


# 패키지
class LogicAniLife(PluginModuleBase):
    db_default = {
        "anilife_db_version": "1",
        "anilife_url": "https://anilife.live",
        "anilife_download_path": os.path.join(path_data, P.package_name, "ohli24"),
        "anilife_auto_make_folder": "True",
        "anilife_auto_make_season_folder": "True",
        "anilife_finished_insert": "[완결]",
        "anilife_max_ffmpeg_process_count": "1",
        "anilife_order_desc": "False",
        "anilife_auto_start": "False",
        "anilife_interval": "* 5 * * *",
        "anilife_auto_mode_all": "False",
        "anilife_auto_code_list": "all",
        "anilife_current_code": "",
        "anilife_uncompleted_auto_enqueue": "False",
        "anilife_image_url_prefix_series": "https://www.jetcloud.cc/series/",
        "anilife_image_url_prefix_episode": "https://www.jetcloud-list.cc/thumbnail/",
    }

    current_headers = None
    current_data = None
    referer = None
    origin_url = None
    episode_url = None
    cookies = None

    os_platform = platform.system()

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
        super(LogicAniLife, self).__init__(P, "setting", scheduler_desc="애니라이프 자동 다운로드")
        self.name = "anilife"
        self.queue = None
        default_route_socketio_module(self, attach='/search')

    @staticmethod
    def get_html(url: str, referer: str = None, stream: bool = False, timeout: int = 5):
        data = ""
        try:
            print("cloudflare protection bypass ==================")
            # return LogicAniLife.get_html_cloudflare(url)
            return LogicAniLife.get_html_selenium(url, referer)
            # return LogicAniLife.get_html_playwright(url)

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
        return data

    @staticmethod
    def get_html_requests(
        url: str, referer: str = None, stream: str = False, timeout: int = 5
    ) -> str:
        data = ""
        try:
            print("get_html_requests ==================")

            # cj = browser_cookie3.chrome(domain_name="anilife.live")
            referer = "https://anilife.live/"

            if LogicAniLife.session is None:
                LogicAniLife.session = requests.session()

            # logger.debug('get_html :%s', url)
            LogicAniLife.headers["Referer"] = "" if referer is None else referer
            LogicAniLife.headers[
                "Cookie"
            ] = "_ga=GA1.1.578607927.1660813724; __gads=ID=10abb8b98b6828ae-2281c943a9d500fd:T=1660813741:RT=1660813741:S=ALNI_MYU_iB2lBgSrEQUBwhKpNsToaqQ8A; sbtsck=javuwDzcOJqUyweM1OQeNGzHbjoHp7Cgw44XnPdM738c3E=;  SPSI=e48379959d54a6a62cc7abdcafdb2761; SPSE=h5HfMGLJzLqzNafMD3YaOvHSC9xfh77CcWdKvexp/z5N5OsTkIiYSCudQhFffEfk/0pcOTVf0DpeV0RoNopzig==; anilife_csrf=b93b9f25a12a51cf185805ec4de7cf9d; UTGv2=h46b326af644f4ac5d0eb1502881136b3750; __gpi=UID=000008ba227e99e0:T=1660813741:RT=1660912282:S=ALNI_MaJHIVJIGpQ5nTE9lvypKQxJnn10A; DSR=SXPX8ELcRgh6N/9rNgjpQoNfaX2DRceeKYR0/ul7qTI9gApWQpZxr8jgymf/r0HsUT551vtOv2CMWpIn0Hd26A==; DCSS=89508000A76BBD939F6DDACE5BD9EB902D2212A; DGCC=Wdm; adOtr=7L4Xe58995d; spcsrf=6554fa003bf6a46dd9b7417acfacc20a; _ga_56VYJJ7FTM=GS1.1.1660912281.10.1.1660912576.0.0.0; PRLST=EO"

            LogicAniLife.headers["Referer"] = referer

            page_content = LogicAniLife.session.get(
                url, headers=headers, timeout=timeout, allow_redirects=True
            )
            data = page_content.text
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
        return data

    @staticmethod
    async def get_html_playwright(
        url: str,
        headless: bool = False,
        referer: str = None,
        engine: str = "chrome",
        stealth: bool = False,
    ) -> str:
        try:
            from playwright.sync_api import sync_playwright
            from playwright.async_api import async_playwright
            from playwright_stealth import stealth_sync, stealth_async

            import time

            cookie = None
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
                # '--single-process',
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

            def set_cookie(req):
                nonlocal cookie
                if "cookie" in req.headers:
                    cookie = req.headers["cookie"]

            async with async_playwright() as p:
                try:
                    if engine == "chrome":
                        browser = await p.chromium.launch(
                            channel="chrome", args=browser_args, headless=headless
                        )
                    elif engine == "webkit":
                        browser = await p.webkit.launch(
                            headless=headless,
                            args=browser_args,
                        )
                    else:
                        browser = await p.firefox.launch(
                            headless=headless,
                            args=browser_args,
                        )
                    # context = browser.new_context(
                    #     user_agent=ua,
                    # )

                    LogicAniLife.headers[
                        "Referer"
                    ] = "https://anilife.live/detail/id/471"
                    # print(LogicAniLife.headers)

                    LogicAniLife.headers["Referer"] = LogicAniLife.episode_url

                    if referer is not None:
                        LogicAniLife.headers["Referer"] = referer

                    logger.debug(f"LogicAniLife.headers::: {LogicAniLife.headers}")
                    context = await browser.new_context(
                        extra_http_headers=LogicAniLife.headers
                    )
                    await context.add_cookies(LogicAniLife.cookies)

                    # LogicAniLife.headers["Cookie"] = cookie_value

                    # context.set_extra_http_headers(LogicAniLife.headers)

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
                    # page.wait_for_timeout(10000)
                    await asyncio.sleep(2.9)

                    # await page.reload()

                    # time.sleep(10)
                    # cookies = context.cookies
                    # print(cookies)

                    print(f"page.url:: {page.url}")
                    LogicAniLife.origin_url = page.url

                    # print(page.content())

                    print(f"run at {time.time() - start} sec")

                    return await page.content()
                except Exception as e:
                    logger.error("Exception:%s", e)
                    logger.error(traceback.format_exc())
                finally:
                    await browser.close()

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
        finally:
            # browser.close()
            pass

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
    def get_html_selenium(url: str, referer: str) -> bytes:
        from selenium.webdriver.common.by import By
        from selenium import webdriver
        from selenium_stealth import stealth
        from webdriver_manager.chrome import ChromeDriverManager
        import time

        options = webdriver.ChromeOptions()
        # 크롬드라이버 헤더 옵션추가 (리눅스에서 실행시 필수)
        options.add_argument("start-maximized")
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("window-size=1920x1080")
        options.add_argument("disable-gpu")
        # options.add_argument('--no-sandbox')
        options.add_argument("--disable-dev-shm-usage")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        if LogicAniLife.os_platform == "Darwin":
            # 크롬드라이버 경로
            driver_path = "./bin/Darwin/chromedriver"
            # driver = webdriver.Chrome(executable_path=driver_path, chrome_options=options)
            driver = webdriver.Chrome(
                ChromeDriverManager().install(), chrome_options=options
            )
        else:
            driver_bin_path = os.path.join(
                os.path.dirname(__file__), "bin", f"{LogicAniLife.os_platform}"
            )
            driver_path = f"{driver_bin_path}/chromedriver"
            driver = webdriver.Chrome(
                executable_path=driver_path, chrome_options=options
            )

        stealth(
            driver,
            languages=["ko-KR", "ko"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        driver.get(url)

        driver.refresh()
        logger.debug(f"current_url:: {driver.current_url}")
        # logger.debug(f"current_cookie:: {driver.get_cookies()}")
        cookies_list = driver.get_cookies()

        cookies_dict = {}
        for cookie in cookies_list:
            cookies_dict[cookie["name"]] = cookie["value"]

        # logger.debug(cookies_dict)
        LogicAniLife.cookies = cookies_list
        # LogicAniLife.headers["Cookie"] = driver.get_cookies()
        LogicAniLife.episode_url = driver.current_url
        time.sleep(1)
        elem = driver.find_element(By.XPATH, "//*")
        source_code = elem.get_attribute("outerHTML")

        driver.close()

        return source_code.encode("utf-8")

    # Create a request interceptor
    @staticmethod
    def interceptor(request):
        del request.headers["Referer"]  # Delete the header first
        request.headers[
            "Referer"
        ] = "https://anilife.live/g/l?id=0a36917f-39cc-43ea-b0c6-0c86d27c2408"

    @staticmethod
    def get_html_seleniumwire(url, referer, wired=False):
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from seleniumwire import webdriver as wired_webdriver
        from selenium_stealth import stealth
        import time

        options = webdriver.ChromeOptions()
        # 크롬드라이버 헤더 옵션추가 (리눅스에서 실행시 필수)
        options.add_argument("start-maximized")
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        # 크롬드라이버 경로
        driver_path = "./bin/Darwin/chromedriver"
        if wired:
            driver = wired_webdriver.Chrome(
                executable_path=driver_path, chrome_options=options
            )
        else:
            driver = webdriver.Chrome(
                executable_path=driver_path, chrome_options=options
            )

        # stealth ======================================
        # stealth(
        #     driver,
        #     languages=["en-US", "en"],
        #     vendor="Google Inc.",
        #     platform="Win32",
        #     webgl_vendor="Intel Inc.",
        #     renderer="Intel Iris OpenGL Engine",
        #     fix_hairline=True,
        # )
        if wired:
            driver.request_interceptor = LogicAniLife.interceptor
        driver.get(url)
        driver.refresh()
        time.sleep(1)
        elem = driver.find_element(By.XPATH, "//*")
        source_code = elem.get_attribute("outerHTML")

        return source_code.encode("utf-8")

    @staticmethod
    def get_html_cloudflare(url, cached=False):
        # scraper = cloudscraper.create_scraper(
        #     # disableCloudflareV1=True,
        #     # captcha={"provider": "return_response"},
        #     delay=10,
        #     browser="chrome",
        # )
        # scraper = cfscrape.create_scraper(
        #     browser={"browser": "chrome", "platform": "android", "desktop": False}
        # )

        # scraper = cloudscraper.create_scraper(
        #     browser={"browser": "chrome", "platform": "windows", "mobile": False},
        #     debug=True,
        # )

        # LogicAniLife.headers["referer"] = LogicAniLife.referer
        LogicAniLife.headers["Referer"] = "https://anilife.live/"
        LogicAniLife.headers[
            "Cookie"
        ] = "_ga=GA1.1.578607927.1660813724; __gads=ID=10abb8b98b6828ae-2281c943a9d500fd:T=1660813741:RT=1660813741:S=ALNI_MYU_iB2lBgSrEQUBwhKpNsToaqQ8A; sbtsck=javuwDzcOJqUyweM1OQeNGzHbjoHp7Cgw44XnPdM738c3E=;  SPSI=e48379959d54a6a62cc7abdcafdb2761; SPSE=h5HfMGLJzLqzNafMD3YaOvHSC9xfh77CcWdKvexp/z5N5OsTkIiYSCudQhFffEfk/0pcOTVf0DpeV0RoNopzig==; anilife_csrf=b93b9f25a12a51cf185805ec4de7cf9d; UTGv2=h46b326af644f4ac5d0eb1502881136b3750; __gpi=UID=000008ba227e99e0:T=1660813741:RT=1660912282:S=ALNI_MaJHIVJIGpQ5nTE9lvypKQxJnn10A; DSR=SXPX8ELcRgh6N/9rNgjpQoNfaX2DRceeKYR0/ul7qTI9gApWQpZxr8jgymf/r0HsUT551vtOv2CMWpIn0Hd26A==; DCSS=89508000A76BBD939F6DDACE5BD9EB902D2212A; DGCC=Wdm; adOtr=7L4Xe58995d; spcsrf=6554fa003bf6a46dd9b7417acfacc20a; _ga_56VYJJ7FTM=GS1.1.1660912281.10.1.1660912576.0.0.0; PRLST=EO"
        # logger.debug(f"headers:: {LogicAniLife.headers}")

        if LogicAniLife.session is None:
            LogicAniLife.session = requests.Session()
            LogicAniLife.session.headers = LogicAniLife.headers

        # LogicAniLife.session = requests.Session()

        sess = cloudscraper.create_scraper(
            browser={"browser": "firefox", "platform": "windows", "desktop": True},
            debug=False,
            sess=LogicAniLife.session,
            delay=10,
        )

        # print(scraper.get(url, headers=LogicAniLife.headers).content)
        # print(scraper.get(url).content)
        # return scraper.get(url, headers=LogicAniLife.headers).content
        # print(LogicAniLife.headers)
        return sess.get(
            url, headers=LogicAniLife.session.headers, timeout=10, allow_redirects=True
        ).content.decode("utf8", errors="replace")

    @staticmethod
    def db_init():
        pass

    def process_menu(self, sub, req):
        arg = P.ModelSetting.to_dict()
        arg["sub"] = self.name
        if sub in ["setting", "queue", "list", "category", "request"]:
            if sub == "request" and req.args.get("content_code") is not None:
                arg["anilife_current_code"] = req.args.get("content_code")
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

                data = self.get_anime_info(cate, page)
                # self.current_data = data
                return jsonify(
                    {"ret": "success", "cate": cate, "page": page, "data": data}
                )
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
                logger.debug(f"add_queue routine ===============")
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
                return jsonify(ModelAniLifeItem.web_list(request))
            elif sub == "db_remove":
                return jsonify(ModelAniLifeItem.delete_by_id(req.form["id"]))
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())

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

    def scheduler_function(self):
        logger.debug(f"ohli24 scheduler_function::=========================")

        content_code_list = P.ModelSetting.get_list("ohli24_auto_code_list", "|")
        url = f'{P.ModelSetting.get("anilife_url")}/dailyani'
        if "all" in content_code_list:
            ret_data = LogicAniLife.get_auto_anime_info(self, url=url)

    def plugin_load(self):
        self.queue = FfmpegQueue(
            P, P.ModelSetting.get_int("anilife_max_ffmpeg_process_count")
        )
        self.current_data = None
        self.queue.queue_start()

    def reset_db(self):
        db.session.query(ModelAniLifeItem).delete()
        db.session.commit()
        return True

    # 시리즈 정보를 가져오는 함수
    def get_series_info(self, code):
        try:
            if code.isdigit():
                url = P.ModelSetting.get("anilife_url") + "/detail/id/" + code
            else:
                url = P.ModelSetting.get("anilife_url") + "/g/l?id=" + code

            logger.debug("url::: > %s", url)
            response_data = LogicAniLife.get_html(url, timeout=10)
            tree = html.fromstring(response_data)
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
                episodes.append(
                    {
                        "ep_num": ep_num,
                        "title": f"{main_title} {ep_num}화 - {title}",
                        "link": link,
                        "thumbnail": image,
                        "date": date,
                        "day": date,
                        "_id": title,
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

    def get_anime_info(self, cate, page):
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
            response_data = LogicAniLife.get_html(url, timeout=10)
            # logger.debug(response_data)

            # logger.debug(f"wrapper_xath:: {wrapper_xpath}")
            tree = html.fromstring(response_data)
            tmp_items = tree.xpath(wrapper_xpath)
            data["anime_count"] = len(tmp_items)
            data["anime_list"] = []

            for item in tmp_items:
                entity = {}
                entity["link"] = item.xpath(".//a/@href")[0]
                # logger.debug(entity["link"])
                p = re.compile(r"^[http?s://]+[a-zA-Z0-9-]+/[a-zA-Z0-9-_.?=]+$")

                # print(p.match(entity["link"]) != None)
                if p.match(entity["link"]) is None:
                    entity["link"] = P.ModelSetting.get("anilife_url") + entity["link"]
                    # real_url = LogicAniLife.get_real_link(url=entity["link"])

                # logger.debug(entity["link"])

                entity["code"] = entity["link"].split("/")[-1]
                entity["title"] = item.xpath(".//div[@class='tt']/text()")[0].strip()
                entity["image_link"] = item.xpath(".//div[@class='limit']/img/@src")[
                    0
                ].replace("..", P.ModelSetting.get("anilife_url"))
                data["ret"] = "success"
                data["anime_list"].append(entity)

            return data
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

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
        # Todo::: 임시 주석 처리
        self.make_episode_info()

    def refresh_status(self):
        self.module_logic.socketio_callback("status", self.as_dict())

    def info_dict(self, tmp):
        # logger.debug("self.info::> %s", self.info)
        for key, value in self.info.items():
            tmp[key] = value
        tmp["vtt"] = self.vtt
        tmp["season"] = self.season
        tmp["content_title"] = self.content_title
        tmp["anilife_info"] = self.info
        tmp["epi_queue"] = self.epi_queue
        return tmp

    def donwload_completed(self):
        db_entity = ModelAniLifeItem.get_by_anilife_id(self.info["_id"])
        if db_entity is not None:
            db_entity.status = "completed"
            db_entity.complated_time = datetime.now()
            db_entity.save()

    def make_episode_info(self):
        logger.debug("make_episode_info() routine ==========")
        try:
            # 다운로드 추가
            base_url = "https://anilife.live"
            iframe_url = ""

            url = self.info["va"]
            logger.debug(f"url:: {url}")

            ourls = parse.urlparse(url)

            self.headers = {
                "Referer": f"{ourls.scheme}://{ourls.netloc}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36",
            }

            headers["Referer"] = "https://anilife.live/detail/id/471"
            headers["Referer"] = LogicAniLife.episode_url

            logger.debug("make_episode_info()::url==> %s", url)
            logger.info(f"self.info:::> {self.info}")

            referer = "https://anilife.live/g/l?id=13fd4d28-ff18-4764-9968-7e7ea7347c51"
            referer = LogicAniLife.episode_url

            # text = requests.get(url, headers=headers).text
            # text = LogicAniLife.get_html_seleniumwire(url, referer=referer, wired=True)
            # https://anilife.live/ani/provider/10f60832-20d1-4918-be62-0f508bf5460c
            referer_url = (
                "https://anilife.live/g/l?id=d4be1e0e-301b-403b-be1b-cf19f3ccfd23"
            )
            referer_url = LogicAniLife.episode_url

            logger.debug(f"LogicAniLife.episode_url:: {LogicAniLife.episode_url}")
            text = asyncio.run(
                LogicAniLife.get_html_playwright(
                    url,
                    headless=True,
                    referer=referer_url,
                    engine="chrome",
                    stealth=True,
                )
            )

            # vod_1080p_url = text

            # logger.debug(text)
            soup = BeautifulSoup(text, "lxml")

            all_scripts = soup.find_all("script")
            # print(all_scripts)

            regex = r"(?P<jawcloud_url>http?s:\/\/.*=jawcloud)"
            match = re.compile(regex).search(text)

            jawcloud_url = None
            # print(match)
            if match:
                jawcloud_url = match.group("jawcloud_url")

            logger.debug(f"jawcloud_url:: {jawcloud_url}")

            # loop = asyncio.new_event_loop()
            # asyncio.set_event_loop(loop)
            #
            logger.info(self.info)

            match = re.compile(
                r"(?P<title>.*?)\s*((?P<season>\d+)%s)?\s*((?P<epi_no>\d+)%s)"
                % ("기", "화")
            ).search(self.info["title"])

            # epi_no 초기값
            epi_no = 1
            self.quality = "1080P"

            if match:
                self.content_title = match.group("title").strip()
                if "season" in match.groupdict() and match.group("season") is not None:
                    self.season = int(match.group("season"))

                # epi_no = 1
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

            # logger.info('self.content_title:: %s', self.content_title)
            self.epi_queue = epi_no

            self.filename = Util.change_text_for_use_filename(ret)
            logger.info(f"self.filename::> {self.filename}")
            self.savepath = P.ModelSetting.get("ohli24_download_path")
            logger.info(f"self.savepath::> {self.savepath}")

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

            vod_1080p_url = asyncio.run(
                LogicAniLife.get_vod_url(jawcloud_url, headless=True)
            )
            print(f"vod_1080p_url:: {vod_1080p_url}")
            self.url = vod_1080p_url

            logger.info(self.url)
        except Exception as e:
            P.logger.error("Exception:%s", e)
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
    def get_by_anilife_id(cls, anilife_id):
        return db.session.query(cls).filter_by(anilife_id=anilife_id).first()

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
        item = ModelAniLifeItem()
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
        item.ohli24_info = q["anilife_info"]
        item.save()
