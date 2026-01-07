import asyncio
import zendriver as zd
import json
import os

async def test():
    try:
        browser = await zd.start(headless=True)
        page = await browser.get("about:blank")
        
        # Test header setting
        headers = {"Referer": "https://v2.linkkf.app/"}
        try:
            await page.send(zd.cdp.network.enable())
            headers_obj = zd.cdp.network.Headers(headers)
            await page.send(zd.cdp.network.set_extra_http_headers(headers_obj))
            print("Successfully set headers")
        except Exception as e:
            print(f"Failed to set headers: {e}")
            import traceback
            traceback.print_exc()

        methods = [m for m in dir(page) if not m.startswith("_")]
        print(json.dumps({"methods": methods}))
        await browser.stop()
    except Exception as e:
        import traceback
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))

if __name__ == "__main__":
    asyncio.run(test())
