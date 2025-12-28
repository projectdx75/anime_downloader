#!/usr/bin/env python3
"""
Camoufox 기반 Anilife 비디오 URL 추출 스크립트 (최적화 비동기 버전)
"""

import sys
import json
import asyncio
import re
import os

async def _wait_for_aldata(page, timeout=10):
    """_aldata 변수가 나타날 때까지 폴링 (최대 timeout초)"""
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            # 1. JS 변수 확인
            aldata = await page.evaluate("typeof _aldata !== 'undefined' ? _aldata : null")
            if aldata:
                return aldata, "JS"
            
            # 2. HTML 소스 패턴 확인
            html = await page.content()
            match = re.search(r'_aldata\s*=\s*["\']([A-Za-z0-9+/=]+)["\']', html)
            if match:
                return match.group(1), "HTML"
        except:
            pass
        await asyncio.sleep(0.3)
    return None, None

async def _run_browser(browser, detail_url, episode_num, result):
    """최적화된 브라우저 작업 수행"""
    # 1. 컨텍스트 및 페이지 생성 (이미지/CSS 차단 옵션 적용 가능 시 적용)
    page = await browser.new_page()
    
    # 리소스 차단 (속도 향상의 핵심)
    async def intercept(route):
        if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
            await route.abort()
        else:
            await route.continue_()
    
    await page.route("**/*", intercept)
    
    try:
        # 1. Detail 페이지 이동
        print(f"1. Navigating to detail page: {detail_url}", file=sys.stderr)
        await page.goto(detail_url, wait_until="commit", timeout=20000) # domcontentloaded보다 빠른 commit 대기
        
        # 2. 에피소드 링크 찾기 (폴링 대기)
        print(f"2. Searching for episode {episode_num}...", file=sys.stderr)
        episode_link = None
        for _ in range(25): # 약 5초간 대기
            try:
                episode_link = page.locator(f'a:has(.epl-num:text("{episode_num}"))').first
                if await episode_link.is_visible():
                    break
                
                # 대체 수단: provider 링크 검색
                links = await page.locator('a[href*="/ani/provider/"]').all()
                for link in links:
                    text = await link.inner_text()
                    if episode_num in text:
                        episode_link = link
                        break
                if episode_link: break
            except: pass
            await asyncio.sleep(0.2)
        
        if not episode_link:
            result["error"] = f"Episode {episode_num} not found"
            result["html"] = await page.content()
            return result

        # 3. 에피소드 클릭 및 이동
        print(f"3. Clicking episode {episode_num}", file=sys.stderr)
        await episode_link.click()
        
        # 4. _aldata 추출 (폴링)
        print("4. Waiting for _aldata...", file=sys.stderr)
        aldata, source = await _wait_for_aldata(page, timeout=8)
        
        if aldata:
            result["aldata"] = aldata
            result["success"] = True
            result["current_url"] = page.url
            print(f"   SUCCESS! Got _aldata from {source}", file=sys.stderr)
            return result
            
        # 5. 추출 실패 시 CloudVideo 버튼 강제 클릭 시도
        print("5. Aldata not found yet. Trying player button...", file=sys.stderr)
        await page.mouse.wheel(0, 500)
        btn = page.locator('a[onclick*="moveCloudvideo"], a[onclick*="moveJawcloud"]').first
        if await btn.is_visible(timeout=2000):
            await btn.click()
            aldata, source = await _wait_for_aldata(page, timeout=5)
            if aldata:
                result["aldata"] = aldata
                result["success"] = True
                result["current_url"] = page.url
                return result

        result["error"] = "Could not extract aldata"
        result["html"] = await page.content()
        result["current_url"] = page.url
            
    finally:
        await page.close()
    
    return result

async def extract_aldata(detail_url: str, episode_num: str) -> dict:
    """AsyncCamoufox로 최적화된 추출 수행"""
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as e:
        return {"error": f"Camoufox not installed: {e}"}
    
    result = {"success": False, "aldata": None, "current_url": None, "error": None}
    
    try:
        has_display = os.environ.get('DISPLAY') is not None
        camou_args = {"headless": False}
        if not has_display:
            camou_args["xvfb"] = True
        
        # 속도 최 최적화를 위한 추가 인자 (필요 시)
        try:
            async with AsyncCamoufox(**camou_args) as browser:
                return await _run_browser(browser, detail_url, episode_num, result)
        except TypeError:
            # xvfb 미지원 버전 대비
            async with AsyncCamoufox(headless=True) as browser:
                return await _run_browser(browser, detail_url, episode_num, result)
            
    except Exception as e:
        result["error"] = str(e)
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    
    detail_url = sys.argv[1]
    episode_num = sys.argv[2]
    
    res = asyncio.run(extract_aldata(detail_url, episode_num))
    print(json.dumps(res, ensure_ascii=False))
