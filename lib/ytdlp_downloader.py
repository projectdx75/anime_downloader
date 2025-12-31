"""
yt-dlp Downloader for linkkf
- Uses yt-dlp as Python module or subprocess
- Same interface as HlsDownloader for easy switching
"""
import os
import subprocess
import sys
import time
import re
import logging
import platform

logger = logging.getLogger(__name__)


class YtdlpDownloader:
    """yt-dlp 기반 다운로더"""
    
    def __init__(self, url, output_path, headers=None, callback=None, proxy=None, cookies_file=None, use_aria2c=False, threads=16):
        self.url = url
        self.output_path = output_path
        self.headers = headers or {}
        self.callback = callback  # 진행 상황 콜백
        self.proxy = proxy
        self.cookies_file = cookies_file  # CDN 세션 쿠키 파일 경로
        self.use_aria2c = use_aria2c  # Aria2c 사용 여부
        self.threads = threads        # 병렬 다운로드 스레드 수
        self.cancelled = False
        self.process = None
        self.error_output = []  # 에러 메시지 저장
        self.total_duration_seconds = 0  # 전체 영상 길이 (초)
        
        # 속도 및 시간 계산용
        self.start_time = None
        self.current_speed = ""
        self.elapsed_time = ""
        self.percent = 0

    
    def format_time(self, seconds):
        """시간을 읽기 좋은 형식으로 변환"""
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}초"
        elif seconds < 3600:
            mins = seconds // 60
            secs = seconds % 60
            return f"{mins}분 {secs}초"
        else:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            return f"{hours}시간 {mins}분"
    
    def format_speed(self, bytes_per_sec):
        """속도를 읽기 좋은 형식으로 변환"""
        if bytes_per_sec is None:
            return ""
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
    
    def time_to_seconds(self, time_str):
        """HH:MM:SS.ms 형식을 초로 변환"""
        try:
            if not time_str:
                return 0
            parts = time_str.split(':')
            if len(parts) != 3:
                return 0
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
        except Exception:
            return 0
    
    def _ensure_ytdlp_installed(self):
        """yt-dlp가 설치되어 있는지 확인하고, 없으면 자동 설치"""
        import shutil
        
        # yt-dlp binary가 PATH에 있는지 확인
        if shutil.which('yt-dlp') is not None:
            return True
        
        logger.info("yt-dlp not found in PATH. Installing via pip...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "yt-dlp", "-q"],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode != 0:
                logger.error(f"Failed to install yt-dlp: {result.stderr}")
                return False
            logger.info("yt-dlp installed successfully")
            return True
        except Exception as e:
            logger.error(f"yt-dlp installation error: {e}")
            return False
    
    def download(self):
        """yt-dlp CLI를 통한 브라우저 흉내(Impersonate) 방식 다운로드 수행"""
        try:
            # yt-dlp 설치 확인
            if not self._ensure_ytdlp_installed():
                return False, "yt-dlp installation failed"
            
            self.start_time = time.time()
            
            # 출력 디렉토리 생성
            output_dir = os.path.dirname(self.output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # URL 전처리: 확장자 힌트(?dummy=.m3u8) 사용 
            # (m3u8: 접두사나 #.m3u8보다 호환성이 높음. HLS 인식 강제용)
            current_url = self.url
            if 'master.txt' in current_url:
                concat_char = '&' if '?' in current_url else '?'
                current_url = f"{current_url}{concat_char}dummy=.m3u8"

            # 1. 기본 명령어 구성 (Impersonate & HLS 옵션)
            # hlz CDN (linkkf)은 .jpg 확장자로 위장된 TS 세그먼트를 사용
            # ffmpeg 8.0에서 이를 인식하지 못하므로 native HLS 다운로더 사용
            use_native_hls = 'hlz' in current_url and '.top/' in current_url
            
            cmd = [
                'yt-dlp',
                '--newline',
                '--no-playlist',
                '--no-part',
            ]
            
            if use_native_hls or self.use_aria2c:
                # hlz CDN: native HLS 다운로더 사용 (ffmpeg의 확장자 제한 우회)
                # Aria2c 사용 시: Native HLS를 써야 프래그먼트 병렬 다운로드가 가능함 (ffmpeg 모드는 순차적)
                cmd += ['--hls-prefer-native']
            else:
                # 기타 CDN: ffmpeg 사용 (더 안정적)
                cmd += ['--hls-prefer-ffmpeg', '--hls-use-mpegts']
            
            cmd += [
                '--no-check-certificate',
                '--progress',
                '--verbose',                # 디버깅용 상세 로그
                '--extractor-args', 'generic:force_hls', # HLS 강제 추출
                '-o', self.output_path,
            ]

            # 1.3 Aria2c 설정 (병렬 다운로드)
            # 1.3 Aria2c / 고속 모드 설정
            if self.use_aria2c:
                # [최적화] HLS(m3u8)의 경우, 작은 파일 수백 개를 받는데 aria2c 프로세스를 매번 띄우는 것보다
                # yt-dlp 내장 멀티스레드(-N)를 사용하는 것이 훨씬 빠르고 가볍습니다.
                # 따라서 사용자가 'aria2c'를 선택했더라도 HLS 스트림에 대해서는 'Native Concurrent' 모드로 작동시켜 속도를 극대화합니다.
                
                # 병렬 프래그먼트 다운로드 개수 (기본 1 -> 16 or 설정값)
                cmd += ['--concurrent-fragments', str(self.threads)]
                
                # 버퍼 크기 조절 (속도 향상 도움)
                cmd += ['--buffer-size', '16M']
                
                # DNS 캐싱 등 네트워크 타임아웃 완화
                cmd += ['--socket-timeout', '30']
                
                logger.info(f"High Speed Mode Active: Using Native Downloader with {self.threads} concurrent threads (Optimized for HLS)")
                # 주의: --external-downloader aria2c는 HLS 프래그먼트에서 오버헤드가 크므로 제거함
            
            
            # 1.5 환경별 브라우저 위장 설정 (Impersonate)
            # macOS에서는 고급 위장 기능을 사용하되, 종속성 문제가 잦은 Linux/Docker에서는 UA 수동 지정
            is_mac = platform.system() == 'Darwin'
            if is_mac:
                cmd += ['--impersonate', 'chrome-120']
                logger.debug("Using yt-dlp --impersonate chrome-120 (macOS detected)")
            else:
                # Docker/Linux: impersonate 라이브러리 부재 가능하므로 UA 수동 설정
                user_agent = self.headers.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                cmd += ['--user-agent', user_agent]
                logger.debug(f"Using manual User-Agent on {platform.system()}: {user_agent}")

            # 2. 프록시 설정
            if self.proxy:
                cmd += ['--proxy', self.proxy]

            # 2.5 쿠키 파일 설정 (CDN 세션 인증용)
            if self.cookies_file and os.path.exists(self.cookies_file):
                cmd += ['--cookies', self.cookies_file]
                logger.info(f"Using cookies file: {self.cookies_file}")

            # 3. 필수 헤더 구성
            # --impersonate가 기본적인 Sec-Fetch를 처리하지만, 
            # X-Requested-With와 정확한 Referer/Origin은 명시적으로 주는 것이 안전합니다.
            has_referer = False
            for k, v in self.headers.items():
                if k.lower() == 'referer':
                    cmd += ['--referer', v]
                    has_referer = True
                elif k.lower() == 'user-agent':
                    # impersonate가 설정한 UA를 명시적 UA로 덮어씀 (필요시)
                    cmd += ['--user-agent', v]
                else:
                    cmd += ['--add-header', f"{k}:{v}"]

            # cdndania 전용 헤더 보강
            if 'cdndania.com' in current_url:
                if not has_referer:
                    cmd += ['--referer', 'https://cdndania.com/']
                cmd += ['--add-header', 'Origin:https://cdndania.com']
                cmd += ['--add-header', 'X-Requested-With:XMLHttpRequest']
            
            # linkkf CDN (hlz3.top, hlz2.top 등) 헤더 보강
            if 'hlz' in current_url and '.top/' in current_url:
                # hlz CDN은 자체 도메인을 Referer로 요구함
                from urllib.parse import urlparse
                parsed = urlparse(current_url)
                cdn_origin = f"{parsed.scheme}://{parsed.netloc}"
                if not has_referer:
                    cmd += ['--referer', cdn_origin + '/']
                cmd += ['--add-header', f'Origin:{cdn_origin}']
                cmd += ['--add-header', 'Accept:*/*']

            cmd.append(current_url)

            logger.info(f"Executing refined browser-impersonated yt-dlp CLI (v17): {' '.join(cmd)}")
            if self.use_aria2c:
                 logger.info("ARIA2C ACTIVE: Forcing native HLS downloader for concurrency.")
            
            
            # 4. subprocess 실행 및 파싱
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # 여러 진행률 형식 매칭
            # yt-dlp native: [download]  10.5% of ~100.00MiB at  2.45MiB/s
            # yt-dlp native: [download]  10.5% of 100.00MiB at 2.45MiB/s ETA 00:30
            # yt-dlp native: [download] 100% of 100.00MiB
            # ffmpeg: frame= 1234 fps= 30 size= 12345kB time=00:01:23.45 bitrate=1234.5kbits/s
            # ffmpeg: size=  123456kB time=00:01:23.45
            prog_patterns = [
                re.compile(r'\[download\]\s+(?P<percent>[\d\.]+)%\s+of\s+.*?(?:\s+at\s+(?P<speed>[\d\.]+\s*\w+/s))?'),
                re.compile(r'\[download\]\s+(?P<percent>[\d\.]+)%'),
                # ffmpeg time 출력 파싱 (time=HH:MM:SS.ms)
                re.compile(r'time=(?P<time>\d+:\d+:\d+\.\d+)'),
                # ffmpeg size 출력 파싱
                re.compile(r'size=\s*(?P<size>\d+)kB'),
            ]
            
            # ffmpeg time-based progress tracking
            last_time_str = ""
            ffmpeg_progress_count = 0

            for line in self.process.stdout:
                if self.cancelled:
                    self.process.terminate()
                    return False, "Cancelled"
                
                line = line.strip()
                if not line: continue
                
                # ffmpeg Duration 파싱 (전체 길이 확인용)
                if 'Duration:' in line and self.total_duration_seconds == 0:
                    dur_match = re.search(r'Duration:\s*(?P<duration>\d+:\d+:\d+\.\d+)', line)
                    if dur_match:
                        self.total_duration_seconds = self.time_to_seconds(dur_match.group('duration'))
                        logger.info(f"[ffmpeg] Total duration detected: {dur_match.group('duration')} ({self.total_duration_seconds}s)")

                # ffmpeg time/size 출력 특별 처리
                # ffmpeg는 [download] X% 형식을 사용하지 않으므로 time으로 진행 상황 추정
                if 'time=' in line:
                    ffmpeg_progress_count += 1
                    # 매 5번째 출력마다 UI 업데이트 (너무 자주 업데이트 방지)
                    if ffmpeg_progress_count % 5 == 0 and self.callback:
                        # time= 파싱
                        time_match = re.search(r'time=(?P<time>\d+:\d+:\d+\.\d+)', line)
                        speed_match = re.search(r'bitrate=\s*([\d\.]+\w+)', line)
                        
                        time_str = time_match.group('time') if time_match else ""
                        bitrate = speed_match.group(1) if speed_match else ""
                        
                        if self.start_time:
                            elapsed = time.time() - self.start_time
                            self.elapsed_time = self.format_time(elapsed)
                        
                        # 비디오 시간 위치 표시 (시:분:초)
                        current_seconds = self.time_to_seconds(time_str)
                        if time_str:
                            # "00:05:30.45" -> "5분 30초"
                            parts = time_str.split(':')
                            hours = int(parts[0])
                            mins = int(parts[1])
                            secs = int(float(parts[2]))
                            if hours > 0:
                                video_time = f"{hours}시간 {mins}분"
                            else:
                                video_time = f"{mins}분 {secs}초"
                        else:
                            video_time = ""
                        
                        self.current_speed = bitrate if bitrate else ""
                        
                        # % 계산 (전체 길이를 알면 정확하게, 모르면 카운터 기반 99% 제한)
                        if self.total_duration_seconds > 0:
                            self.percent = (current_seconds / self.total_duration_seconds) * 100
                            self.percent = min(100.0, self.percent)
                        else:
                            self.percent = min(99.0, ffmpeg_progress_count)
                        
                        logger.info(f"[ffmpeg progress] {self.percent:.1f}% time={video_time} bitrate={bitrate}")
                        self.callback(percent=int(self.percent), current=int(current_seconds), total=int(self.total_duration_seconds), speed=video_time, elapsed=self.elapsed_time)
                    continue
                
                # 일반 [download] X% 형식 처리 (yt-dlp native 다운로더용)
                for prog_re in prog_patterns[:2]:  # 첫 두 패턴만 사용 (download 형식)
                    match = prog_re.search(line)
                    if match:
                        try:
                            new_percent = float(match.group('percent'))
                            speed_group = match.groupdict().get('speed')
                            
                            # 속도가 표시되지 않는 경우 (aria2c 등)를 위해 정규식 보완
                            if not speed_group:
                                # "[download]  10.5% of ~100.00MiB at  2.45MiB/s" 형태 재확인
                                at_match = re.search(r'at\s+([\d\.]+\s*\w+/s)', line)
                                if at_match:
                                    speed_group = at_match.group(1)
                            
                            if speed_group:
                                self.current_speed = speed_group.strip()
                            
                            if self.start_time:
                                elapsed = time.time() - self.start_time
                                self.elapsed_time = self.format_time(elapsed)
                            
                            # [최적화] 진행률이 1% 이상 차이나거나, 100%인 경우에만 콜백 호출 (로그 부하 감소)
                            if self.callback and (int(new_percent) > int(self.percent) or new_percent >= 100):
                                self.percent = new_percent
                                logger.info(f"[yt-dlp progress] {int(self.percent)}% speed={self.current_speed}")
                                self.callback(percent=int(self.percent), current=int(self.percent), total=100, speed=self.current_speed, elapsed=self.elapsed_time)
                            else:
                                self.percent = new_percent
                        except Exception as cb_err:
                            logger.warning(f"Callback error: {cb_err}")
                        break  # 한 패턴이 매칭되면 중단
                
                if 'error' in line.lower() or 'security' in line.lower() or 'unable' in line.lower():
                    logger.warning(f"yt-dlp output notice: {line}")
                    self.error_output.append(line)
                
                # Aria2c / 병렬 다운로드 로그 로깅
                if 'aria2c' in line.lower() or 'fragment' in line.lower():
                    logger.info(f"yt-dlp: {line}")

            self.process.wait()
            
            if self.process.returncode == 0 and os.path.exists(self.output_path):
                # 가짜 파일(보안 에러 텍스트) 체크
                file_size = os.path.getsize(self.output_path)
                if file_size < 2000:
                    try:
                        with open(self.output_path, 'r') as f:
                            text = f.read().lower()
                        if "security error" in text or not text:
                            os.remove(self.output_path)
                            return False, f"CDN 보안 차단(가짜 파일 다운로드됨: {file_size}B)"
                    except: pass
                return True, "Download completed"
            
            error_msg = "\n".join(self.error_output[-3:]) if self.error_output else f"Exit code {self.process.returncode}"
            return False, f"yt-dlp 실패: {error_msg}"
        except Exception as e:
            logger.error(f"yt-dlp download exception: {e}")
            return False, f"yt-dlp download exception: {str(e)}"
    
    def cancel(self):
        """다운로드 취소"""
        self.cancelled = True
        try:
            if self.process:
                # subprocess 종류에 따라 종료 방식 결정
                if platform.system() == 'Windows':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], capture_output=True)
                else:
                    self.process.terminate()
                    # 강제 종료 필요 시
                    # import signal
                    # os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                logger.info(f"Ytdlp process {self.process.pid} terminated by cancel()")
        except Exception as e:
            logger.error(f"Error terminating ytdlp process: {e}")
