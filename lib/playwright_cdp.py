#!/usr/bin/env python3
"""
Chrome 디버그 모드에 연결하여 Anilife 비디오 URL 추출
Detail 페이지 → 에피소드 클릭 → _aldata 추출 플로우

사용법:
    1. Chrome 디버그 모드 실행:
       /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome_debug
    
    2. 스크립트 실행:
       python playwright_cdp.py <detail_url> <episode_num>
"""

import sys
import json
import time
import re

def extract_aldata_via_cdp(detail_url: str, episode_num: str) -> dict:
    """Chrome DevTools Protocol로 연결하여 _aldata 추출"""
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return {"error": f"Playwright not installed: {e}"}
    
    result = {
        "success": False,
        "aldata": None,
        "html": None,
        "current_url": None,
        "error": None,
        "vod_url": None
    }
    
    try:
        with sync_playwright() as p:
            # Chrome 디버그 포트에 연결
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            
            # 기존 컨텍스트 사용
            contexts = browser.contexts
            if not contexts:
                context = browser.new_context()
            else:
                context = contexts[0]
            
            # 새 페이지 열기
            page = context.new_page()
            
            try:
                # 1. Detail 페이지로 이동
                print(f"1. Navigating to detail page: {detail_url}", file=sys.stderr)
                page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                
                print(f"   Current URL: {page.url}", file=sys.stderr)
                
                # 2. 에피소드 목록으로 스크롤
                page.mouse.wheel(0, 800)
                time.sleep(1)
                
                # 3. 해당 에피소드 찾아서 클릭
                print(f"2. Looking for episode {episode_num}", file=sys.stderr)
                
                # 에피소드 링크 찾기 (provider 링크 중에서)
                episode_clicked = False
                try:
                    # 방법 1: epl-num 클래스의 div에서 에피소드 번호 찾기
                    episode_link = page.locator(f'a:has(.epl-num:text("{episode_num}"))').first
                    if episode_link.is_visible(timeout=5000):
                        href = episode_link.get_attribute("href")
                        print(f"   Found episode link: {href}", file=sys.stderr)
                        episode_link.click()
                        episode_clicked = True
                        time.sleep(3)
                except Exception as e:
                    print(f"   Method 1 failed: {e}", file=sys.stderr)
                
                if not episode_clicked:
                    try:
                        # 방법 2: provider 링크들 중에서 에피소드 번호가 포함된 것 클릭
                        links = page.locator('a[href*="/ani/provider/"]').all()
                        for link in links:
                            text = link.inner_text()
                            if episode_num in text:
                                print(f"   Found: {text}", file=sys.stderr)
                                link.click()
                                episode_clicked = True
                                time.sleep(3)
                                break
                    except Exception as e:
                        print(f"   Method 2 failed: {e}", file=sys.stderr)
                
                if not episode_clicked:
                    result["error"] = f"Episode {episode_num} not found"
                    result["html"] = page.content()
                    return result
                
                # 4. Provider 페이지에서 _aldata 추출
                print(f"3. Provider page URL: {page.url}", file=sys.stderr)
                result["current_url"] = page.url
                
                # _aldata 추출 시도
                try:
                    aldata_value = page.evaluate("typeof _aldata !== 'undefined' ? _aldata : null")
                    if aldata_value:
                        result["aldata"] = aldata_value
                        result["success"] = True
                        print(f"   SUCCESS! _aldata found: {aldata_value[:60]}...", file=sys.stderr)
                        return result
                except Exception as js_err:
                    print(f"   JS error: {js_err}", file=sys.stderr)
                
                # HTML에서 _aldata 패턴 추출 시도
                html = page.content()
                aldata_match = re.search(r'_aldata\s*=\s*["\']([A-Za-z0-9+/=]+)["\']', html)
                if aldata_match:
                    result["aldata"] = aldata_match.group(1)
                    result["success"] = True
                    print(f"   SUCCESS! _aldata from HTML: {result['aldata'][:60]}...", file=sys.stderr)
                    return result
                
                # 5. CloudVideo 버튼 클릭 시도
                print("4. Trying CloudVideo button click...", file=sys.stderr)
                try:
                    page.mouse.wheel(0, 500)
                    time.sleep(1)
                    
                    cloudvideo_btn = page.locator('a[onclick*="moveCloudvideo"], a[onclick*="moveJawcloud"]').first
                    if cloudvideo_btn.is_visible(timeout=3000):
                        cloudvideo_btn.click()
                        time.sleep(3)
                        
                        result["current_url"] = page.url
                        print(f"   After click URL: {page.url}", file=sys.stderr)
                        
                        # 플레이어 페이지에서 _aldata 추출
                        try:
                            aldata_value = page.evaluate("typeof _aldata !== 'undefined' ? _aldata : null")
                            if aldata_value:
                                result["aldata"] = aldata_value
                                result["success"] = True
                                print(f"   SUCCESS! _aldata: {aldata_value[:60]}...", file=sys.stderr)
                                return result
                        except:
                            pass
                        
                        # HTML에서 추출
                        html = page.content()
                        aldata_match = re.search(r'_aldata\s*=\s*["\']([A-Za-z0-9+/=]+)["\']', html)
                        if aldata_match:
                            result["aldata"] = aldata_match.group(1)
                            result["success"] = True
                            return result
                            
                        result["html"] = html
                except Exception as click_err:
                    print(f"   Click error: {click_err}", file=sys.stderr)
                    result["html"] = page.content()
                        
            finally:
                page.close()
                
    except Exception as e:
        result["error"] = str(e)
        if "connect" in str(e).lower():
            result["error"] = "Chrome 디버그 모드가 실행 중이 아닙니다."
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python playwright_cdp.py <detail_url> <episode_num>"}))
        sys.exit(1)
    
    detail_url = sys.argv[1]
    episode_num = sys.argv[2]
    result = extract_aldata_via_cdp(detail_url, episode_num)
    print(json.dumps(result, ensure_ascii=False))
