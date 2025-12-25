import json

from fastapi import FastAPI

import asyncio
import traceback
from typing import Optional, List

from playwright_har_tracer import HarTracer
from pydantic import BaseModel
import sys
import subprocess
import importlib
import uvicorn
from playwright.sync_api import sync_playwright

from playwright.async_api import async_playwright

# pkgs = ["playwright", "playwright_stealth", "playwright_har_tracer", "loguru"]
pkgs = ["playwright", "playwright_stealth", "playwright_har_tracer", "loguru"]
for pkg in pkgs:
    try:
        importlib.import_module(pkg)
    # except ImportError:
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
        )
        # main(["install", pkg])
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        importlib.import_module(pkg)

from loguru import logger

# try:
#     from playwright_stealth import stealth_async
# except:
#     pip install playwright_stealth
#
# try:
#     import html_to_json
# except:
#     pip install html_to_json

# from playwright_har_tracer import HarTracer

import time
import os

user_dir = "tmp/playwright"
user_dir = os.path.join(os.getcwd(), user_dir)

app = FastAPI()

# headers = {
#     # ":authority": "anilife.live",
#     "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36",
#     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
#     "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
#
#     # "Cookie": ""
#     "Cookie": "SL_G_WPT_TO=ko; SL_GWPT_Show_Hide_tmp=1; SL_wptGlobTipTmp=1; DSR=WQYVukjkxKVYEbpgM0pgMs+awM/br6JyMtbfB4OGMC0XEA+UxUxR1RUgOi1mNMoQB16xIEuqk64iex+/ahi72A==; DCSS=FEC4550B310816E1CA91CBE4A0069C43E04F108; SPSI=c9a8435ac1577631126a68a61da5d240; SPSE=aV099+8sLURR7w5MAL1ABihQFpGsh5188ml5NIaMjHbnknx+C/y1qITA7nLCZOTsE67VWb+oacReiz56F3CswA==; anilife_csrf=6e19420853df91fc05732b8be6db4201; UTGv2=h4a5ce301324340f0b03d9e61e42bc6c0416; spcsrf=84aa5294e8eef0a1b2ddac94d3128f29; sp_lit=fggbJYfuR2dVL/kk5POeFA==; PRLST=tw; adOtr=4E9Ccaac551",
# }
headers = {
    # 'authority': 'anilife.live',
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "ko-KR,ko;q=0.8",
    "cache-control": "no-cache",
    # 'cookie': '_ga=GA1.1.578607927.1660813724; __gads=ID=10abb8b98b6828ae-2281c943a9d500fd:T=1660813741:RT=1660813741:S=ALNI_MYU_iB2lBgSrEQUBwhKpNsToaqQ8A; SPSI=5f044d5c641270640d82deeea4c7904a; SPSE=6ysw8BS2tk+H8nN0bo8LOyavaI+InS3i9YuPEzBuEHjrd9GFUl8T3Gd4lg0Wwx/5+zwOrEnqeApQGjdDhqKQiQ==; anilife_csrf=d629470ba1b8a2b81426114a0fd933bb; UTGv2=h46b326af644f4ac5d0eb1502881136b3750; SL_G_WPT_TO=ko; __gpi=UID=000008ba227e99e0:T=1660813741:RT=1668300534:S=ALNI_MaJHIVJIGpQ5nTE9lvypKQxJnn10A; SL_GWPT_Show_Hide_tmp=1; SL_wptGlobTipTmp=1; spcsrf=324bb1134a2ffaeffba5a6d90d4b170d; sp_lit=56vk5DIus4k4khwHctc+NQ==; PRLST=ZY; _ga_56VYJJ7FTM=GS1.1.1668304234.38.1.1668304574.0.0.0; adOtr=44fd5c0Y514',
    # 'pragma': 'no-cache',
    "referer": "https://anilife.live/g/l?id=65bd6132-e480-4599-bfee-37e0e1eb20e9",
    # 'sec-fetch-dest': 'document',
    # 'sec-fetch-mode': 'navigate',
    # 'sec-fetch-site': 'same-origin',
    # 'sec-fetch-user': '?1',
    # 'sec-gpc': '1',
    # 'upgrade-insecure-requests': '1',
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
}

