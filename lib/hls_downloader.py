"""
Custom HLS Downloader for linkkf
- Handles .jpg extension segments that ffmpeg 8.0 rejects
- Downloads segments individually and concatenates them
"""
import os
import requests
import tempfile
import subprocess
import time
from urllib.parse import urljoin


class HlsDownloader:
    """HLS 다운로더 - .jpg 확장자 세그먼트 지원"""
    
    def __init__(self, m3u8_url, output_path, headers=None, callback=None):
        self.m3u8_url = m3u8_url
        self.output_path = output_path
        self.headers = headers or {}
        self.callback = callback  # 진행 상황 콜백
        self.segments = []
        self.total_segments = 0
        self.downloaded_segments = 0
        self.cancelled = False
        
        # 속도 및 시간 계산용
        self.start_time = None
        self.total_bytes = 0
        self.last_speed_update_time = None
        self.last_bytes = 0
        self.current_speed = 0  # bytes per second
    
    def parse_m3u8(self):
        """m3u8 파일 파싱"""
        response = requests.get(self.m3u8_url, headers=self.headers, timeout=30)
        content = response.text
        
        base_url = self.m3u8_url.rsplit('/', 1)[0] + '/'
        
        self.segments = []
        for line in content.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # 상대 경로면 절대 경로로 변환
                if not line.startswith('http'):
                    segment_url = urljoin(base_url, line)
                else:
                    segment_url = line
                self.segments.append(segment_url)
        
        self.total_segments = len(self.segments)
        return self.total_segments
    
    def format_speed(self, bytes_per_sec):
        """속도를 읽기 좋은 형식으로 변환"""
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
    
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
    
    def download(self):
        """세그먼트 다운로드 및 합치기"""
        try:
            # m3u8 파싱
            self.parse_m3u8()
            
            if not self.segments:
                return False, "No segments found in m3u8"
            
            self.start_time = time.time()
            self.last_speed_update_time = self.start_time
            
            # 임시 디렉토리에 세그먼트 저장
            with tempfile.TemporaryDirectory() as temp_dir:
                segment_files = []
                
                for i, segment_url in enumerate(self.segments):
                    if self.cancelled:
                        return False, "Cancelled"
                    
                    # 세그먼트 다운로드
                    segment_path = os.path.join(temp_dir, f"segment_{i:05d}.ts")
                    
                    try:
                        response = requests.get(segment_url, headers=self.headers, timeout=60)
                        response.raise_for_status()
                        
                        segment_data = response.content
                        with open(segment_path, 'wb') as f:
                            f.write(segment_data)
                        
                        segment_files.append(segment_path)
                        self.downloaded_segments = i + 1
                        self.total_bytes += len(segment_data)
                        
                        # 속도 계산 (1초마다 갱신)
                        current_time = time.time()
                        time_diff = current_time - self.last_speed_update_time
                        if time_diff >= 1.0:
                            bytes_diff = self.total_bytes - self.last_bytes
                            self.current_speed = bytes_diff / time_diff
                            self.last_speed_update_time = current_time
                            self.last_bytes = self.total_bytes
                        
                        # 경과 시간 계산
                        elapsed_time = current_time - self.start_time
                        
                        # 콜백 호출 (진행 상황 업데이트)
                        if self.callback:
                            percent = int((self.downloaded_segments / self.total_segments) * 100)
                            self.callback(
                                percent=percent, 
                                current=self.downloaded_segments, 
                                total=self.total_segments,
                                speed=self.format_speed(self.current_speed),
                                elapsed=self.format_time(elapsed_time)
                            )
                    
                    except Exception as e:
                        return False, f"Failed to download segment {i}: {e}"
                
                # 세그먼트 합치기 (concat 파일 생성)
                concat_file = os.path.join(temp_dir, "concat.txt")
                with open(concat_file, 'w') as f:
                    for seg_file in segment_files:
                        f.write(f"file '{seg_file}'\n")
                
                # 출력 디렉토리 생성
                output_dir = os.path.dirname(self.output_path)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                
                # ffmpeg로 합치기
                cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c', 'copy',
                    self.output_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                
                if result.returncode != 0:
                    return False, f"FFmpeg concat failed: {result.stderr}"
                
                return True, "Download completed"
        
        except Exception as e:
            return False, f"Download error: {e}"
    
    def cancel(self):
        """다운로드 취소"""
        self.cancelled = True
