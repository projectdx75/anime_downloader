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
import os
import shutil


def find_browser_executable(manual_path=None):
    """시스템에서 브라우저 실행 파일 찾기 (Docker/Ubuntu 환경 대응)"""
    # 수동 설정 시 우선
    if manual_path and os.path.exists(manual_path):
        return manual_path
        
    common_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/lib/chromium-browser/chromium-browser",
    ]
    
    # 먼저 절대 경로 확인
    for path in common_paths:
        if os.path.exists(path):
            return path
            
    # shutil.which로 PATH 확인
    for cmd in ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]:
        found = shutil.which(cmd)
        if found:
            return found
            
    return None


async def fetch_html(url: str, timeout: int = 60, browser_path: str = None) -> dict:
    """Zendriver로 HTML 페칭"""
    try:
        import zendriver as zd
    except ImportError as e:
        return {"success": False, "error": f"Zendriver not installed: {e}. Run: pip install zendriver", "html": ""}
    
    result = {"success": False, "html": "", "elapsed": 0}
    start_time = asyncio.get_event_loop().time()
    browser = None
    
    try:
        # 실행 가능한 브라우저 찾기
        exec_path = find_browser_executable(browser_path)
        
        # 브라우저 시작
        if exec_path:
            browser = await zd.start(
                headless=True, 
                browser_executable_path=exec_path, 
                no_sandbox=True,
                browser_args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-first-run"]
            )
        else:
            browser = await zd.start(
                headless=True, 
                no_sandbox=True,
                browser_args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-first-run"]
            )
            
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
    manual_path = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        res = asyncio.run(fetch_html(target_url, timeout_sec, manual_path))
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e), "html": "", "elapsed": 0}))
