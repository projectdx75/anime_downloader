"""
cdndania.com CDN 전용 다운로더 (curl_cffi 사용)
- 동일한 세션(TLS 핑거프린트)으로 m3u8 추출과 세그먼트 다운로드 수행
- CDN 보안 검증 우회
- subprocess로 분리 실행하여 Flask 블로킹 방지
"""
import os
import sys
import time
import json
import logging
import subprocess
import tempfile
import threading
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


class CdndaniaDownloader:
    """cdndania.com 전용 다운로더 (세션 기반 보안 우회)"""
    
    def __init__(self, iframe_src, output_path, referer_url=None, callback=None, proxy=None):
        self.iframe_src = iframe_src  # cdndania.com 플레이어 iframe URL
        self.output_path = output_path
        self.referer_url = referer_url or "https://ani.ohli24.com/"
        self.callback = callback
        self.proxy = proxy
        self.cancelled = False
        
        # 진행 상황 추적
        self.start_time = None
        self.total_bytes = 0
        self.current_speed = 0
        self.process = None
        
    def download(self):
        """subprocess로 다운로드 실행 (Flask 블로킹 방지)"""
        try:
            # 현재 파일 경로 (subprocess에서 실행할 스크립트)
            script_path = os.path.abspath(__file__)
            
            # 진행 상황 파일
            progress_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            progress_path = progress_file.name
            progress_file.close()
            
            # subprocess 실행
            cmd = [
                sys.executable, script_path,
                self.iframe_src,
                self.output_path,
                self.referer_url or "",
                self.proxy or "",
                progress_path
            ]
            
            logger.info(f"Starting download subprocess: {self.iframe_src}")
            logger.info(f"Output: {self.output_path}")
            logger.info(f"Progress file: {progress_path}")
            
            # subprocess 시작 (non-blocking)
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.start_time = time.time()
            last_callback_time = 0
            
            # 진행 상황 모니터링 (별도 스레드 불필요, 메인에서 폴링)
            while self.process.poll() is None:
                if self.cancelled:
                    self.process.terminate()
                    try:
                        os.unlink(progress_path)
                    except:
                        pass
                    return False, "Cancelled by user"
                
                # 진행 상황 읽기 (0.5초마다)
                current_time = time.time()
                if current_time - last_callback_time >= 0.5:
                    last_callback_time = current_time
                    try:
                        if os.path.exists(progress_path):
                            with open(progress_path, 'r') as f:
                                content = f.read().strip()
                                if content:
                                    progress = json.loads(content)
                                    if self.callback and progress.get('percent', 0) > 0:
                                        self.callback(
                                            percent=progress.get('percent', 0),
                                            current=progress.get('current', 0),
                                            total=progress.get('total', 0),
                                            speed=progress.get('speed', ''),
                                            elapsed=progress.get('elapsed', '')
                                        )
                    except (json.JSONDecodeError, IOError):
                        pass
                
                time.sleep(0.1)  # CPU 사용률 줄이기
            
            # 프로세스 종료 후 결과 확인
            stdout, stderr = self.process.communicate()
            
            # 진행 상황 파일 삭제
            try:
                os.unlink(progress_path)
            except:
                pass
            
            if self.process.returncode == 0:
                # 출력 파일 확인
                if os.path.exists(self.output_path):
                    file_size = os.path.getsize(self.output_path)
                    if file_size > 10000:  # 10KB 이상
                        logger.info(f"Download completed: {self.output_path} ({file_size / 1024 / 1024:.1f}MB)")
                        return True, "Download completed"
                    else:
                        logger.error(f"Output file too small: {file_size}B")
                        return False, f"Output file too small: {file_size}B"
                else:
                    logger.error(f"Output file not found: {self.output_path}")
                    return False, "Output file not created"
            else:
                # stderr에서 에러 메시지 추출
                error_msg = stderr.strip() if stderr else f"Process exited with code {self.process.returncode}"
                logger.error(f"Download failed: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            logger.error(f"CdndaniaDownloader error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)
    
    def cancel(self):
        """다운로드 취소"""
        self.cancelled = True
        if self.process:
            self.process.terminate()


