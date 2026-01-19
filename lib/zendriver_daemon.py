#!/usr/bin/env python3
"""
Zendriver 데몬 서버
- 브라우저를 상시 유지하여 빠른 HTML 페칭
- HTTP API로 요청 받아 처리
- 4~6초 → 2~3초 속도 향상 기대
"""

import sys
import json
import asyncio
import signal
import time
import os
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Lock
from typing import Any, Optional, Dict, List, Type, cast
import zendriver as zd

# 터미널 및 파일로 로그 출력 설정
LOG_FILE: str = "/tmp/zendriver_daemon.log"

def log_debug(msg: str) -> None:
    """타임스탬프와 함께 로그 출력 및 파일 저장"""
    timestamp: str = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg: str = f"[{timestamp}] {msg}"
    print(formatted_msg, file=sys.stderr)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception:
        pass

DAEMON_PORT: int = 19876
browser: Optional[Any] = None
browser_lock: Lock = Lock()
loop: Optional[asyncio.AbstractEventLoop] = None
manual_browser_path: Optional[str] = None


def find_browser_executable() -> List[str]:
    """시스템에서 브라우저 실행 파일 찾기 (OS별 대응)"""
    import platform
    import shutil
    
    # 수동 설정된 경로 최우선
    if manual_browser_path and os.path.exists(manual_browser_path):
        return [manual_browser_path]
        
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


class ZendriverHandler(BaseHTTPRequestHandler):
    """HTTP 요청 핸들러"""
    
    def log_message(self, format: str, *args: Any) -> None:
        """로그 출력 억제"""
        pass
    
    def do_POST(self) -> None:
        """POST 요청 처리 (/fetch, /health, /shutdown)"""
        global browser, loop
        
        if self.path == "/fetch":
            try:
                content_length: int = int(self.headers.get('Content-Length', 0))
                if content_length == 0:
                    self._send_json(400, {"success": False, "error": "Empty body"})
                    return
                
                body_bytes: bytes = self.rfile.read(content_length)
                body: str = body_bytes.decode('utf-8')
                data: Dict[str, Any] = json.loads(body)
                
                url: Optional[str] = data.get("url")
                headers: Optional[Dict[str, str]] = data.get("headers")
                timeout: int = cast(int, data.get("timeout", 30))
                
                if not url:
                    self._send_json(400, {"success": False, "error": "Missing 'url' parameter"})
                    return
                
                # 비동기 fetch 실행
                if loop:
                    future = asyncio.run_coroutine_threadsafe(
                        fetch_with_browser(url, timeout, headers), loop
                    )
                    result: Dict[str, Any] = future.result(timeout=timeout + 15)
                    self._send_json(200, result)
                else:
                    self._send_json(500, {"success": False, "error": "Event loop not ready"})
                
            except Exception as e:
                log_debug(f"[Handler] Error: {e}\n{traceback.format_exc()}")
                self._send_json(500, {
                    "success": False, 
                    "error": str(e) or e.__class__.__name__, 
                    "traceback": traceback.format_exc()
                })
        
        elif self.path == "/health":
            self._send_json(200, {"status": "ok", "browser_ready": browser is not None})
        
        elif self.path == "/shutdown":
            self._send_json(200, {"status": "shutting_down"})
            Thread(target=lambda: (time.sleep(0.5), os._exit(0))).start()
        
        else:
            self._send_json(404, {"error": "Not found"})
    
    def do_GET(self) -> None:
        """GET 요청 처리 (/health)"""
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "browser_ready": browser is not None})
        else:
            self._send_json(404, {"error": "Not found"})
    
    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        """JSON 응답 전송"""
        try:
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            log_debug(f"[Handler] Failed to send response: {e}")


