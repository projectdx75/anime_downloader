#!/usr/bin/env python3
"""
Camoufox 기반 Anilife 비디오 URL 추출 스크립트 (비동기 버전)
강력한 봇 감지 우회 기능이 있는 스텔스 Firefox
"""

import sys
import json
import asyncio
import re
import os

async def _run_browser(browser, detail_url, episode_num, result):
    """실제 브라우저 작업을 수행하는 내부 비동기 함수"""
    page = await browser.new_page()
    try:
        # 1. Detail 페이지로 이동
        print(f"1. Navigating to detail page: {detail_url}", file=sys.stderr)
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        print(f"   Current URL: {page.url}", file=sys.stderr)
        
        # 2. 에피소드 목록으로 스크롤
        await page.mouse.wheel(0, 800)
        await asyncio.sleep(1)
        
        # 3. 해당 에피소드 찾아서 클릭
        print(f"2. Looking for episode {episode_num}", file=sys.stderr)
        
        episode_clicked = False
        try:
            # epl-num 클래스의 div에서 에피소드 번호 찾기
            episode_link = page.locator(f'a:has(.epl-num:text("{episode_num}"))').first
            if await episode_link.is_visible(timeout=5000):
                href = await episode_link.get_attribute("href")
                print(f"   Found episode link: {href}", file=sys.stderr)
                await episode_link.click()
                episode_clicked = True
                await asyncio.sleep(3)
        except Exception as e:
            print(f"   Method 1 failed: {e}", file=sys.stderr)
        
        if not episode_clicked:
            try:
                # provider 링크들 중에서 에피소드 번호가 포함된 것 클릭
                links = await page.locator('a[href*="/ani/provider/"]').all()
                for link in links:
                    text = await link.inner_text()
                    if episode_num in text:
                        print(f"   Found: {text}", file=sys.stderr)
                        await link.click()
                        episode_clicked = True
                        await asyncio.sleep(3)
                        break
            except Exception as e:
                print(f"   Method 2 failed: {e}", file=sys.stderr)
        
        if not episode_clicked:
            result["error"] = f"Episode {episode_num} not found"
            result["html"] = await page.content()
            return result
        
        # 4. Provider 페이지에서 _aldata 추출
        print(f"3. Provider page URL: {page.url}", file=sys.stderr)
        result["current_url"] = page.url
        
        # 리다이렉트 확인
        if "/ani/provider/" not in page.url:
            result["error"] = f"Redirected to {page.url}"
            result["html"] = await page.content()
            return result
        
        # _aldata 추출 시도
        try:
            aldata_value = await page.evaluate("typeof _aldata !== 'undefined' ? _aldata : null")
            if aldata_value:
                result["aldata"] = aldata_value
                result["success"] = True
                print(f"   SUCCESS! _aldata found: {aldata_value[:60]}...", file=sys.stderr)
                return result
        except Exception as js_err:
            print(f"   JS error: {js_err}", file=sys.stderr)
        
        # HTML에서 _aldata 패턴 추출 시도
        html_content = await page.content()
        aldata_match = re.search(r'_aldata\s*=\s*["\']([A-Za-z0-9+/=]+)["\']', html_content)
        if aldata_match:
            result["aldata"] = aldata_match.group(1)
            result["success"] = True
            print(f"   SUCCESS! _aldata from HTML: {result['aldata'][:60]}...", file=sys.stderr)
            return result
        
        # 5. CloudVideo 버튼 클릭 시도
        print("4. Trying CloudVideo button click...", file=sys.stderr)
        try:
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(1)
            
            cloudvideo_btn = page.locator('a[onclick*="moveCloudvideo"], a[onclick*="moveJawcloud"]').first
            if await cloudvideo_btn.is_visible(timeout=3000):
                await cloudvideo_btn.click()
                await asyncio.sleep(3)
                
                result["current_url"] = page.url
                print(f"   After click URL: {page.url}", file=sys.stderr)
                
                # 리다이렉트 확인 (구글로 갔는지)
                if "google.com" in page.url:
                    result["error"] = "Redirected to Google - bot detected"
                    return result
                
                # 플레이어 페이지에서 _aldata 추출
                try:
                    aldata_value = await page.evaluate("typeof _aldata !== 'undefined' ? _aldata : null")
                    if aldata_value:
                        result["aldata"] = aldata_value
                        result["success"] = True
                        print(f"   SUCCESS! _aldata: {aldata_value[:60]}...", file=sys.stderr)
                        return result
                except:
                    pass
                
                # HTML에서 추출
                html_content = await page.content()
                aldata_match = re.search(r'_aldata\s*=\s*["\']([A-Za-z0-9+/=]+)["\']', html_content)
                if aldata_match:
                    result["aldata"] = aldata_match.group(1)
                    result["success"] = True
                    return result
                    
                result["html"] = html_content
        except Exception as click_err:
            print(f"   Click error: {click_err}", file=sys.stderr)
            result["html"] = await page.content()
            
    finally:
        await page.close()
    
    return result

async def extract_aldata(detail_url: str, episode_num: str) -> dict:
    """AsyncCamoufox로 Detail 페이지에서 _aldata 추출"""
    
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as e:
        return {"error": f"Camoufox not installed: {e}"}
    
    result = {
        "success": False, "aldata": None, "html": None,
        "current_url": None, "error": None, "vod_url": None
    }
    
    try:
        # Docker/서버 환경에서는 DISPLAY가 없으므로 Xvfb 가상 디스플레이 사용 시도
        has_display = os.environ.get('DISPLAY') is not None
        
        if not has_display:
            print("   No DISPLAY detected. Using Virtual Display (Xvfb) for better stealth.", file=sys.stderr)
            camou_args = {"headless": False, "xvfb": True}
        else:
            camou_args = {"headless": False}
        
        # xvfb 인자 지원 여부에 따른 안전한 실행 (Try-Except Fallback)
        try:
            async with AsyncCamoufox(**camou_args) as browser:
                return await _run_browser(browser, detail_url, episode_num, result)
        except TypeError as e:
            if "xvfb" in str(e):
                print(f"   Warning: Local Camoufox version too old for 'xvfb'. Falling back to headless.", file=sys.stderr)
                async with AsyncCamoufox(headless=True) as browser:
                    return await _run_browser(browser, detail_url, episode_num, result)
            raise e
            
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
    
    # 비동기 실행 루프 시작
    try:
        res = asyncio.run(extract_aldata(detail_url, episode_num))
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "success": False}))
