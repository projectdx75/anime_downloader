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
    
    def __init__(self, url, output_path, headers=None, callback=None):
        self.url = url
        self.output_path = output_path
        self.headers = headers or {}
        self.callback = callback  # 진행 상황 콜백
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
        """yt-dlp Python 모듈로 다운로드 수행"""
        try:
            import yt_dlp
        except ImportError:
            return False, "yt-dlp를 찾을 수 없습니다. pip install yt-dlp 로 설치해주세요."
        
        try:
            self.start_time = time.time()
            
            # 출력 디렉토리 생성
            output_dir = os.path.dirname(self.output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 진행률 콜백
            def progress_hook(d):
                if self.cancelled:
                    raise Exception("Cancelled")
                
                if d['status'] == 'downloading':
                    # 진행률 추출
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    downloaded = d.get('downloaded_bytes', 0)
                    speed = d.get('speed', 0)
                    
                    if total > 0:
                        self.percent = (downloaded / total) * 100
                    
                    self.current_speed = self.format_speed(speed) if speed else ""
                    
                    if self.start_time:
                        elapsed = time.time() - self.start_time
                        self.elapsed_time = self.format_time(elapsed)
                    
                    # 콜백 호출
                    if self.callback:
                        self.callback(
                            percent=int(self.percent),
                            current=int(self.percent),
                            total=100,
                            speed=self.current_speed,
                            elapsed=self.elapsed_time
                        )
                
                elif d['status'] == 'finished':
                    logger.info(f"yt-dlp download finished: {d.get('filename', '')}")
            
            # yt-dlp 옵션 설정
            ydl_opts = {
                'outtmpl': self.output_path,
                'progress_hooks': [progress_hook],
                'quiet': False,
                'no_warnings': False,
                'noprogress': False,
            }
            
            # 헤더 추가
            http_headers = {}
            if self.headers:
                if self.headers.get('Referer'):
                    http_headers['Referer'] = self.headers['Referer']
                if self.headers.get('User-Agent'):
                    http_headers['User-Agent'] = self.headers['User-Agent']
            
            if http_headers:
                ydl_opts['http_headers'] = http_headers
            
            logger.info(f"yt-dlp downloading: {self.url}")
            logger.info(f"Output path: {self.output_path}")
            logger.info(f"Headers: {http_headers}")
            
            # 다운로드 실행
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            
            # 파일 존재 확인
            if os.path.exists(self.output_path):
                return True, "Download completed"
            else:
                # yt-dlp가 확장자를 변경했을 수 있음
                base_name = os.path.splitext(self.output_path)[0]
                for ext in ['.mp4', '.mkv', '.webm', '.ts']:
                    possible_path = base_name + ext
                    if os.path.exists(possible_path):
                        if possible_path != self.output_path:
                            os.rename(possible_path, self.output_path)
                        return True, "Download completed"
                
                return False, "Output file not found"
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"yt-dlp download error: {error_msg}")
            return False, f"yt-dlp 실패: {error_msg}"
    
    def cancel(self):
        """다운로드 취소"""
        self.cancelled = True