def _download_worker(iframe_src, output_path, referer_url, proxy, progress_path):
    """실제 다운로드 작업 (subprocess에서 실행)"""
    import sys
    import os
    import time
    import json
    import tempfile
    from urllib.parse import urljoin
    
    # 로깅 설정 (subprocess용)
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s|%(levelname)s|%(name)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )
    log = logging.getLogger(__name__)
    
    def update_progress(percent, current, total, speed, elapsed):
        """진행 상황을 파일에 저장"""
        try:
            with open(progress_path, 'w') as f:
                json.dump({
                    'percent': percent,
                    'current': current,
                    'total': total,
                    'speed': speed,
                    'elapsed': elapsed
                }, f)
        except:
            pass
    
    def format_speed(bytes_per_sec):
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
    
    def format_time(seconds):
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}초"
        elif seconds < 3600:
            return f"{seconds // 60}분 {seconds % 60}초"
        else:
            return f"{seconds // 3600}시간 {(seconds % 3600) // 60}분"
    
    try:
        # curl_cffi 임포트
        try:
            from curl_cffi import requests as cffi_requests
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "curl_cffi", "-q"], 
                         timeout=120, check=True)
            from curl_cffi import requests as cffi_requests
        
        # 세션 생성 (Chrome 120 TLS 핑거프린트 사용)
        session = cffi_requests.Session(impersonate="chrome120")
        
        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}
        
        # 1. iframe URL에서 video_id 추출
        video_id = None
        if "/video/" in iframe_src:
            video_id = iframe_src.split("/video/")[1].split("?")[0].split("&")[0]
        elif "/v/" in iframe_src:
            video_id = iframe_src.split("/v/")[1].split("?")[0].split("&")[0]
        
        if not video_id:
            print(f"Could not extract video ID from: {iframe_src}", file=sys.stderr)
            sys.exit(1)
        
        log.info(f"Extracted video_id: {video_id}")
        
        # 2. 플레이어 페이지 먼저 방문 (세션/쿠키 획득)
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "referer": referer_url,
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
        }
        
        log.info(f"Visiting iframe page: {iframe_src}")
        resp = session.get(iframe_src, headers=headers, proxies=proxies, timeout=30)
        log.info(f"Iframe page status: {resp.status_code}")
        
        # 3. getVideo API 호출
        api_url = f"https://cdndania.com/player/index.php?data={video_id}&do=getVideo"
        api_headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "referer": iframe_src,
            "origin": "https://cdndania.com",
            "accept": "application/json, text/javascript, */*; q=0.01",
        }
        post_data = {
            "hash": video_id,
            "r": referer_url
        }
        
        log.info(f"Calling video API: {api_url}")
        api_resp = session.post(api_url, headers=api_headers, data=post_data, 
                               proxies=proxies, timeout=30)
        
        if api_resp.status_code != 200:
            print(f"API request failed: HTTP {api_resp.status_code}", file=sys.stderr)
            sys.exit(1)
        
        try:
            data = api_resp.json()
        except:
            print(f"Failed to parse API response: {api_resp.text[:200]}", file=sys.stderr)
            sys.exit(1)
        
        video_url = data.get("videoSource") or data.get("securedLink")
        if not video_url:
            print(f"No video URL in API response: {data}", file=sys.stderr)
            sys.exit(1)
        
        log.info(f"Got video URL: {video_url}")
        
        # 4. m3u8 다운로드 (동일 세션 유지!)
        m3u8_headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "referer": iframe_src,
            "origin": "https://cdndania.com",
            "accept": "*/*",
        }
        
        log.info(f"Fetching m3u8: {video_url}")
        m3u8_resp = session.get(video_url, headers=m3u8_headers, proxies=proxies, timeout=30)
        
        if m3u8_resp.status_code != 200:
            print(f"m3u8 fetch failed: HTTP {m3u8_resp.status_code}", file=sys.stderr)
            sys.exit(1)
        
        m3u8_content = m3u8_resp.text
        
        # Master playlist 확인
        if "#EXT-X-STREAM-INF" in m3u8_content:
            # 가장 높은 품질의 미디어 플레이리스트 URL 추출
            base = video_url.rsplit('/', 1)[0] + '/'
            last_url = None
            for line in m3u8_content.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    if line.startswith('http'):
                        last_url = line
                    else:
                        last_url = urljoin(base, line)
            
            if last_url:
                log.info(f"Following media playlist: {last_url}")
                m3u8_resp = session.get(last_url, headers=m3u8_headers, proxies=proxies, timeout=30)
                m3u8_content = m3u8_resp.text
                video_url = last_url
        
        # 5. 세그먼트 URL 파싱
        base = video_url.rsplit('/', 1)[0] + '/'
        segments = []
        for line in m3u8_content.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                if line.startswith('http'):
                    segments.append(line)
                else:
                    segments.append(urljoin(base, line))
        
        if not segments:
            print("No segments found in m3u8", file=sys.stderr)
            sys.exit(1)
        
        log.info(f"Found {len(segments)} segments")
        
        # 6. 세그먼트 다운로드
        start_time = time.time()
        last_speed_time = start_time
        total_bytes = 0
        last_bytes = 0
        current_speed = 0
        
        with tempfile.TemporaryDirectory() as temp_dir:
            segment_files = []
            total_segments = len(segments)
            
            log.info(f"Temp directory: {temp_dir}")
            
            for i, segment_url in enumerate(segments):
                segment_path = os.path.join(temp_dir, f"segment_{i:05d}.ts")
                
                # 매 20개마다 또는 첫 5개 로그
                if i < 5 or i % 20 == 0:
                    log.info(f"Downloading segment {i+1}/{total_segments}")
                
                try:
                    seg_resp = session.get(segment_url, headers=m3u8_headers, 
                                          proxies=proxies, timeout=120)
                    
                    if seg_resp.status_code != 200:
                        time.sleep(0.5)
                        seg_resp = session.get(segment_url, headers=m3u8_headers, 
                                              proxies=proxies, timeout=120)
                    
                    segment_data = seg_resp.content
                    
                    if len(segment_data) < 100:
                        print(f"CDN security block: segment {i} returned {len(segment_data)}B", file=sys.stderr)
                        sys.exit(1)
                    
                    with open(segment_path, 'wb') as f:
                        f.write(segment_data)
                    
                    segment_files.append(f"segment_{i:05d}.ts")
                    total_bytes += len(segment_data)
                    
                    # 속도 계산
                    current_time = time.time()
                    if current_time - last_speed_time >= 1.0:
                        bytes_diff = total_bytes - last_bytes
                        time_diff = current_time - last_speed_time
                        current_speed = bytes_diff / time_diff if time_diff > 0 else 0
                        last_speed_time = current_time
                        last_bytes = total_bytes
                    
                    # 진행률 업데이트
                    percent = int(((i + 1) / total_segments) * 100)
                    elapsed = format_time(current_time - start_time)
                    update_progress(percent, i + 1, total_segments, format_speed(current_speed), elapsed)
                    
                except Exception as e:
                    log.error(f"Segment {i} download error: {e}")
                    print(f"Segment {i} download failed: {e}", file=sys.stderr)
                    sys.exit(1)
            
            # 7. ffmpeg로 합치기
            log.info("Concatenating segments with ffmpeg...")
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, 'w') as f:
                for seg_file in segment_files:
                    f.write(f"file '{seg_file}'\n")
            
            # 출력 디렉토리 생성
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', 'concat.txt',
                '-c', 'copy',
                os.path.abspath(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                   timeout=600, cwd=temp_dir)
            
            if result.returncode != 0:
                print(f"FFmpeg concat failed: {result.stderr[:200]}", file=sys.stderr)
                sys.exit(1)
            
            # 출력 파일 확인
            if not os.path.exists(output_path):
                print("Output file not created", file=sys.stderr)
                sys.exit(1)
            
            file_size = os.path.getsize(output_path)
            if file_size < 10000:
                print(f"Output file too small: {file_size}B", file=sys.stderr)
                sys.exit(1)
            
            log.info(f"Download completed: {output_path} ({file_size / 1024 / 1024:.1f}MB)")
            update_progress(100, total_segments, total_segments, "", format_time(time.time() - start_time))
            sys.exit(0)
            
    except Exception as e:
        import traceback
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


