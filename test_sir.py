import asyncio
from playwright.async_api import Playwright, async_playwright


async def run(playwright: Playwright) -> None:
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    # Open new page
    page = await context.new_page()
    # Go to https://sir.kr/
    await page.goto("https://sir.kr/")
    await asyncio.sleep(1)
    # Click [placeholder="아이디"]
    await page.locator('[placeholder="아이디"]').click()
    # Fill [placeholder="아이디"]
    await page.locator('[placeholder="아이디"]').fill("tongki77")
    # Press Tab
    await page.locator('[placeholder="아이디"]').press("Tab")
    # Fill [placeholder="비밀번호"]
    await page.locator('[placeholder="비밀번호"]').fill("sir98766")
    # Click input:has-text("로그인")
    await page.locator('input:has-text("로그인")').click()
    # await expect(page).to_have_url("https://sir.kr/")
    # Click text=출석 2
    await asyncio.sleep(2)
    await page.locator("text=출석 2").click()
    await asyncio.sleep(2)
    # ---------------------
    await context.close()
    await browser.close()


async def main() -> None:
    async with async_playwright() as playwright:
        await run(playwright)


asyncio.run(main())
