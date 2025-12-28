#!/usr/bin/env python3
"""
Camoufox 기반 Anilife 비디오 URL 추출 스크립트 (Ultra-Speed 버전)
- Stealth-Headless 모드 사용 (Xvfb 오버헤드 제거)
- 엄격한 Stdout/Stderr 분리 (JSON 파싱 안정성)
- 공격적 리소스 및 도메인 차단
"""

import sys
import json
import asyncio
import re
import os

async def _wait_for_aldata(page, timeout=8):
    """_aldata 변수가 나타날 때까지 고속 폴링 (50ms)"""
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            # 1. JS 변수 확인 (가장 빠름)
            aldata = await page.evaluate("typeof _aldata !== 'undefined' ? _aldata : null")
            if aldata:
                return aldata, "JS"
            
            # 2. HTML 소스 패턴 확인 (커밋 직후에 바로 걸릴 수 있음)
            html = await page.content()
            match = re.search(r'_aldata\s*=\s*["\']([A-Za-z0-9+/=]+)["\']', html)
            if match:
                return match.group(1), "HTML"
        except:
            pass
        await asyncio.sleep(0.05) # 50ms로 단축
    return None, None

async def _run_browser(browser, detail_url, episode_num, result, provider_url=None):
    """세션 유지 + 직접 리다이렉트 방식 (클릭/새창 없음)"""
    start_time_all = asyncio.get_event_loop().time()
    page = await browser.new_page()
    
    # 리소스 차단 (스크립트는 허용)
    async def intercept(route):
        resource_type = route.request.resource_type
        if resource_type in ["image", "media", "font", "stylesheet"]:
            await route.abort()
        else:
            await route.continue_()
    
    await page.route("**/*", intercept)
    
    try:
        # 1. Detail 페이지 이동 → 세션/쿠키 획득
        t_nav_start = asyncio.get_event_loop().time()
        print(f"1. Session: {detail_url}", file=sys.stderr)
        await page.goto(detail_url, wait_until="commit", timeout=10000)
        print(f"   Done in {round(asyncio.get_event_loop().time() - t_nav_start, 2)}s", file=sys.stderr)
        
        # 2. 에피소드 링크에서 href 추출 (클릭 X)
        t_find_start = asyncio.get_event_loop().time()
        print(f"2. Finding ep {episode_num} link...", file=sys.stderr)
        
        episode_link = page.locator(f'a:has(.epl-num:text("{episode_num}"))').first
        for _ in range(20):
            if await episode_link.is_visible(): break
            await asyncio.sleep(0.1)
        
        # 클릭 방식으로 네비게이션 (직접 URL 접근은 사이트에서 막힘)
        print(f"   Link found in {round(asyncio.get_event_loop().time() - t_find_start, 2)}s. Clicking...", file=sys.stderr)
        await episode_link.click()
        
        # 3. _aldata 추출 (고속 폴링)
        print("3. Extracting _aldata...", file=sys.stderr)
        aldata, source = await _wait_for_aldata(page, timeout=6)
        
        # 버튼 클릭 폴백
        if not aldata:
            print("   Trying player button...", file=sys.stderr)
            btn = page.locator('a[onclick*="moveCloudvideo"], a[onclick*="moveJawcloud"]').first
            for _ in range(20):  # 2초 대기
                if await btn.is_visible(): break
                await asyncio.sleep(0.1)
            if await btn.is_visible():
                await btn.click(force=True)
                aldata, source = await _wait_for_aldata(page, timeout=4)
                if aldata: source = f"{source}-btn"
        
        if aldata:
            elapsed = asyncio.get_event_loop().time() - start_time_all
            result.update({"aldata": aldata, "success": True, "elapsed": round(elapsed, 2), "source": source})
            print(f"   SUCCESS in {result['elapsed']}s ({source})", file=sys.stderr)
            return result
        
        result["error"] = "Failed to extract aldata"
            
    finally:
        await page.close()
    
    return result

async def extract_aldata(detail_url: str, episode_num: str, provider_url: str = None) -> dict:
    """AsyncCamoufox Stealth-Headless mode"""
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as e:
        return {"error": f"Camoufox not installed: {e}"}
    
    result = {"success": False, "aldata": None, "elapsed": 0}
    
    try:
        # Camoufox는 headless=True에서도 강력한 스텔스를 제공함 (Xvfb 오버헤드 불필요)
        async with AsyncCamoufox(headless=True) as browser:
            return await _run_browser(browser, detail_url, episode_num, result, provider_url)
            
    except Exception as e:
        result["error"] = str(e)
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    
    detail_url = sys.argv[1]
    episode_num = sys.argv[2]
    provider_url = sys.argv[3] if len(sys.argv) > 3 else None
    
    # stdout에는 오직 JSON만 출력하도록 보장
    try:
        res = asyncio.run(extract_aldata(detail_url, episode_num, provider_url))
        # 최종 JSON 결과 출력
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "success": False, "elapsed": 0}))
