import asyncio
import os
import platform
import traceback

import cloudscraper
import requests
from loguru import logger

from anime_downloader.lib.util import yommi_timeit


class Crawler:

    def __init__(self):
        self.session = None
        self.headers = {
            # 'authority': 'anilife.live',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'ko-KR,ko;q=0.8',
            'cache-control': 'no-cache',
            'cookie': 'SL_G_WPT_TO=ko; SL_GWPT_Show_Hide_tmp=1; SL_wptGlobTipTmp=1; DSR=WQYVukjkxKVYEbpgM0pgMs+awM/br6JyMtbfB4OGMC0XEA+UxUxR1RUgOi1mNMoQB16xIEuqk64iex+/ahi72A==; DCSS=FEC4550B310816E1CA91CBE4A0069C43E04F108; SPSI=faccf9a99dee9625af1c93607c2be678; SPSE=j3smljSGgZcayyKDFoQKk5/tnnUnFHa9FzCrL6GOkRwsET506JX0hAvzye3rEobnKfHiir8mAw8z7/KG11QQXw==; anilife_csrf=f30c66ba689880e9710a85b1945ad798; UTGv2=h4a5ce301324340f0b03d9e61e42bc6c0416; spcsrf=77a4e9c38c8e7392b7a36818071a5e3e; sp_lit=acrE8Wfvo4cd6GxQyGoytg==; PRLST=RT; adOtr=fZaBf9c9aed',
            # 'pragma': 'no-cache',
            'referer': 'https://anilife.live/g/l?id=afb8c5e4-1720-4f3d-a6b1-27e7473dc6fb',
            # 'sec-fetch-dest': 'document',
            # 'sec-fetch-mode': 'navigate',
            # 'sec-fetch-site': 'same-origin',
            # 'sec-fetch-user': '?1',
            # 'sec-gpc': '1',
            # 'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
        }
        self.origin_url = ''
        self.episode_url = None
        self.OS_PLATFORM = platform.system()

    def get_html_requests(
            self,
            url: str, referer: str = None, stream: str = False, timeout: int = 5
    ) -> str:
        data = ""
        try:
            print("get_html_requests ==================")

            # cj = browser_cookie3.chrome(domain_name="anilife.live")
            referer = "https://anilife.live/"

            if self.session is None:
                self.session = requests.session()

            # logger.debug('get_html :%s', url)
            self.headers["Referer"] = "" if referer is None else referer
            self.headers[
                "Cookie"
            ] = "_ga=GA1.1.578607927.1660813724; __gads=ID=10abb8b98b6828ae-2281c943a9d500fd:T=1660813741:RT=1660813741:S=ALNI_MYU_iB2lBgSrEQUBwhKpNsToaqQ8A; sbtsck=javuwDzcOJqUyweM1OQeNGzHbjoHp7Cgw44XnPdM738c3E=;  SPSI=e48379959d54a6a62cc7abdcafdb2761; SPSE=h5HfMGLJzLqzNafMD3YaOvHSC9xfh77CcWdKvexp/z5N5OsTkIiYSCudQhFffEfk/0pcOTVf0DpeV0RoNopzig==; anilife_csrf=b93b9f25a12a51cf185805ec4de7cf9d; UTGv2=h46b326af644f4ac5d0eb1502881136b3750; __gpi=UID=000008ba227e99e0:T=1660813741:RT=1660912282:S=ALNI_MaJHIVJIGpQ5nTE9lvypKQxJnn10A; DSR=SXPX8ELcRgh6N/9rNgjpQoNfaX2DRceeKYR0/ul7qTI9gApWQpZxr8jgymf/r0HsUT551vtOv2CMWpIn0Hd26A==; DCSS=89508000A76BBD939F6DDACE5BD9EB902D2212A; DGCC=Wdm; adOtr=7L4Xe58995d; spcsrf=6554fa003bf6a46dd9b7417acfacc20a; _ga_56VYJJ7FTM=GS1.1.1660912281.10.1.1660912576.0.0.0; PRLST=EO"

            self.headers["Referer"] = referer

            page_content = self.session.get(
                url, headers=self.headers, timeout=timeout, allow_redirects=True
            )
            data = page_content.text
        except Exception as e:
            logger.error(f"Exception: {e}")
            logger.error(traceback.format_exc())
        return data

    async def get_html_playwright(
            self,
            url: str,
            headless: bool = False,
            referer: str = None,
            engine: str = "chrome",
            stealth: bool = False,
    ):
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

            logger.info(engine)
            async with async_playwright() as p:
                browser = None
                try:
                    if engine == "chrome":
                        browser = await p.chromium.launch(
                            channel="chrome", args=browser_args, headless=headless
                        )
                        print(engine)

                        # browser = await p.chromium.connect('http://192.168.0.2:14444')
                    elif engine == "webkit":
                        browser = await p.webkit.launch(
                            headless=headless,
                            args=browser_args,
                        )
                    else:
                        print('here')
                        browser = await p.firefox.launch(
                            headless=headless,
                            args=browser_args,
                        )

                    # context = browser.new_context(
                    #     user_agent=ua,
                    # )

                    # LogicAniLife.headers[
                    #     "Referer"
                    # ] = "https://anilife.live/detail/id/471"
                    # print(LogicAniLife.headers)

                    self.headers["Referer"] = self.episode_url

                    if referer is not None:
                        self.headers["Referer"] = referer

                    logger.debug(f"self.headers {self.headers}")
                    context = await browser.new_context(
                        extra_http_headers=self.headers
                    )
                    # await context.add_cookies(self.cookies)

                    # self.headers["Cookie"] = cookie_value

                    # context.set_extra_http_headers(self.headers)
                    print('here1')
                    page = await context.new_page()

                    # page.set_extra_http_headers(self.headers)

                    # if stealth:
                    #     await stealth_async(page)

                    # page.on("request", set_cookie)
                    # stealth_sync(page)
                    print(self.headers["Referer"])

                    # page.on("request", set_cookie)

                    print(f'Referer:: {self.headers["Referer"]}')

                    # await page.set_extra_http_headers(self.headers)

                    await page.goto(
                        url, wait_until="load", referer=self.headers["Referer"]
                    )
                    # page.wait_for_timeout(10000)
                    await asyncio.sleep(1)

                    # await page.reload()

                    # time.sleep(10)
                    # cookies = context.cookies
                    # print(cookies)

                    print(f"page.url:: {page.url}")
                    self.origin_url = page.url

                    print(await page.content())

                    print(f"run at {time.time() - start} sec")

                    return await page.content()
                except Exception as e:
                    logger.error(f"Exception: {e}")
                    logger.error(traceback.format_exc())
                finally:
                    await browser.close()

        except Exception as e:
            logger.error(f"Exception: {e}")
            logger.error(traceback.format_exc())
        finally:
            # browser.close()
            pass

    def get_html_playwright_sync(
            self,
            url: str,
            headless: bool = False,
            referer: str = None,
            engine: str = "chrome",
            stealth: bool = False,
    ) -> str:
        try:
            from playwright.sync_api import sync_playwright

            import time

            print("playwright ==========================================")

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

            # headless = True

            with sync_playwright() as p:
                try:
                    if engine == "chrome":
                        # browser = await p.chromium.launch(
                        #     channel="chrome", args=browser_args, headless=headless
                        # )
                        print(engine)

                        # browser = p.chromium.connect_over_cdp('http://yommi.duckdns.org:14444')
                        browser = p.chromium.launch(
                            channel="chrome", args=browser_args, headless=headless
                        )

                    elif engine == "webkit":
                        browser = p.webkit.launch(
                            headless=headless,
                            args=browser_args,
                        )
                    else:
                        browser = p.firefox.launch(
                            headless=headless,
                            args=browser_args,
                        )
                    # context = browser.new_context(
                    #     user_agent=ua,
                    # )

                    self.headers[
                        "Referer"
                    ] = "https://anilife.live/detail/id/471"
                    # print(self.headers)

                    self.headers["Referer"] = self.episode_url

                    if referer is not None:
                        self.headers["Referer"] = referer

                    logger.debug(f"self.headers::: {self.headers}")
                    context = browser.new_context(
                        extra_http_headers=self.headers
                    )
                    # await context.add_cookies(self.cookies)

                    # self.headers["Cookie"] = cookie_value

                    # context.set_extra_http_headers(self.headers)

                    page = context.new_page()

                    # page.set_extra_http_headers(self.headers)

                    if stealth:
                        # stealth_async(page)
                        pass

                    # page.on("request", set_cookie)
                    # stealth_sync(page)
                    print(self.headers["Referer"])

                    page.on("request", set_cookie)

                    print(f'Referer:: {self.headers["Referer"]}')
                    # await page.set_extra_http_headers(self.headers)

                    page.goto(
                        url, wait_until="load", referer=self.headers["Referer"]
                    )
                    # page.wait_for_timeout(10000)
                    time.sleep(1)

                    # await page.reload()

                    # cookies = context.cookies
                    # print(cookies)

                    print(f"page.url:: {page.url}")
                    self.origin_url = page.url

                    print(page.content().encode("utf8"))

                    print(f"run at {time.time() - start} sec")

                    return page.content()
                except Exception as e:
                    logger.error("Exception:%s", e)
                    logger.error(traceback.format_exc())
                finally:
                    browser.close()

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

        @yommi_timeit
        def get_html_selenium(self, url: str, referer: str, is_stealth: bool = False,
                              is_headless: bool = False) -> bytes:
            from selenium.webdriver.common.by import By
            from selenium import webdriver
            from selenium_stealth import stealth
            from webdriver_manager.chrome import ChromeDriverManager
            import time

            print("get_html_selenium() ==========================================")

            options = webdriver.ChromeOptions()
            # 크롬드라이버 헤더 옵션추가 (리눅스에서 실행시 필수)
            options.add_argument("start-maximized")
            if is_headless:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("window-size=1920x1080")
            options.add_argument("disable-gpu")
            # options.add_argument('--no-sandbox')
            options.add_argument("--disable-dev-shm-usage")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("detach", True)
            options.add_experimental_option("useAutomationExtension", False)

            logger.debug(self.OS_PLATFORM)

            driver_bin_path = os.path.join(
                os.path.dirname(__file__), "bin", self.OS_PLATFORM
            )

            # 크롬 드라이버 경로
            driver_path = f"{driver_bin_path}/chromedriver"

            if self.OS_PLATFORM == "Darwin":
                # driver = webdriver.Chrome(executable_path=driver_path, chrome_options=options)
                print("here:::::::::")
                driver = webdriver.Chrome(
                    ChromeDriverManager().install(), chrome_options=options
                )
            elif self.OS_PLATFORM == "Linux":
                driver = webdriver.Chrome(
                    ChromeDriverManager().install(), chrome_options=options
                )
                # driver = webdriver.Chrome(executable_path=driver_path, chrome_options=options)

                # driver = webdriver.Remote(command_executor='http://192.168.0.2:14444', options=options)

            else:
                driver = webdriver.Chrome(
                    executable_path=driver_path, chrome_options=options
                )

            # is_stealth = True
            if is_stealth:
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

            # time.sleep(1)
            #
            # driver.refresh()

            logger.debug(f"current_url:: {driver.current_url}")
            # logger.debug(f"current_cookie:: {driver.get_cookies()}")
            cookies_list = driver.get_cookies()

            cookies_dict = {}
            for cookie in cookies_list:
                cookies_dict[cookie["name"]] = cookie["value"]

            # logger.debug(cookies_dict)
            self.cookies = cookies_list
            # self.headers["Cookie"] = driver.get_cookies()
            self.episode_url = driver.current_url
            time.sleep(1)
            elem = driver.find_element(By.XPATH, "//*")
            source_code = elem.get_attribute("outerHTML")

            logger.debug(source_code)

            driver.close()

            driver.quit()

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
                driver.request_interceptor = self.interceptor
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
            self.headers["Referer"] = "https://anilife.live/"
            self.headers[
                "Cookie"
            ] = "_ga=GA1.1.578607927.1660813724; __gads=ID=10abb8b98b6828ae-2281c943a9d500fd:T=1660813741:RT=1660813741:S=ALNI_MYU_iB2lBgSrEQUBwhKpNsToaqQ8A; sbtsck=javuwDzcOJqUyweM1OQeNGzHbjoHp7Cgw44XnPdM738c3E=;  SPSI=e48379959d54a6a62cc7abdcafdb2761; SPSE=h5HfMGLJzLqzNafMD3YaOvHSC9xfh77CcWdKvexp/z5N5OsTkIiYSCudQhFffEfk/0pcOTVf0DpeV0RoNopzig==; anilife_csrf=b93b9f25a12a51cf185805ec4de7cf9d; UTGv2=h46b326af644f4ac5d0eb1502881136b3750; __gpi=UID=000008ba227e99e0:T=1660813741:RT=1660912282:S=ALNI_MaJHIVJIGpQ5nTE9lvypKQxJnn10A; DSR=SXPX8ELcRgh6N/9rNgjpQoNfaX2DRceeKYR0/ul7qTI9gApWQpZxr8jgymf/r0HsUT551vtOv2CMWpIn0Hd26A==; DCSS=89508000A76BBD939F6DDACE5BD9EB902D2212A; DGCC=Wdm; adOtr=7L4Xe58995d; spcsrf=6554fa003bf6a46dd9b7417acfacc20a; _ga_56VYJJ7FTM=GS1.1.1660912281.10.1.1660912576.0.0.0; PRLST=EO"
            # logger.debug(f"headers:: {LogicAniLife.headers}")

            if self.session is None:
                self.session = requests.Session()
                self.session.headers = self.headers

            # LogicAniLife.session = requests.Session()

            sess = cloudscraper.create_scraper(
                browser={"browser": "firefox", "platform": "windows", "desktop": True},
                debug=False,
                sess=self.session,
                delay=10,
            )

            # print(scraper.get(url, headers=LogicAniLife.headers).content)
            # print(scraper.get(url).content)
            # return scraper.get(url, headers=LogicAniLife.headers).content
            # print(LogicAniLife.headers)
            return sess.get(
                url, headers=self.session.headers, timeout=10, allow_redirects=True
            ).content.decode("utf8", errors="replace")
