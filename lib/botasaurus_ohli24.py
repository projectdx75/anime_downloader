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
from typing import Dict, Any, Optional

# 봇사우루스 디버깅 일시정지 방지 및 자동 종료 설정
os.environ["BOTASAURUS_ENV"] = "production"

def fetch_html(url: str, headers: Optional[Dict[str, str]] = None, proxy: Optional[str] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"success": False, "html": "", "elapsed": 0}
    start_time: float = time.time()
    
    try:
        from botasaurus.request import request as b_request
        
        # raise_exception=True는 에러 시 exception을 발생시키게 함
        # close_on_crash=True는 에러 발생 시 대기하지 않고 즉시 종료 (배포 환경용)
        @b_request(proxy=proxy, raise_exception=True, close_on_crash=True)
        def fetch_url(request: Any, data: Dict[str, Any]) -> str:
            target_url = data.get('url')
            headers = data.get('headers') or {}
            
            # 기본적인 헤더 보강 (Ohli24 대응 - Cloudflare 우회 시도)
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
            
            return request.get(target_url, headers=headers, timeout=30)

        # 봇사우루스는 실패 시 자동 재시도 등을 하기도 함.
        # 여기서는 단발성 요청이므로 직접 호출.
        b_resp: str = fetch_url({'url': url, 'headers': headers})
        elapsed: float = time.time() - start_time
        
        if b_resp and len(b_resp) > 10:
            result.update({
                "success": True,
                "html": b_resp,
                "elapsed": round(elapsed, 2)
            })
        else:
            result["error"] = f"Short response: {len(b_resp) if b_resp else 0} bytes"
            result["elapsed"] = round(elapsed, 2)
            
    except Exception as e:
        result["error"] = str(e)
        result["elapsed"] = round(time.time() - start_time, 2)
        
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: python botasaurus_ohli24.py <url> [headers_json] [proxy]"}))
        sys.exit(1)
    
    target_url: str = sys.argv[1]
    headers_arg: Optional[Dict[str, str]] = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
    proxy_arg: Optional[str] = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    
    res: Dict[str, Any] = fetch_html(target_url, headers_arg, proxy_arg)
    print(json.dumps(res, ensure_ascii=False))
