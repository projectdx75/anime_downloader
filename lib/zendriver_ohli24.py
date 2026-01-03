#!/usr/bin/env python3
"""
Zendriver 기반 Ohli24 HTML 페칭 스크립트
- Chrome DevTools Protocol 사용 (탐지 어려움)
- Cloudflare 우회를 위한 헤드리스 브라우저 폴백
- curl_cffi/cloudscraper 실패 시 사용
- JSON 출력으로 안정적인 IPC
"""

import sys
import json
import asyncio


async def fetch_html(url: str, timeout: int = 60) -> dict:
    """Zendriver로 HTML 페칭"""
    try:
        import zendriver as zd
    except ImportError as e:
        return {"success": False, "error": f"Zendriver not installed: {e}. Run: pip install zendriver", "html": ""}
    
    result = {"success": False, "html": "", "elapsed": 0}
    start_time = asyncio.get_event_loop().time()
    browser = None
    
    try:
        # 브라우저 시작
        browser = await zd.start(headless=True)
        page = await browser.get(url)
        
        # 페이지 로드 대기 (DOM 안정화)
        await asyncio.sleep(2)
        
        # HTML 추출
        html = await page.get_content()
        elapsed = asyncio.get_event_loop().time() - start_time
        
        if html and len(html) > 100:
            result.update({
                "success": True,
                "html": html,
                "elapsed": round(elapsed, 2)
            })
        else:
            result["error"] = f"Short response: {len(html) if html else 0} bytes"
            result["elapsed"] = round(elapsed, 2)
                
    except Exception as e:
        result["error"] = str(e)
        result["elapsed"] = round(asyncio.get_event_loop().time() - start_time, 2)
    finally:
        if browser:
            try:
                await browser.stop()
            except:
                pass
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: python zendriver_ohli24.py <url>", "html": ""}))
        sys.exit(1)
    
    target_url = sys.argv[1]
    timeout_sec = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    
    try:
        res = asyncio.run(fetch_html(target_url, timeout_sec))
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e), "html": "", "elapsed": 0}))