useragent = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
    "like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
}

origin_url = None


class PlParam(BaseModel):
    url: str
    headless: Optional[bool] = False
    referer: Optional[str] = None
    engine: Optional[str] = "chrome"
    stealth: Optional[bool] = (False,)
    reload: Optional[bool] = (False,)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/get_html")
async def get_html():
    pass


def intercept_response(response):
    # we can extract details from background requests
    if response.request.resource_type == "xhr":
        print(response.headers.get("cookie"))
    return response


async def request_event_handler(response):
    # print("HTTP Status code: {}".format(response.status))
    # body = await response.body()
    # print("HTML body page: {}".format(body))
    print("HTTP Cookie")
    custom_cookie = await response.all_headers()
    print(custom_cookie["cookie"])


@app.post("/get_html_by_playwright")
async def get_html_by_playwright(p_param: PlParam):
    # pl_dict = p_param.__dict__

    global headers, origin_url
    logger.debug(headers)
    pl_dict = p_param.dict()

    # logger.debug(pl_dict.engine)\
    # reload: bool = pl_dict['reload']
    logger.debug(pl_dict["engine"])
    try:
        from playwright.async_api import async_playwright

        # from playwright.sync_api import sync_playwright

        import time

        print("** playwright ==========================================")

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
        browser_args = []
        browser = None
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

        # def set_cookie(req):
        #     nonlocal cookie
        #     if "cookie" in req.headers:
        #         cookie = req.headers["cookie"]

        # headless = True

        # print(pl_dict.engine)
        async with async_playwright() as p:
            try:
                if pl_dict["engine"] == "chrome":
                    # browser = await p.chromium.launch(
                    #     channel="chrome", args=browser_args, headless=pl_dict["headless"]
                    # )
                    browser = await p.chromium.launch_persistent_context(
                        channel="chrome",
                        args=browser_args,
                        headless=pl_dict["headless"],
                        user_data_dir=user_dir,
                    )
                    print(pl_dict["engine"])

                    # browser = await p.chromium.connect('http://192.168.0.2:14444')
                if pl_dict["engine"] == "chromium":
                    browser = await p.chromium.launch(
                        channel="chromium",
                        args=browser_args,
                        headless=pl_dict["headless"],
                    )
                    print(pl_dict["engine"])
                elif pl_dict["engine"] == "webkit":
                    browser = await p.webkit.launch(
                        headless=pl_dict["headless"],
                        args=browser_args,
                    )
                else:
                    print("firefox")
                    browser = await p.firefox.launch(
                        headless=pl_dict["headless"],
                        args=browser_args,
                    )

                # context = browser.new_context(
                #     user_agent=ua,
                # )

                # LogicAniLife.headers[
                #     "Referer"
                # ] = "https://anilife.live/detail/id/471"
                # print(LogicAniLife.headers)
                # headers["referer"] = "https://anilife.live/detail/id/471"

                logger.info(headers)
                # context = await browser.new_context(
                #     extra_http_headers=headers
                # )
                # await context.add_cookies(LogicAniLife.cookies)

                # LogicAniLife.headers["Cookie"] = cookie_value

                # create a new incognito browser context
                context = await browser.new_context()
                # create a new page inside context.
                page = await context.new_page()

                # print(cookie)
                # page.on("response", intercept_response)
                # page.on(
                #     "response",
                #     lambda response: asyncio.create_task(request_event_handler(response)),
                # )

                await page.set_extra_http_headers(headers)

                # if stealth:
                #     await stealth_async(page)

                # page.on("request", set_cookie)
                # stealth_sync(page)
                # logger.info(headers["referer"])

                # page.on("request", set_cookie)

                logger.info(f'referer:: {headers["referer"]}')

                logger.info(headers)
                # await page.set_extra_http_headers(LogicAniLife.headers)

                # await page.goto(
                #     pl_dict["url"], wait_until="load", referer=headers["Referer"]
                # )
                await page.goto(pl_dict["url"], wait_until="load")

                # page.wait_for_timeout(10000)
                await asyncio.sleep(2)
                logger.debug(pl_dict["reload"])

                if pl_dict["reload"]:
                    await page.reload()

                await asyncio.sleep(1)
                cookies = await context.cookies()
                # logger.debug(cookie)
                logger.debug(len(cookies))
                json_mylist = json.dumps(cookies, separators=(",", ":"))
                # logger.debug(json_mylist)
                tmp = ""
                for c in cookies:
                    # print(c["name"])
                    # print(c["value"])
                    tmp += f'{c["name"]}={c["value"]}; '

                logger.debug(tmp)
                headers["cookie"] = tmp
                headers["Cookie"] = tmp

                # page.on("response", intercept_response)
                await asyncio.sleep(0.5)
                # time.sleep(10)
                # cookies = context.cookies
                # print(cookies)

                logger.info(f"page.url:: {page.url}")
                _url = page.url
                origin_url = page.url
                headers["referer"] = origin_url
                headers["Referer"] = origin_url

                # origin_url = page.url
                ret_data = await page.content()

                logger.info(f"run at {time.time() - start} sec")
                await page.close()
                # print(ret_data)
                return {"success": "ok", "url": _url, "html": ret_data}

            except Exception as e:
                logger.error(f"Exception: {str(e)}")
                logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"Exception: {str(e)}")
        logger.error(traceback.format_exc())


