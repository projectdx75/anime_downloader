"""
cdndania.com CDN 전용 다운로더 (curl_cffi 사용)
- 동일한 세션(TLS 핑거프린트)으로 m3u8 추출과 세그먼트 다운로드 수행
- CDN 보안 검증 우회
- subprocess로 분리 실행하여 Flask 블로킹 방지
"""
from __future__ import annotations

import os
import sys
import time
import json
import logging
import subprocess
import tempfile
import threading
from typing import Callable, Optional, Tuple, Any, IO
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


class CdndaniaDownloader:
    """cdndania.com 전용 다운로더 (세션 기반 보안 우회)"""
    
    def __init__(
        self,
        iframe_src: str,
        output_path: str,
        referer_url: Optional[str] = None,
        callback: Optional[Callable[[int, int, int, str, str], None]] = None,
        proxy: Optional[str] = None,
        threads: int = 16,
        on_download_finished: Optional[Callable[[], None]] = None
    ) -> None:
        self.iframe_src: str = iframe_src  # cdndania.com 플레이어 iframe URL
        self.output_path: str = output_path
        self.referer_url: str = referer_url or "https://ani.ohli24.com/"
        self.callback: Optional[Callable[[int, int, int, str, str], None]] = callback
        self.proxy: Optional[str] = proxy
        self.threads: int = threads
        self.on_download_finished: Optional[Callable[[], None]] = on_download_finished
        self.cancelled: bool = False
        self.released: bool = False  # 조기 반환 여부
        
        # 진행 상황 추적
        self.start_time: Optional[float] = None
        self.total_bytes: int = 0
        self.current_speed: float = 0
        self.process: Optional[subprocess.Popen[str]] = None
        
    def download(self) -> Tuple[bool, str]:
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
                progress_path,
                str(self.threads)
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
            
            # Subprocess 로그 실시간 출력용 스레드
            def log_reader(pipe: IO[str]) -> None:
                try:
                    for line in iter(pipe.readline, ''):
                        if line:
                            logger.info(f"[Worker] {line.strip()}")
                        else:
                            break
                except ValueError:
                    pass

            log_thread = threading.Thread(target=log_reader, args=(self.process.stderr,), daemon=True)
            log_thread.start()
            
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
                                    # 조기 반환 체크 (merging 상태이면 네트워크 완료로 간주)
                                    status = progress.get('status', 'downloading')
                                    if status == 'merging' and not self.released:
                                        if self.on_download_finished:
                                            self.on_download_finished()
                                        self.released = True
                                        
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
    
    def cancel(self) -> None:
        """다운로드 취소"""
        self.cancelled = True
        if self.process:
            self.process.terminate()


def _download_worker(
    iframe_src: str,
    output_path: str,
    referer_url: Optional[str],
    proxy: Optional[str],
    progress_path: str,
    threads: int = 16
) -> None:
    """실제 다운로드 작업 (subprocess에서 실행) - AsyncIO Wrapper"""
    import sys
    import asyncio
    
    # Windows/Mac 등에서 loop 정책 설정이 필요할 수 있음
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try:
        asyncio.run(_download_worker_async(iframe_src, output_path, referer_url, proxy, progress_path, threads))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        import logging
        logging.getLogger(__name__).error(f"AsyncIO Loop Error: {e}")
        traceback.print_exc()
        sys.exit(1)

