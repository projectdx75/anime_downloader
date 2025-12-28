#!/usr/bin/env python3
"""
Playwright 기반 Anilife 비디오 URL 추출 스크립트
FlaskFarm의 gevent와 충돌을 피하기 위해 별도의 subprocess로 실행됩니다.

사용법:
    python playwright_anilife.py <detail_url> <episode_num>
    
출력:
    JSON 형식으로 _aldata 또는 에러 메시지 출력
"""

import sys
import json
import time
import re

def extract_aldata(detail_url: str, episode_num: str) -> dict:
    """Detail 페이지에서 에피소드를 클릭하고 _aldata를 추출합니다."""
    
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
        "player_url": None
    }
    
    try:
        with sync_playwright() as p:
            # 시스템에 설치된 Chrome 사용
            browser = p.chromium.launch(
                headless=False,  # visible 모드
                channel="chrome",  # 시스템 Chrome 사용
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-automation",
                    "--no-sandbox",
                ]
            )
            
            # 브라우저 컨텍스트 생성 (스텔스 설정)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ko-KR",
            )
            
            # navigator.webdriver 숨기기
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = context.new_page()
            
            try:
                # 1. Detail 페이지 방문
                page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                
                # 2. 에피소드 찾아서 클릭 (episode_num을 포함하는 provider 링크)
                episode_clicked = False
                
                # 스크롤하여 에피소드 목록 로드
                page.mouse.wheel(0, 800)
                time.sleep(1)
                
                # JavaScript로 에피소드 링크 찾아 클릭
                try:
                    episode_href = page.evaluate(f"""
                        (() => {{
                            const links = Array.from(document.querySelectorAll('a[href*="/ani/provider/"]'));
                            const ep = links.find(a => a.innerText.includes('{episode_num}'));
                            if (ep) {{
                                ep.click();
                                return ep.href;
                            }}
                            return null;
                        }})()
                    """)
                    if episode_href:
                        episode_clicked = True
                        time.sleep(2)
                except Exception as e:
                    result["error"] = f"Episode click failed: {e}"
                
                if not episode_clicked:
                    result["error"] = f"Episode {episode_num} not found"
                    result["html"] = page.content()
                    return result
                
                # 3. Provider 페이지에서 player_guid 추출 (버튼 클릭 대신)
                # moveCloudvideo() 또는 moveJawcloud() 함수에서 GUID 추출
                try:
                    player_info = page.evaluate("""
                        (() => {
                            // 함수 소스에서 GUID 추출 시도
                            let playerUrl = null;
                            
                            // moveCloudvideo 함수 확인
                            if (typeof moveCloudvideo === 'function') {
                                const funcStr = moveCloudvideo.toString();
                                // URL 패턴 찾기
                                const match = funcStr.match(/['"]([^'"]+\\/h\\/live[^'"]+)['"]/);
                                if (match) {
                                    playerUrl = match[1];
                                }
                            }
                            
                            // moveJawcloud 함수 확인
                            if (!playerUrl && typeof moveJawcloud === 'function') {
                                const funcStr = moveJawcloud.toString();
                                const match = funcStr.match(/['"]([^'"]+\\/h\\/live[^'"]+)['"]/);
                                if (match) {
                                    playerUrl = match[1];
                                }
                            }
                            
                            // 페이지 변수 확인
                            if (!playerUrl && typeof _player_guid !== 'undefined') {
                                playerUrl = '/h/live?p=' + _player_guid + '&player=jawcloud';
                            }
                            
                            // onclick 속성에서 추출
                            if (!playerUrl) {
                                const btn = document.querySelector('a[onclick*="moveCloudvideo"], a[onclick*="moveJawcloud"]');
                                if (btn) {
                                    const onclick = btn.getAttribute('onclick');
                                    // 함수 이름 확인 후 페이지 소스에서 URL 추출
                                }
                            }
                            
                            // 전역 변수 검색
                            if (!playerUrl) {
                                for (const key of Object.keys(window)) {
                                    if (key.includes('player') || key.includes('guid')) {
                                        const val = window[key];
                                        if (typeof val === 'string' && val.match(/^[a-f0-9-]{36}$/)) {
                                            playerUrl = '/h/live?p=' + val + '&player=jawcloud';
                                            break;
                                        }
                                    }
                                }
                            }
                            
                            // _aldata 직접 확인 (provider 페이지에 있을 수 있음)
                            if (typeof _aldata !== 'undefined') {
                                return { aldata: _aldata, playerUrl: null };
                            }
                            
                            return { aldata: null, playerUrl: playerUrl };
                        })()
                    """)
                    
                    if player_info.get("aldata"):
                        result["aldata"] = player_info["aldata"]
                        result["success"] = True
                        result["current_url"] = page.url
                        return result
                    
                    result["player_url"] = player_info.get("playerUrl")
                    
                except Exception as e:
                    result["error"] = f"Player info extraction failed: {e}"
                
                # 4. Player URL이 있으면 해당 페이지로 이동하여 _aldata 추출
                if result.get("player_url"):
                    player_full_url = "https://anilife.live" + result["player_url"] if result["player_url"].startswith("/") else result["player_url"]
                    page.goto(player_full_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(2)
                    
                    # _aldata 추출
                    try:
                        aldata_value = page.evaluate("typeof _aldata !== 'undefined' ? _aldata : null")
                        if aldata_value:
                            result["aldata"] = aldata_value
                            result["success"] = True
                    except Exception as e:
                        pass
                
                # 현재 URL 기록
                result["current_url"] = page.url
                
                # HTML에서 _aldata 패턴 추출 시도
                if not result["aldata"]:
                    html = page.content()
                    # _aldata = "..." 패턴 찾기
                    aldata_match = re.search(r'_aldata\s*=\s*["\']([A-Za-z0-9+/=]+)["\']', html)
                    if aldata_match:
                        result["aldata"] = aldata_match.group(1)
                        result["success"] = True
                    else:
                        result["html"] = html
                    
            finally:
                context.close()
                browser.close()
                
    except Exception as e:
        result["error"] = str(e)
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python playwright_anilife.py <detail_url> <episode_num>"}))
        sys.exit(1)
    
    detail_url = sys.argv[1]
    episode_num = sys.argv[2]
    result = extract_aldata(detail_url, episode_num)
    print(json.dumps(result, ensure_ascii=False))
