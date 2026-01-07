#!/usr/bin/env python3
"""
Botasaurus 기반 Ohli24 HTML 페칭 스크립트
- gevent monkey-patching과 Trio 간의 충돌을 방지하기 위해 별도 프로세스로 실행
- JSON 출력으로 상위 프로세스(mod_ohli24)와 통신
"""

import sys
import json
import time
import traceback

def fetch_html(url, headers=None, proxy=None):
    result = {"success": False, "html": "", "elapsed": 0}
    start_time = time.time()
    
    try:
        from botasaurus.request import request as b_request
        
        @b_request(headers=headers, use_stealth=True, proxy=proxy)
        def fetch_url(request, data):
            return request.get(data)

        b_resp = fetch_url(url)
        elapsed = time.time() - start_time
        
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
        result["traceback"] = traceback.format_exc()
        result["elapsed"] = round(time.time() - start_time, 2)
        
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: python botasaurus_ohli24.py <url> [headers_json] [proxy]"}))
        sys.exit(1)
    
    target_url = sys.argv[1]
    headers_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
    proxy_arg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    
    res = fetch_html(target_url, headers_arg, proxy_arg)
    print(json.dumps(res, ensure_ascii=False))
