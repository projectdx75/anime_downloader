#!/usr/bin/env python3
"""
Camoufox 기반 Anilife 비디오 URL 추출 스크립트
강력한 봇 감지 우회 기능이 있는 스텔스 Firefox

사용법:
    python camoufox_anilife.py <detail_url> <episode_num>
"""

import sys
import json
import time
import re

def extract_aldata(detail_url: str, episode_num: str) -> dict:
    """Camoufox로 Detail 페이지에서 _aldata 추출"""
    
    try:
        from camoufox.sync_api import Camoufox
    except ImportError as e:
        return {"error": f"Camoufox not installed: {e}"}
    
    result = {
        "success": False,
        "aldata": None,
        "html": None,
        "current_url": None,
        "error": None,
        "vod_url": None
    }
    
    try:
        # Camoufox 시작 (자동 fingerprint 생성)
        # Docker/서버 환경에서는 DISPLAY가 없으므로 headless 모드 사용
        import os
        has_display = os.environ.get('DISPLAY') is not None
        use_headless = not has_display
        
        with Camoufox(headless=use_headless) as browser:
            page = browser.new_page()
            
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
                
                episode_clicked = False
                try:
                    # epl-num 클래스의 div에서 에피소드 번호 찾기
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
                        # provider 링크들 중에서 에피소드 번호가 포함된 것 클릭
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
                
                # 리다이렉트 확인
                if "/ani/provider/" not in page.url:
                    result["error"] = f"Redirected to {page.url}"
                    result["html"] = page.content()
                    return result
                
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
                        
                        # 리다이렉트 확인 (구글로 갔는지)
                        if "google.com" in page.url:
                            result["error"] = "Redirected to Google - bot detected"
                            return result
                        
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
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python camoufox_anilife.py <detail_url> <episode_num>"}))
        sys.exit(1)
    
    detail_url = sys.argv[1]
    episode_num = sys.argv[2]
    result = extract_aldata(detail_url, episode_num)
    print(json.dumps(result, ensure_ascii=False))
