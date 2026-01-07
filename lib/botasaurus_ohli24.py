#!/usr/bin/env python3
"""
Botasaurus 기반 Ohli24 HTML 페칭 스크립트
- gevent monkey-patching과 Trio 간의 충돌을 방지하기 위해 별도 프로세스로 실행
- JSON 출력으로 상위 프로세스(mod_ohli24)와 통신
"""

import sys
import json
import os
import time
import traceback
from typing import Dict, Any, Optional

# 봇사우루스 디버깅 일시정지 방지 및 자동 종료 설정
os.environ["BOTASAURUS_ENV"] = "production"

def fetch_html(url: str, headers: Optional[Dict[str, str]] = None, proxy: Optional[str] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"success": False, "html": "", "elapsed": 0}
    max_retries = 2
    
    try:
        from botasaurus.request import request as b_request
        
        # use_stealth=True 추가하여 탐지 회피 강화
        @b_request(
            proxy=proxy, 
            raise_exception=True, 
            close_on_crash=True
        )
        def fetch_url(request: Any, data: Dict[str, Any]) -> str:
            target_url = data.get('url')
            headers = data.get('headers') or {}
            
            # 기본적인 헤더 보강 (Ohli24 대응 - Cloudflare/TLS Fingerprinting 대응)
            default_headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }
            
            for k, v in default_headers.items():
                if k not in headers and k.lower() not in [hk.lower() for hk in headers]:
                    headers[k] = v
            
            return request.get(target_url, headers=headers, timeout=20)

        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                b_resp: str = fetch_url({'url': url, 'headers': headers})
                elapsed = time.time() - start_time
                
                # 리스트 페이지는 보통 수백KB 이상 (최소 500바이트 체크)
                if b_resp and len(b_resp) > 500:
                    result.update({
                        "success": True,
                        "html": b_resp,
                        "elapsed": round(elapsed, 2),
                        "attempt": attempt + 1
                    })
                    return result
                else:
                    reason = f"Short response ({len(b_resp) if b_resp else 0} bytes)"
                    if attempt < max_retries:
                        time.sleep(1)
                        continue
                    result["error"] = reason
                    result["elapsed"] = round(time.time() - start_time, 2)
            except Exception as inner_e:
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                result["error"] = str(inner_e)
                result["elapsed"] = round(time.time() - start_time, 2)
                
    except Exception as e:
        result["error"] = f"Botasaurus init/import error: {str(e)}"
        result["elapsed"] = 0
        
    return result

if __name__ == "__main__":
    # 모든 stdout을 stderr로 리다이렉트 (라이브러리 로그가 stdout을 오염시키는 것 방지)
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    
    try:
        if len(sys.argv) < 2:
            # 에러 메시지는 출력해야 하므로 다시 복구 후 출력
            sys.stdout = original_stdout
            print(json.dumps({"success": False, "error": "Usage: script.py <url> [headers] [proxy]"}))
            sys.exit(1)
        
        target_url: str = sys.argv[1]
        headers_arg: Optional[Dict[str, str]] = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
        proxy_arg: Optional[str] = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
        
        res: Dict[str, Any] = fetch_html(target_url, headers_arg, proxy_arg)
        
        # 최종 결과 출력 전에만 stdout 복구
        sys.stdout = original_stdout
        print(json.dumps(res, ensure_ascii=False))
    except Exception as fatal_e:
        # 에러 발생 시에도 JSON 형태로 출력하도록 보장
        sys.stdout = original_stdout
        print(json.dumps({
            "success": False, 
            "error": f"Fatal execution error: {str(fatal_e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