@app.post("/get_vod_url")
async def get_vod_url(p_param: PlParam):
    pl_dict = p_param.dict()
    # logger.debug(pl_dict.engine)
    logger.debug(pl_dict["engine"])
    har = None
    _headless: bool = False

    if pl_dict["headless"] is not None:
        _headless = pl_dict["headless"]

    try:

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
            # "--use-gl=egl",
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
                browser = await p.chromium.launch(
                    headless=pl_dict["headless"], args=browser_args
                )

                # browser = await p.webkit.launch(headless=headless)
                # context = browser.new_context(
                #     user_agent=ua,
                # )

                # headers[
                #     "Referer"
                # ] = "https://anilife.live/g/l?id=14344143-040a-4e40-9399-a7d22d94554b"
                #
                logger.info(f"headers : {headers}")

                # context = await browser.new_context(extra_http_headers=LogicAniLife.headers)
                context = await browser.new_context()
                await context.set_extra_http_headers(headers)

                # await context.add_cookies(LogicAniLife.cookies)

                tracer = HarTracer(context=context, browser_name=p.chromium.name)
                # tracer = HarTracer(context=context, browser_name=p.webkit.name)

                # LogicAniLife.headers["Cookie"] = cookie_value

                # context.set_extra_http_headers(LogicAniLife.headers)

                page = await context.new_page()

                # await page.set_extra_http_headers(headers)

                # await stealth_async(page)
                # logger.debug(url)

                # page.on("request", set_cookie)
                # stealth_sync(page)
                # await page.goto(
                #     url, wait_until="load", referer=LogicAniLife.headers["Referer"]
                # )
                # await page.goto(url, wait_until="load")
                await page.goto(pl_dict["url"], wait_until="domcontentloaded")

                # await page.reload()

                har = await tracer.flush()

                await context.close()
                await browser.close()

                # page.wait_for_timeout(10000)
                await asyncio.sleep(1)

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

            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())

            result_har_json = har.to_json()
            result_har_dict = har.to_dict()
            logger.debug(result_har_dict)

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


# if __name__ == "__main__":
#     uvicorn.run("main:app", host="0.0.0.0", port=7070, reload=True)