async def _download_worker_async(
    iframe_src: str,
    output_path: str,
    referer_url: Optional[str],
    proxy: Optional[str],
    progress_path: str,
    threads: int = 16
) -> None:
    """실제 다운로드 작업 (AsyncIO)"""
    import sys
    import os
    import time
    import json
    import tempfile
    import logging
    from urllib.parse import urljoin, urlparse
    import asyncio
    
    # 로깅 설정 (subprocess용)
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s|%(levelname)s|%(name)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )
    log = logging.getLogger(__name__)
    
    # curl_cffi 임포트
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "curl_cffi", "-q"], 
                     timeout=120, check=True)
        from curl_cffi.requests import AsyncSession

    # Progress Update Helper
    def update_progress(
        percent: int,
        current: int,
        total: int,
        speed: str,
        elapsed: str,
        status: Optional[str] = None
    ) -> None:
        try:
            data: dict[str, Any] = {
                'percent': percent,
                'current': current,
                'total': total,
                'speed': speed,
                'elapsed': elapsed
            }
            if status:
                data['status'] = status
            
            with open(progress_path, 'w') as f:
                json.dump(data, f)
        except:
            pass
    
    def format_speed(bytes_per_sec: float) -> str:
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"

    def format_time(seconds: float) -> str:
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}초"
        elif seconds < 3600:
            return f"{seconds // 60}분 {seconds % 60}초"
        else:
            return f"{seconds // 3600}시간 {(seconds % 3600) // 60}분"

    try:
        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        # --- Async Session Context ---
        # impersonate="chrome110"으로 변경 (TLS Fingerprint 변경, Safari 이슈 회피)
        async with AsyncSession(impersonate="chrome110", proxies=proxies) as session:
            
            # 1. iframe URL에서 video_id 추출
            video_id = None
            if "/video/" in iframe_src:
                video_id = iframe_src.split("/video/")[1].split("?")[0].split("&")[0]
            elif "/v/" in iframe_src:
                video_id = iframe_src.split("/v/")[1].split("?")[0].split("&")[0]
            
            if not video_id:
                log.error(f"Could not extract video ID from: {iframe_src}")
                sys.exit(1)
            
            log.info(f"Extracted video_id: {video_id}")
            
            # 2. 플레이어 페이지 먼저 방문 (세션/쿠키 획득)
            headers = {
                # "user-agent": "...", # impersonate가 알아서 설정함
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "referer": referer_url,
                # "sec-ch-ua": ..., # 제거
                # "sec-ch-ua-mobile": "?0",
                # "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "iframe",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "cross-site",
            }
            
            log.info(f"Visiting iframe page: {iframe_src}")
            resp = await session.get(iframe_src, headers=headers)
            log.info(f"Iframe page status: {resp.status_code}")
            
            parsed_iframe = urlparse(iframe_src)
            cdn_base_url = f"{parsed_iframe.scheme}://{parsed_iframe.netloc}"

            # 3. getVideo API 호출
            api_url = f"{cdn_base_url}/player/index.php?data={video_id}&do=getVideo"
            api_headers = {
                # "user-agent": ..., 
                "x-requested-with": "XMLHttpRequest",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "referer": iframe_src,
                "origin": cdn_base_url,
                "accept": "application/json, text/javascript, */*; q=0.01",
            }
            post_data = {"hash": video_id, "r": referer_url}
            
            log.info(f"Calling video API: {api_url}")
            api_resp = await session.post(api_url, headers=api_headers, data=post_data)
            
            if api_resp.status_code != 200:
                log.error(f"API request failed: HTTP {api_resp.status_code}")
                sys.exit(1)
                
            try:
                data = api_resp.json()
            except:
                log.error("Failed to parse API response")
                sys.exit(1)
            
            video_url = data.get("videoSource") or data.get("securedLink")
            if not video_url:
                log.error(f"No video URL in API response: {data}")
                sys.exit(1)
                
            log.info(f"Got video URL: {video_url}")
            
            # 4. m3u8 다운로드
            m3u8_headers = {
                # "user-agent": ...,
                "referer": iframe_src,
                "origin": cdn_base_url,
                "accept": "*/*",
            }
            
            log.info(f"Fetching m3u8: {video_url}")
            m3u8_resp = await session.get(video_url, headers=m3u8_headers)
            m3u8_content = m3u8_resp.text
            
            # Master playlist 확인 및 미디어 플레이리스트 추적
            detected_resolution = None
            if "#EXT-X-STREAM-INF" in m3u8_content:
                base = video_url.rsplit('/', 1)[0] + '/'
                last_url = None
                last_resolution = None
                for line in m3u8_content.strip().split('\n'):
                    line = line.strip()
                    # RESOLUTION 파싱: #EXT-X-STREAM-INF:...,RESOLUTION=1280x720,...
                    if line.startswith('#EXT-X-STREAM-INF'):
                        res_match = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                        if res_match:
                            last_resolution = int(res_match.group(2))  # height (720, 1080 등)
                    elif line and not line.startswith('#'):
                        if line.startswith('http'):
                            last_url = line
                        else:
                            last_url = urljoin(base, line)
                        # 마지막(최고 품질) 스트림의 해상도 저장
                        if last_resolution:
                            detected_resolution = last_resolution
                
                if last_url:
                    log.info(f"Following media playlist: {last_url}")
                    m3u8_resp = await session.get(last_url, headers=m3u8_headers)
                    m3u8_content = m3u8_resp.text
                    video_url = last_url
            
            # 해상도 로깅 (참고용 - 이미 mod_ohli24.py에서 파일명 생성 전 처리됨)
            if detected_resolution:
                log.info(f"Detected resolution: {detected_resolution}p")
            
            # 5. 세그먼트 파싱
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
                log.error("No segments found")
                sys.exit(1)
            
            log.info(f"Found {len(segments)} segments. Starting AsyncIO download...")
            
            # 6. Async Segment Download
            # 쿠키 유지: session.cookies는 이미 이전 요청들로 인해 채워져 있음 (자동 관리)
            
            # 출력 디렉토리
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            with tempfile.TemporaryDirectory(dir=output_dir) as temp_dir:
                log.info(f"Temp directory: {temp_dir}")
                
                start_time = time.time()
                total_segments = len(segments)
                completed_segments = 0
                total_bytes = 0
                segment_files = [None] * total_segments
                
                # Semaphore로 동시성 제어 - 설정값 사용 (UI에서 1~16 선택 가능)
                actual_threads = threads  # 설정에서 전달된 값 사용
                log.info(f"Concurrency set to {actual_threads} (from settings)")
                sem = asyncio.Semaphore(actual_threads)
                
                async def download_one(idx: int, url: str) -> None:
                    nonlocal completed_segments, total_bytes
                    async with sem:
                        outfile = os.path.join(temp_dir, f"segment_{idx:05d}.ts")
                        for retry in range(3):
                            try:
                                # 스트림 방식으로 다운로드하면 메모리 절약 가능하지만, TS는 작으므로 그냥 read
                                # log.debug(f"Req Seg {idx}...") 
                                # 타임아웃 강제 적용 (asyncio.wait_for) - Hang 방지
                                resp = await asyncio.wait_for(
                                    session.get(url, headers=m3u8_headers), 
                                    timeout=20
                                )
                                
                                if resp.status_code == 200:
                                    content = resp.content
                                    if len(content) < 500:
                                        # HTML/에러 체크
                                        head = content[:100].decode('utf-8', errors='ignore').lower()
                                        if "<html" in head or "<!doctype" in head:
                                            if retry == 2:
                                                log.warning(f"Seg {idx} is HTML garbage. Retrying...")
                                            raise Exception("HTML content received")
                                    
                                    # Write File (Sync write is fine for tmpfs/SSD usually, otherwise aiofiles)
                                    with open(outfile, 'wb') as f:
                                        f.write(content)
                                    
                                    segment_files[idx] = f"segment_{idx:05d}.ts"
                                    completed_segments += 1
                                    total_bytes += len(content)
                                    
                                    # Log Progress
                                    if completed_segments == 1 or completed_segments % 10 == 0 or completed_segments == total_segments:
                                        pct = int((completed_segments / total_segments) * 100)
                                        elapsed = time.time() - start_time
                                        speed = total_bytes / elapsed if elapsed > 0 else 0
                                        log.info(f"Progress: {pct}% ({completed_segments}/{total_segments}) Speed: {format_speed(speed)}")
                                        update_progress(pct, completed_segments, total_segments, format_speed(speed), format_time(elapsed))
                                    return
                            except asyncio.TimeoutError:
                                if retry == 2:
                                    log.error(f"Seg {idx} TIMEOUT.")
                                # else:
                                #     log.debug(f"Seg {idx} timeout, retrying...")
                                pass
                            except Exception as e:
                                if retry == 2:
                                    log.error(f"Seg {idx} failed: {e}")
                                else:
                                    log.warning(f"Seg {idx} error: {e}. Retrying in 5s...")
                                    await asyncio.sleep(5) # Backoff increased to 5s
                
                # Create Tasks
                tasks = [download_one(i, url) for i, url in enumerate(segments)]
                await asyncio.gather(*tasks)
                
                # Check Results
                if completed_segments != total_segments:
                    log.error(f"Download incomplete: {completed_segments}/{total_segments}")
                    sys.exit(1)
                
                log.info("All segments downloaded. Merging...")
                update_progress(100, total_segments, total_segments, "", "", status="merging")
                
                # Merge
                concat_list_path = os.path.join(temp_dir, "concat.txt")
                with open(concat_list_path, 'w') as f:
                    for sf in segment_files:
                        if sf:
                            f.write(f"file '{sf}'\n")
                
                cmd = [
                    'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                    '-i', 'concat.txt', '-c', 'copy', os.path.abspath(output_path)
                ]
                
                # ffmpeg는 sync subprocess로 실행 (block이어도 상관없음, 마지막 단계라)
                # 하지만 asyncio 환경이므로 run_in_executor 혹은 create_subprocess_exec 권장
                # 여기선 간단히 create_subprocess_exec 사용
                proc = await asyncio.create_subprocess_exec(
                    *cmd, 
                    stdout=asyncio.subprocess.PIPE, 
                    stderr=asyncio.subprocess.PIPE,
                    cwd=temp_dir
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode != 0:
                    log.error(f"FFmpeg failed: {stderr.decode()}")
                    sys.exit(1)
                
                if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                    log.info(f"Download Success: {output_path}")
                else:
                    log.error("Output file invalid")
                    sys.exit(1)
                    
    except Exception as e:
        log.error(f"Critical Error: {e}")
        import traceback
        log.error(traceback.format_exc())
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
        threads = int(sys.argv[6]) if len(sys.argv) > 6 else 16
        
        _download_worker(iframe_url, output_path, referer, proxy, progress_path, threads)
    elif len(sys.argv) >= 3:
        # CLI 테스트 모드
        logging.basicConfig(level=logging.DEBUG)
        
        iframe_url = sys.argv[1]
        output_path = sys.argv[2]
        referer = sys.argv[3] if len(sys.argv) > 3 else None
        proxy = sys.argv[4] if len(sys.argv) > 4 else None
        
        def progress_callback(percent: int, current: int, total: int, speed: str, elapsed: str) -> None:
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
        print("Usage: python cdndania_downloader.py <iframe_url> <output_path> [referer] [proxy] [progress_path] [threads]")
