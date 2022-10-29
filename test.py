from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

# from playwright_stealth import stealth_sync
import asyncio
import html_to_json


async def run(playwright):

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://anilife.live/",
        # "Cookie": "SPSI=ef307b8c976fac3363cdf420c9ca40a9; SPSE=+PhK0/uGUBMCZIgXplNjzqW3K2kXLybiElDTtOOiboHiBXO7Tp/9roMW7FplGZuGCUo3i4Fwx5VIUG57Zj6VVw==; anilife_csrf=b1eb92529839d7486169cd91e4e60cd2; UTGv2=h45f897818578a5664b31004b95a9992d273; _ga=GA1.1.281412913.1662803695; _ga_56VYJJ7FTM=GS1.1.1662803695.1.0.1662803707.0.0.0; DCST=pE9; DSR=w2XdPUpwLWDqkLpWXfs/5TiO4mtNv5O3hqNhEr7GP1kFoRBBzbFRpR+xsJd9A+E29M+we7qIvJxQmHQTjDNLuQ==; DCSS=696763EB4EA5A67C4E39CFA510FE36F19B0912C; DGCC=RgP; spcsrf=8a6b943005d711258f2f145a8404d873; sp_lit=F9PWLXyxvZbOyk3eVmtTlg==; PRLST=wW; adOtr=70fbCc39867"
        # "Cookie": ""
        # "Cookie": "_ga=GA1.1.578607927.1660813724; __gads=ID=10abb8b98b6828ae-2281c943a9d500fd:T=1660813741:RT=1660813741:S=ALNI_MYU_iB2lBgSrEQUBwhKpNsToaqQ8A; SL_G_WPT_TO=ko; SL_GWPT_Show_Hide_tmp=1; SL_wptGlobTipTmp=1; SPSI=944c237cdd8606d80e5e330a0f332d03; SPSE=itZcXMDuso0ktWnDkV2G0HVwWEctCgDjrcFMlEQ5C745wqvp1pEEddrsAsjPUBjl6/8+9Njpq1IG3wt/tVag7w==; sbtsck=jav9aILa6Ofn0dEQr5DhDq5rpbd1JUoNgKwxBpZrqYd+CM=; anilife_csrf=54ee9d15c87864ee5e2538a63d894ad6; UTGv2=h46b326af644f4ac5d0eb1502881136b3750; DCST=pE9; __gpi=UID=000008ba227e99e0:T=1660813741:RT=1661170429:S=ALNI_MaJHIVJIGpQ5nTE9lvypKQxJnn10A; DSR=GWyTLTvSMF/lQD77ojQkGyl+7JvTudkSwV1GKeNVUcWEBa/msln9zzsBj7lj+89ywSRBM34Ol73AKf+KHZ9bZA==; DCSS=9D44115EC4CE12CADB88A005DC65A3CD74A211E; DGCC=zdV; spcsrf=fba136251afc6b5283109fc920322c70; sp_lit=kw0Xkp66eQ7bV0f0tNClhg==; PRLST=gt; adOtr=2C4H9c4d78d; _ga_56VYJJ7FTM=GS1.1.1661168661.18.1.1661173389.0.0.0",
    }
    useragent = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
    }

    browser = await playwright.webkit.launch(headless=False)
    # context = browser.new_context(
    #     user_agent=ua,
    # )

    # url = "https://anilife.live/h/live?p=7ccd9e49-9f59-4976-b5d8-25725d6a6188&a=none&player=jawcloud"
    url = "https://api-svr-01.anilife.live/m3u8/st/MDk5NzUyNjY3NTkwZTc3ZmYwMGRmNGIyMzk3MGZiNzU1YjBkNjk2YTFiMzJiZTVhZWZjYjg3NGY4YmE3NTkyMDRkNTU1Y2RjMDhkZTkwNWZiMzZiMTI3ZjE5Zjk0YzQ3MjgzYmUxMTIzZTM2OTllMWZlMzZjM2I1OTIxMmNkNmZmODUxOWZhY2JiMzUxYmE4ZjVjOTMyNzFiYzA0YWI1OTNjZWU0NzMwOTJmYTA4NGU1ZDM1YTlkODA5NzljOTMxNTVhYjlmMmQwMWIwOGMyMTg1N2UyOWJjYjZjN2UwNzJkNjBiOGQzNzc4NTZlZjlkNTQwMDQ5MjgyOGQzYjQxN2M1YmIzYmZiYWYwNGQ0M2U5YmIwMjc4NjgyN2I4M2M1ZDFjOWUxMjM3MjViZDJlZDM3MGI0ZmJkNDE2MThhYTY2N2JlZDllNjQwNTg4MGIxZjBmYTYzMTU4ZTJlZmI1Zg==/dKtKWqgJFnmS-1XShKtsaJWn_OMY1F_HdGDxH2w38mQ/1662826054"
    #
    # if referer is not None:
    #     LogicAniLife.headers["Referer"] = referer

    # context = browser.new_context(extra_http_headers=LogicAniLife.headers)
    # context = await browser.new_context()
    context = await browser.new_context(extra_http_headers=headers)
    # LogicAniLife.headers["Cookie"] = cookie_value

    # context.set_extra_http_headers(LogicAniLife.headers)

    page = await context.new_page()

    # page.on("request", set_cookie)
    # stealth_sync(page)
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(2000)
    # time.sleep(1)
    # page.reload()

    # time.sleep(10)
    cookies = context.cookies
    # print(cookies)

    # print(page.content())
    # vod_url = await page.evaluate(
    #     """() => {
    #     return console.log(vodUrl_1080p) }"""
    # )
    # vod_url1 = await page.evaluate(
    #     """async () =>{
    # return _0x55265f(0x99) + alJson[_0x55265f(0x91)]
    # }"""
    # )
    # print(vod_url)
    # print(vod_url1)
    html_content = await page.content()
    # print(await page.content())
    # print(f"html_content:: {html_content}")
    output_json = html_to_json.convert(html_content)
    print(output_json)
    print(f"output_json:: {output_json['html'][0]['body'][0]['_value']}")


async def main():
    async with async_playwright() as p:
        await run(p)


from loguru import logger
import snoop


class Calc:
    @staticmethod
    # @logger.catch()
    @snoop
    def add(a, b):
        return a + b


cal = Calc()
cal.add(1, 2)  # return 3