async def ensure_browser() -> Any:
    """브라우저 인스턴스 확인/생성"""
    global browser
    
    with browser_lock:
        if browser is None:
            try:
                # 존재하는 후보군 가져오기
                candidates = find_browser_executable()
                if not candidates:
                    log_debug("[ZendriverDaemon] No browser candidates found!")
                    return None
                
                # 리눅스/도커 성능 분석용 로그
                import platform
                if platform.system() == "Linux":
                    try:
                        shm_size = os.statvfs('/dev/shm')
                        free_shm = (shm_size.f_bavail * shm_size.f_frsize) / (1024 * 1024)
                        log_debug(f"[ZendriverDaemon] Linux detected. /dev/shm free: {free_shm:.1f} MB")
                    except Exception as shm_e:
                        log_debug(f"[ZendriverDaemon] Failed to check /dev/shm: {shm_e}")

                # 사용자 데이터 디렉토리 설정 (Mac/Root 권한 이슈 대응)
                import tempfile
                import platform
                uid = os.getuid() if hasattr(os, 'getuid') else 'win'
                
                log_debug(f"[ZendriverDaemon] Environment: Python {sys.version.split()[0]} on {platform.system()}")
                
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
                    "--disable-blink-features=AutomationControlled",
                    # 추가적인 도커 최적화 플래그
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--no-zygote",
                    "--disable-extensions",
                    "--wasm-tier-up=false",
                ]
                
                # 추가적인 리소스 블로킹 설정
                # Note: zendriver supports direct CDP commands
                
                for exec_path in candidates:
                    user_data_dir = os.path.join(tempfile.gettempdir(), f"zd_daemon_{uid}_{os.path.basename(exec_path).replace(' ', '_')}")
                    os.makedirs(user_data_dir, exist_ok=True)
                    
                    try:
                        log_debug(f"[ZendriverDaemon] Trying browser at: {exec_path}")
                        start_time_init = time.time()
                        browser = await zd.start(
                            headless=True, 
                            browser_executable_path=exec_path, 
                            no_sandbox=True,
                            user_data_dir=user_data_dir,
                            browser_args=browser_args
                        )
                        log_debug(f"[ZendriverDaemon] Browser started successfully in {time.time() - start_time_init:.2f}s using: {exec_path}")
                        return browser
                    except Exception as e:
                        log_debug(f"[ZendriverDaemon] Failed to start {exec_path}: {e}")
                        browser = None
                
                raise Exception("All browser candidates failed to start")
            except Exception as e:
                log_debug(f"[ZendriverDaemon] Failed to start browser: {e}")
                browser = None
                raise
    
    return browser


