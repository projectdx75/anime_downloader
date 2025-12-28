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
        await asyncio.sleep(0.2)
    return None, None

async def _run_browser(browser, detail_url, episode_num, result):
    """최적화된 브라우저 작업 수행"""
    start_time_all = asyncio.get_event_loop().time()
    page = await browser.new_page()
    
    # 공격적 리소스 및 트래킹 차단
    async def intercept(route):
        req_url = route.request.url.lower()
        resource_type = route.request.resource_type
        
        # 차단 목록: 이미지, 미디어, 폰트, 스타일시트, 분석/광고 스크립트
        block_patterns = ["google-analytics", "googletagmanager", "facebook.net", "ads"]
        block_types = ["image", "media", "font", "stylesheet"]
        
        if resource_type in block_types or any(p in req_url for p in block_patterns):
            await route.abort()
        else:
            await route.continue_()
    
    await page.route("**/*", intercept)
    
    try:
        # 1. Detail 페이지 이동
        t_nav_start = asyncio.get_event_loop().time()
        print(f"1. Navigating: {detail_url}", file=sys.stderr)
        await page.goto(detail_url, wait_until="commit", timeout=15000)
        print(f"   Navigation took: {round(asyncio.get_event_loop().time() - t_nav_start, 2)}s", file=sys.stderr)
        
        # 2. 에피소드 링크 찾기 및 클릭
        t_find_start = asyncio.get_event_loop().time()
        print(f"2. Searching episode {episode_num}...", file=sys.stderr)
        episode_link = None
        for _ in range(20): # 약 4초
            try:
                # epl-num 텍스트 매칭
                episode_link = page.locator(f'a:has(.epl-num:text("{episode_num}"))').first
                if await episode_link.is_visible():
                    break
                
                # 대체: provider 링크
                links = await page.locator('a[href*="/ani/provider/"]').all()
                for link in links:
                    if episode_num in await link.inner_text():
                        episode_link = link
                        break
                if episode_link: break
            except: pass
            await asyncio.sleep(0.2)
        
        if not episode_link:
            result["error"] = f"Episode {episode_num} not found"
            return result

        print(f"   Finding link took: {round(asyncio.get_event_loop().time() - t_find_start, 2)}s", file=sys.stderr)

        # 3. 에피소드 클릭
        t_click_start = asyncio.get_event_loop().time()
        await episode_link.click()
        
        # 4. _aldata 추출 (최대 6초 폴링)
        aldata, source = await _wait_for_aldata(page, timeout=6)
        
        if aldata:
            elapsed = asyncio.get_event_loop().time() - start_time_all
            result.update({
                "aldata": aldata, "success": True, 
                "elapsed": round(elapsed, 2), "source": source
            })
            print(f"   SUCCESS! Extracted via {source} in {result['elapsed']}s", file=sys.stderr)
            return result
            
        # 5. 최후의 수단: 플레이어 버튼 클릭 시도
        print(f"   Initial extraction failed ({round(asyncio.get_event_loop().time() - t_click_start, 2)}s). Trying player button...", file=sys.stderr)
        btn = page.locator('a[onclick*="moveCloudvideo"], a[onclick*="moveJawcloud"]').first
        if await btn.is_visible(timeout=1500):
            await btn.click()
            aldata, source = await _wait_for_aldata(page, timeout=4)
            if aldata:
                elapsed = asyncio.get_event_loop().time() - start_time_all
                result.update({
                    "aldata": aldata, "success": True, 
                    "elapsed": round(elapsed, 2), "source": f"{source}-player"
                })
                print(f"   SUCCESS! Got aldata via player in {result['elapsed']}s", file=sys.stderr)
                return result

        result["error"] = "Aldata extraction failed"
            
    finally:
        await page.close()
    
    return result

async def extract_aldata(detail_url: str, episode_num: str) -> dict:
    """AsyncCamoufox Stealth-Headless mode"""
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as e:
        return {"error": f"Camoufox not installed: {e}"}
    
    result = {"success": False, "aldata": None, "elapsed": 0}
    
    try:
        # Camoufox는 headless=True에서도 강력한 스텔스를 제공함 (Xvfb 오버헤드 불필요)
        async with AsyncCamoufox(headless=True) as browser:
            return await _run_browser(browser, detail_url, episode_num, result)
            
    except Exception as e:
        result["error"] = str(e)
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    
    # stdout에는 오직 JSON만 출력하도록 보장
    try:
        res = asyncio.run(extract_aldata(sys.argv[1], sys.argv[2]))
        # 최종 JSON 결과 출력
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "success": False, "elapsed": 0}))
