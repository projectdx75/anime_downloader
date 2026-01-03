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
from typing import Any, Optional

DAEMON_PORT: int = 19876
browser: Optional[Any] = None
browser_lock: Lock = Lock()
loop: Optional[asyncio.AbstractEventLoop] = None


class ZendriverHandler(BaseHTTPRequestHandler):
    """HTTP 요청 핸들러"""
    
    def log_message(self, format: str, *args: Any) -> None:
        # 로그 출력 억제
        pass
    
    def do_POST(self) -> None:
        global browser, loop
        
        if self.path == "/fetch":
            try:
                content_length = int(self.headers['Content-Length'])
                body = self.rfile.read(content_length).decode('utf-8')
                data: dict = json.loads(body)
                
                url: Optional[str] = data.get("url")
                timeout: int = data.get("timeout", 30)
                
                if not url:
                    self._send_json(400, {"success": False, "error": "Missing 'url' parameter"})
                    return
                
                # 비동기 fetch 실행
                if loop:
                    result = asyncio.run_coroutine_threadsafe(
                        fetch_with_browser(url, timeout), loop
                    ).result(timeout=timeout + 10)
                    self._send_json(200, result)
                else:
                    self._send_json(500, {"success": False, "error": "Event loop not ready"})
                
            except Exception as e:
                self._send_json(500, {"success": False, "error": str(e), "traceback": traceback.format_exc()})
        
        elif self.path == "/health":
            self._send_json(200, {"status": "ok", "browser_ready": browser is not None})
        
        elif self.path == "/shutdown":
            self._send_json(200, {"status": "shutting_down"})
            Thread(target=lambda: (time.sleep(0.5), os._exit(0))).start()
        
        else:
            self._send_json(404, {"error": "Not found"})
    
    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "browser_ready": browser is not None})
        else:
            self._send_json(404, {"error": "Not found"})
    
    def _send_json(self, status_code: int, data: dict) -> None:
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))


async def ensure_browser() -> Any:
    """브라우저 인스턴스 확인/생성"""
    global browser
    
    with browser_lock:
        if browser is None:
            try:
                import zendriver as zd
                browser = await zd.start(headless=True)
                print(f"[ZendriverDaemon] Browser started", file=sys.stderr)
            except Exception as e:
                print(f"[ZendriverDaemon] Failed to start browser: {e}", file=sys.stderr)
                browser = None
                raise
    
    return browser


async def fetch_with_browser(url: str, timeout: int = 30) -> dict:
    """상시 대기 브라우저로 HTML 페칭"""
    global browser
    
    result: dict = {"success": False, "html": "", "elapsed": 0}
    start_time: float = time.time()
    
    try:
        await ensure_browser()
        
        if browser is None:
            result["error"] = "Browser not available"
            return result
        
        # 새 탭에서 페이지 로드
        page = await browser.get(url)
        
        # 페이지 로드 대기
        await asyncio.sleep(1.5)
        
        # HTML 추출
        html: str = await page.get_content()
        elapsed: float = time.time() - start_time
        
        if html and len(html) > 100:
            result.update({
                "success": True,
                "html": html,
                "elapsed": round(elapsed, 2)
            })
        else:
            result["error"] = f"Short response: {len(html) if html else 0} bytes"
            result["elapsed"] = round(elapsed, 2)
        
        # 탭 닫기 (브라우저는 유지)
        try:
            await page.close()
        except:
            pass
            
    except Exception as e:
        result["error"] = str(e)
        result["elapsed"] = round(time.time() - start_time, 2)
        
        # 브라우저 오류 시 재시작 플래그
        if "browser" in str(e).lower() or "closed" in str(e).lower():
            browser = None
    
    return result


async def run_async_loop() -> None:
    """비동기 이벤트 루프 실행"""
    global loop
    loop = asyncio.get_event_loop()
    
    # 브라우저 미리 시작
    try:
        await ensure_browser()
    except:
        pass
    
    # 루프 유지
    while True:
        await asyncio.sleep(1)


def run_server() -> None:
    """HTTP 서버 실행"""
    server = HTTPServer(('127.0.0.1', DAEMON_PORT), ZendriverHandler)
    print(f"[ZendriverDaemon] Starting on port {DAEMON_PORT}", file=sys.stderr)
    server.serve_forever()


def signal_handler(sig: int, frame: Any) -> None:
    """종료 시그널 처리"""
    global browser
    print("\n[ZendriverDaemon] Shutting down...", file=sys.stderr)
    if browser:
        try:
            asyncio.run(browser.stop())
        except:
            pass
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 비동기 루프를 별도 스레드에서 실행
    async_thread = Thread(target=lambda: asyncio.run(run_async_loop()), daemon=True)
    async_thread.start()
    
    # HTTP 서버 실행 (메인 스레드)
    time.sleep(1)  # 브라우저 시작 대기
    run_server()
