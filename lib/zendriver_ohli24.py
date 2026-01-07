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
    """시스템에서 브라우저 실행 파일 찾기 (OS별 대응)"""
    import platform
    
    # 수동 설정 시 우선
    if manual_path and os.path.exists(manual_path):
        return manual_path
        
    system = platform.system()
    app_dirs = ["/Applications", "/Volumes/WD/Users/Applications"]
    common_paths = []
    
    if system == "Darwin": # Mac
        for base in app_dirs:
            common_paths.extend([
                f"{base}/Google Chrome.app/Contents/MacOS/Google Chrome",
                f"{base}/Chromium.app/Contents/MacOS/Chromium",
                f"{base}/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ])
    elif system == "Windows":
        common_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    else: # Linux/Other
        common_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/lib/chromium-browser/chromium-browser",
        ]
    
    # 존재하는 모든 후보들 반환
    candidates = [p for p in common_paths if os.path.exists(p)]
    
    # PATH에서 찾기 추가
    for cmd in ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium", "chrome", "microsoft-edge"]:
        found = shutil.which(cmd)
        if found and found not in candidates:
            candidates.append(found)
            
    return candidates


async def fetch_html(url: str, timeout: int = 60, browser_path: str = None) -> dict:
    """Zendriver로 HTML 페칭"""
    try:
        import zendriver as zd
    except ImportError as e:
        return {"success": False, "error": f"Zendriver not installed: {e}. Run: pip install zendriver", "html": ""}
    
    result = {"success": False, "html": "", "elapsed": 0}
    start_time = asyncio.get_event_loop().time()
    browser = None
    
    # 실행 가능한 브라우저 후보들 찾기
    candidates = find_browser_executable(browser_path)
    if not candidates:
        return {"success": False, "error": "No browser executable found", "html": ""}
        
    # 사용자 데이터 디렉토리 설정 (Mac/Root 권한 이슈 대응)
    import tempfile
    uid = os.getuid() if hasattr(os, 'getuid') else 'win'
    
    # 공통 브라우저 인자
    browser_args = [
        "--no-sandbox", 
        "--disable-setuid-sandbox", 
        "--disable-dev-shm-usage", 
        "--disable-gpu", 
        "--no-first-run",
        "--no-service-autorun",
        "--password-store=basic",
        "--mute-audio",
        "--disable-notifications",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-client-side-phishing-detection",
        "--disable-default-apps",
        "--disable-hang-monitor",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--no-default-browser-check",
        "--safebrowsing-disable-auto-update",
        "--remote-allow-origins=*",
        "--blink-settings=imagesEnabled=false",
    ]

    last_error = "All candidates failed"
    
    # 여러 브라우저 후보들 시도 (크롬이 이미 실행 중일 때 등의 상황 대비)
    for exec_path in candidates:
        browser = None
        user_data_dir = os.path.join(tempfile.gettempdir(), f"zd_ohli_{uid}_{os.path.basename(exec_path).replace(' ', '_')}")
        os.makedirs(user_data_dir, exist_ok=True)
        
        try:
            # 브라우저 시작
            browser = await zd.start(
                headless=True, 
                browser_executable_path=exec_path, 
                no_sandbox=True,
                user_data_dir=user_data_dir,
                browser_args=browser_args
            )
            
            page = await browser.get(url)
            
            # 페이지 로드 대기 - 지능형 폴링 (최대 10초)
            # 1. 리스트 페이지는 바로 반환, 2. 에피소드 페이지는 플레이어 로딩 대기
            max_wait = 10
            poll_interval = 0.2  # 1.0s -> 0.2s로 단축하여 반응속도 향상
            waited = 0
            html = ""
            
            while waited < max_wait:
                await asyncio.sleep(poll_interval)
                waited += poll_interval
                html = await page.get_content()
                
                # 리스트 페이지 마커 확인 (발견 즉시 탈출)
                if "post-list" in html or "list-box" in html or "post-row" in html:
                    # log_debug(f"[Zendriver] List page detected in {waited:.1f}s")
                    break
                
                # cdndania/fireplayer iframe이 로드되었는지 확인 (에피소드 페이지)
                if "cdndania" in html or "fireplayer" in html:
                    # log_debug(f"[Zendriver] Player detected in {waited:.1f}s")
                    break
            
            elapsed = asyncio.get_event_loop().time() - start_time
            
            if html and len(html) > 100:
                result.update({
                    "success": True,
                    "html": html,
                    "elapsed": round(elapsed, 2)
                })
                # 성공했으므로 루프 종료
                await browser.stop()
                return result
            else:
                last_error = f"Short response from {exec_path}: {len(html) if html else 0} bytes"
                
        except Exception as e:
            last_error = f"Failed with {exec_path}: {str(e)}"
        finally:
            if browser:
                try:
                    await browser.stop()
                except:
                    pass
                    
    result["error"] = last_error
    result["elapsed"] = round(asyncio.get_event_loop().time() - start_time, 2)
    return result
    
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
