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

logger = logging.getLogger(__name__)


class YtdlpDownloader:
    """yt-dlp 기반 다운로더"""
    
    def __init__(self, url, output_path, headers=None, callback=None, proxy=None, cookies_file=None):
        self.url = url
        self.output_path = output_path
        self.headers = headers or {}
        self.callback = callback  # 진행 상황 콜백
        self.proxy = proxy
        self.cookies_file = cookies_file  # CDN 세션 쿠키 파일 경로
        self.cancelled = False
        self.process = None
        self.error_output = []  # 에러 메시지 저장
        
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
    
    def download(self):
        """yt-dlp CLI를 통한 브라우저 흉내(Impersonate) 방식 다운로드 수행"""
        try:
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

            # 1. 기본 명령어 구성 (Impersonate & HLS 강제)
            cmd = [
                'yt-dlp',
                '--newline',
                '--no-playlist',
                '--no-part',
                '--hls-prefer-ffmpeg',
                '--hls-use-mpegts',
                '--no-check-certificate',
                '--progress',
                '--verbose',                # 디버깅용 상세 로그
                '--impersonate', 'chrome-120', # 정밀한 크롬-120 지문 사용
                '--extractor-args', 'generic:force_hls', # HLS 강제 추출
                '-o', self.output_path,
            ]

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

            cmd.append(current_url)

            logger.info(f"Executing refined browser-impersonated yt-dlp CLI (v16): {' '.join(cmd)}")
            
            # 4. subprocess 실행 및 파싱
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # 여러 진행률 형식 매칭
            # [download]  10.5% of ~100.00MiB at  2.45MiB/s
            # [download]  10.5% of 100.00MiB at 2.45MiB/s ETA 00:30
            # [download] 100% of 100.00MiB
            prog_patterns = [
                re.compile(r'\[download\]\s+(?P<percent>[\d\.]+)%\s+of\s+.*?(?:\s+at\s+(?P<speed>[\d\.]+\s*\w+/s))?'),
                re.compile(r'\[download\]\s+(?P<percent>[\d\.]+)%'),
            ]

            for line in self.process.stdout:
                if self.cancelled:
                    self.process.terminate()
                    return False, "Cancelled"
                
                line = line.strip()
                if not line: continue
                
                # 디버깅: 모든 출력 로깅 (너무 많으면 주석 해제)
                if '[download]' in line or 'fragment' in line.lower():
                    logger.debug(f"yt-dlp: {line}")
                
                for prog_re in prog_patterns:
                    match = prog_re.search(line)
                    if match:
                        try:
                            self.percent = float(match.group('percent'))
                            speed_group = match.groupdict().get('speed')
                            if speed_group:
                                self.current_speed = speed_group.strip()
                            if self.start_time:
                                elapsed = time.time() - self.start_time
                                self.elapsed_time = self.format_time(elapsed)
                            if self.callback:
                                self.callback(percent=int(self.percent), current=int(self.percent), total=100, speed=self.current_speed, elapsed=self.elapsed_time)
                        except: pass
                        break  # 한 패턴이 매칭되면 중단
                
                if 'error' in line.lower() or 'security' in line.lower() or 'unable' in line.lower():
                    logger.warning(f"yt-dlp output notice: {line}")
                    self.error_output.append(line)

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