async def fetch_with_browser(url: str, timeout: int = 30, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """상시 대기 브라우저로 HTML 페칭 (탭 유지 방식, 헤더 지원)"""
    global browser
    
    result: Dict[str, Any] = {"success": False, "html": "", "elapsed": 0.0}
    start_time: float = time.time()
    
    try:
        init_start = time.time()
        await ensure_browser()
        init_elapsed = time.time() - init_start
        
        if browser is None:
            result["error"] = "Browser not available"
            return result
        
        log_debug(f"[ZendriverDaemon] Fetching URL: {url} (Init: {init_elapsed:.2f}s)")
        
        try:
            nav_start = time.time()
            # zendriver는 browser.get(url)로 페이지 로드
            
            page: Any = None
            html_content = ""
            nav_elapsed = 0.0
            poll_elapsed = 0.0
            
            # 페이지 로드 시도
            try:
                # zendriver/core/browser.py:304 에서 self.targets가 비어있을 때 StopIteration 발생 가능
                # 이를 방지하기 위해 tabs가 생길 때까지 잠시 대기하거나 직접 생성 시도
                
                # 탭(페이지) 확보
                page = None
                for attempt in range(5):
                    try:
                        if browser.tabs:
                            page = browser.tabs[0]
                            log_debug(f"[ZendriverDaemon] Using existing tab (Attempt {attempt+1})")
                            break
                        else:
                            log_debug(f"[ZendriverDaemon] No tabs found, trying browser.get('about:blank') (Attempt {attempt+1})")
                            page = await browser.get("about:blank")
                            break
                    except (StopIteration, RuntimeError, Exception) as tab_e:
                        log_debug(f"[ZendriverDaemon] Tab acquisition failed: {tab_e}. Retrying...")
                        await asyncio.sleep(0.5)
                
                if not page:
                    result["error"] = "Failed to acquire browser tab"
                    return result

                # 헤더 설정 (CDP 사용)
                if headers:
                    try:
                        log_debug(f"[ZendriverDaemon] Setting headers: {list(headers.keys())}")
                        await page.send(zd.cdp.network.enable())
                        # Wrap dict with Headers type for CDP compatibility
                        cdp_headers = zd.cdp.network.Headers(headers)
                        await page.send(zd.cdp.network.set_extra_http_headers(cdp_headers))
                    except Exception as e:
                        log_debug(f"[ZendriverDaemon] Failed to set headers: {e}")

                # 실제 페이지 로드
                await asyncio.wait_for(page.get(url), timeout=20)
                nav_elapsed = time.time() - nav_start
            except asyncio.TimeoutError:
                log_debug(f"[ZendriverDaemon] Navigation timeout after 20s")
                nav_elapsed = 20.0
            
            # 컨텐츠 완전 로드 대기 (폴링)
            poll_start = time.time()
            if page:
                max_wait = 10  # 최대 10초 대기
                poll_interval = 0.3
                waited = 0
                last_length = 0
                stable_count = 0
                
                while waited < max_wait:
                    try:
                        html_content = await page.get_content()
                        current_length = len(html_content) if html_content else 0
                        
                        # 충분히 긴 컨텐츠 + 마커 발견시 즉시 탈출
                        if current_length > 50000:
                            if "post-list" in html_content or "list-box" in html_content or "post-row" in html_content:
                                log_debug(f"[ZendriverDaemon] List page ready in {waited:.1f}s (len: {current_length})")
                                break
                            if "cdndania" in html_content or "fireplayer" in html_content:
                                log_debug(f"[ZendriverDaemon] Player ready in {waited:.1f}s (len: {current_length})")
                                break
                        
                        # 컨텐츠 길이가 안정화됐는지 체크
                        if current_length > 1000 and current_length == last_length:
                            stable_count += 1
                            if stable_count >= 3:  # 연속 3회 동일하면 로드 완료
                                log_debug(f"[ZendriverDaemon] Content stabilized at {current_length} bytes")
                                break
                        else:
                            stable_count = 0
                        
                        last_length = current_length
                        
                    except Exception as e:
                        log_debug(f"[ZendriverDaemon] get_content error during poll: {e}")
                    
                    await asyncio.sleep(poll_interval)
                    waited += poll_interval
                
                # 최종 컨텐츠 가져오기
                if not html_content or len(html_content) < 1000:
                    try:
                        html_content = await page.get_content()
                    except Exception as e:
                        log_debug(f"[ZendriverDaemon] Final get_content failed: {e}")
            
            poll_elapsed = time.time() - poll_start
            total_elapsed = time.time() - start_time
            
            # 최소 길이 임계값 (사이트마다 페이지 크기가 다름)
            min_acceptable_length = 10000
            
            if html_content and len(html_content) > min_acceptable_length:
                result.update({
                    "success": True,
                    "html": html_content,
                    "elapsed": round(total_elapsed, 2),
                    "metrics": {
                        "init": round(init_elapsed, 2),
                        "nav": round(nav_elapsed, 2),
                        "poll": round(poll_elapsed, 2)
                    }
                })
                log_debug(f"[ZendriverDaemon] Success in {total_elapsed:.2f}s (Nav: {nav_elapsed:.2f}s, Poll: {poll_elapsed:.2f}s, Length: {len(html_content)})")
            else:
                result["error"] = f"Short response: {len(html_content) if html_content else 0} bytes"
                result["elapsed"] = round(total_elapsed, 2)
                log_debug(f"[ZendriverDaemon] Fetch failure: Short response ({len(html_content) if html_content else 0} bytes)")
            
            # 탭 정리: 닫지 말고 about:blank로 리셋 (최소 1개 탭 유지 필요)
            if page:
                try:
                    await page.get("about:blank")
                except Exception as e:
                    log_debug(f"[ZendriverDaemon] Tab reset failed: {e}")
            
        except StopIteration:
            log_debug("[ZendriverDaemon] StopIteration caught during browser.get, resetting browser")
            browser = None
            raise
            
    except BaseException as e:
        # StopIteration 등 모든 예외 캐치
        err_msg: str = str(e) or e.__class__.__name__
        result["error"] = err_msg
        result["elapsed"] = round(time.time() - start_time, 2)
        log_debug(f"[ZendriverDaemon] Exception during fetch: {err_msg}")
        if not isinstance(e, asyncio.CancelledError):
             log_debug(traceback.format_exc())
        
        # 브라우저 오류 시 재시작 플래그
        if "browser" in err_msg.lower() or "closed" in err_msg.lower() or "stopiteration" in err_msg.lower():
            log_debug("[ZendriverDaemon] Resetting browser due to critical error")
            browser = None
    
    return result


async def run_async_loop() -> None:
    """비동기 이벤트 루프 실행"""
    global loop
    loop = asyncio.get_event_loop()
    
    log_debug("[ZendriverDaemon] Async loop started")
    
    # 브라우저 미리 시작
    try:
        await ensure_browser()
    except Exception as e:
        log_debug(f"[ZendriverDaemon] Initial browser start failed: {e}")
    
    # 루프 유지
    while True:
        await asyncio.sleep(1)


def run_server() -> None:
    """HTTP 서버 실행"""
    try:
        server: HTTPServer = HTTPServer(('127.0.0.1', DAEMON_PORT), ZendriverHandler)
        log_debug(f"[ZendriverDaemon] HTTP server starting on port {DAEMON_PORT}")
        server.serve_forever()
    except Exception as e:
        log_debug(f"[ZendriverDaemon] HTTP server error: {e}")


def signal_handler(sig: int, frame: Any) -> None:
    """종료 시그널 처리"""
    global browser
    log_debug("\n[ZendriverDaemon] Shutdown signal received")
    if browser:
        try:
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(browser.stop(), loop)
                future.result(timeout=5)
        except Exception as e:
            log_debug(f"[ZendriverDaemon] Error during browser stop: {e}")
    sys.exit(0)


if __name__ == "__main__":
    # 인자 처리
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser_path", type=str, default=None)
    args = parser.parse_args()
    
    if args.browser_path:
        manual_browser_path = args.browser_path
        log_debug(f"[ZendriverDaemon] Manual browser path set: {manual_browser_path}")

    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 비동기 루프를 별도 스레드에서 실행
    async_thread: Thread = Thread(target=lambda: asyncio.run(run_async_loop()), daemon=True)
    async_thread.start()
    
    # HTTP 서버 실행 (메인 스레드)
    time.sleep(2)  # 초기화 대기
    run_server()
