import asyncio
import sys
import json
import re
from camoufox.async_api import AsyncCamoufox

async def test_extraction(detail_url, provider_url):
    print(f"Testing direct navigation with Referer...")
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        
        # 1. Detail page (establish Referer)
        print(f"1. Estabilishing Referer: {detail_url}")
        t1 = asyncio.get_event_loop().time()
        await page.goto(detail_url, wait_until="commit")
        print(f"   Took {round(asyncio.get_event_loop().time() - t1, 2)}s")
        
        # 2. Same-session direct navigation to provider
        print(f"2. Navigating directly to provider: {provider_url}")
        t2 = asyncio.get_event_loop().time()
        await page.goto(provider_url, wait_until="commit")
        print(f"   Took {round(asyncio.get_event_loop().time() - t2, 2)}s")
        
        # 3. Check for aldata
        html = await page.content()
        final_url = page.url
        print(f"Final URL: {final_url}")
        
        if "google.com" in final_url:
            print("FAILED: Redirected to Google (Bot detection triggered)")
        else:
            match = re.search(r'_aldata\s*=\s*["\']([A-Za-z0-9+/=]+)["\']', html)
            if match:
                print("SUCCESS: Got aldata via direct navigation!")
            else:
                print("FAILED: Aldata not found in HTML")

if __name__ == "__main__":
    # Sample URLs for testing
    # Note: These are placeholders, I will use real ones if available from logs
    d_url = "https://anilife.live/detail/id/2967"
    p_url = "https://anilife.live/ani/provider/31db6215-62bb-420a-8d18-9717013854eb"
    
    if len(sys.argv) > 2:
        d_url = sys.argv[1]
        p_url = sys.argv[2]
        
    asyncio.run(test_extraction(d_url, p_url))
