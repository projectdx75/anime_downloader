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
                timeout: int = cast(int, data.get("timeout", 30))
                
                if not url:
                    self._send_json(400, {"success": False, "error": "Missing 'url' parameter"})
                    return
                
                # 비동기 fetch 실행
                if loop:
                    future = asyncio.run_coroutine_threadsafe(
                        fetch_with_browser(url, timeout), loop
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
                uid = os.getuid() if hasattr(os, 'getuid') else 'win'
                
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


async def fetch_with_browser(url: str, timeout: int = 30) -> Dict[str, Any]:
    """상시 대기 브라우저로 HTML 페칭 (탭 유지 방식)"""
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
            # zendriver는 browser.get(url)로 페이지 로드 (완료까지 기다림)
            # 병렬 폴링 대신, asyncio.wait_for로 타임아웃 걸고 빠른 탈출 조건 체크
            
            page: Any = None
            html_content = ""
            nav_elapsed = 0.0
            poll_elapsed = 0.0
            
            # 먼저 타임아웃 내에 페이지 로드 시도
            try:
                page = await asyncio.wait_for(browser.get(url), timeout=20)
                nav_elapsed = time.time() - nav_start
            except asyncio.TimeoutError:
                log_debug(f"[ZendriverDaemon] Navigation timeout after 20s")
                # 타임아웃 됐어도 현재 탭에서 컨텐츠를 가져와볼 수 있음
                nav_elapsed = 20.0
            
            # 컨텐츠 가져오기
            poll_start = time.time()
            if page:
                try:
                    html_content = await page.get_content()
                except Exception as e:
                    log_debug(f"[ZendriverDaemon] get_content failed: {e}")
            
            poll_elapsed = time.time() - poll_start
            total_elapsed = time.time() - start_time
            
            # 조기 탈출 조건 로깅
            if html_content:
                if "post-list" in html_content or "list-box" in html_content or "post-row" in html_content:
                    log_debug(f"[ZendriverDaemon] List page detected in {total_elapsed:.1f}s")
                elif "cdndania" in html_content or "fireplayer" in html_content:
                    log_debug(f"[ZendriverDaemon] Player detected in {total_elapsed:.1f}s")
            
            if html_content and len(html_content) > 100:
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
            
            # 탭 정리 (탭이 너무 쌓이지 않게)
            
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