# CLI 및 subprocess 엔트리포인트
if __name__ == "__main__":
    if len(sys.argv) >= 6:
        # subprocess 모드
        iframe_url = sys.argv[1]
        output_path = sys.argv[2]
        referer = sys.argv[3] if sys.argv[3] else None
        proxy = sys.argv[4] if sys.argv[4] else None
        progress_path = sys.argv[5]
        
        _download_worker(iframe_url, output_path, referer, proxy, progress_path)
    elif len(sys.argv) >= 3:
        # CLI 테스트 모드
        logging.basicConfig(level=logging.DEBUG)
        
        iframe_url = sys.argv[1]
        output_path = sys.argv[2]
        referer = sys.argv[3] if len(sys.argv) > 3 else None
        proxy = sys.argv[4] if len(sys.argv) > 4 else None
        
        def progress_callback(percent, current, total, speed, elapsed):
            print(f"\r[{percent:3d}%] {current}/{total} segments - {speed} - {elapsed}", end="", flush=True)
        
        downloader = CdndaniaDownloader(
            iframe_src=iframe_url,
            output_path=output_path,
            referer_url=referer,
            callback=progress_callback,
            proxy=proxy
        )
        
        success, message = downloader.download()
        print()
        print(f"Result: {'SUCCESS' if success else 'FAILED'} - {message}")
    else:
        print("Usage: python cdndania_downloader.py <iframe_url> <output_path> [referer_url] [proxy]")
        sys.exit(1)
