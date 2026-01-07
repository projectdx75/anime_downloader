import requests
import json
import re
import sys

def test_fetch():
    url = "https://playv2.sub3.top/r2/play.php?&id=n20&url=405686s1"
    headers = {
        "Referer": "https://linkkf.live/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    daemon_url = "http://127.0.0.1:19876/fetch"
    payload = {
        "url": url,
        "headers": headers,
        "timeout": 30
    }
    
    print(f"Fetching {url} via daemon...")
    try:
        resp = requests.post(daemon_url, json=payload, timeout=40)
        if resp.status_code != 200:
            print(f"Error: HTTP {resp.status_code}")
            print(resp.text)
            return
        
        data = resp.json()
        if not data.get("success"):
            print(f"Fetch failed: {data.get('error')}")
            return
        
        html = data.get("html", "")
        print(f"Fetch success. Length: {len(html)}")
        
        # Save for inspection
        with open("linkkf_player_test.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Saved to linkkf_player_test.html")
        
        # Try regex patterns from mod_linkkf.py
        patterns = [
            r"url:\s*['\"]([^'\"]*\.m3u8[^'\"]*)['\"]",
            r"<source[^>]+src=['\"]([^'\"]*\.m3u8[^'\"]*)['\"]",
            r"src\s*=\s*['\"]([^'\"]*\.m3u8[^'\"]*)['\"]",
            r"url\s*:\s*['\"]([^'\"]+)['\"]"
        ]
        
        found = False
        for p in patterns:
            match = re.search(p, html, re.IGNORECASE)
            if match:
                url_found = match.group(1)
                if ".m3u8" in url_found or "m3u8" in p:
                    print(f"Pattern '{p}' found: {url_found}")
                    found = True
        
        if not found:
            print("No m3u8 found with existing patterns.")
            # Search for any .m3u8
            any_m3u8 = re.findall(r"['\"]([^'\"]*\.m3u8[^'\"]*)['\"]", html)
            if any_m3u8:
                print(f"Generic search found {len(any_m3u8)} m3u8 links:")
                for m in any_m3u8[:5]:
                    print(f"  - {m}")
            else:
                print("No .m3u8 found in generic search either.")
                # Check for other video extensions or potential indicators
                if "Artplayer" in html:
                    print("Artplayer detected.")
                if "video" in html:
                    print("Video tag found.")
                
                # Check for 'cache/'
                if "cache/" in html:
                    print("Found 'cache/' keyword.")
                    cache_links = re.findall(r"['\"]([^'\"]*cache/[^'\"]*)['\"]", html)
                    for c in cache_links:
                        print(f"  - Possible cache link: {c}")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_fetch()
