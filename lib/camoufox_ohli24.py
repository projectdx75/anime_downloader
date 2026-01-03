#!/usr/bin/env python3
"""
Camoufox 기반 Ohli24 HTML 페칭 스크립트
- Cloudflare 우회를 위한 헤드리스 브라우저 폴백
- curl_cffi 실패 시 사용
- JSON 출력으로 안정적인 IPC
"""

import sys
import json
import asyncio


async def fetch_html(url: str, timeout: int = 30) -> dict:
    """AsyncCamoufox로 HTML 페칭"""
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as e:
        return {"success": False, "error": f"Camoufox not installed: {e}", "html": ""}
    
    result = {"success": False, "html": "", "elapsed": 0}
    start_time = asyncio.get_event_loop().time()
    
    try:
        async with AsyncCamoufox(headless=True) as browser:
            page = await browser.new_page()
            
            # 불필요한 리소스 차단 (속도 향상)
            async def intercept(route):
                resource_type = route.request.resource_type
                if resource_type in ["image", "media", "font"]:
                    await route.abort()
                else:
                    await route.continue_()
            
            await page.route("**/*", intercept)
            
            try:
                # 페이지 로드
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                
                # HTML 추출
                html = await page.content()
                elapsed = asyncio.get_event_loop().time() - start_time
                
                result.update({
                    "success": True,
                    "html": html,
                    "elapsed": round(elapsed, 2)
                })
                
            finally:
                await page.close()
                
    except Exception as e:
        result["error"] = str(e)
        result["elapsed"] = round(asyncio.get_event_loop().time() - start_time, 2)
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: python camoufox_ohli24.py <url>", "html": ""}))
        sys.exit(1)
    
    target_url = sys.argv[1]
    timeout_sec = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    
    try:
        res = asyncio.run(fetch_html(target_url, timeout_sec))
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e), "html": "", "elapsed": 0}))
