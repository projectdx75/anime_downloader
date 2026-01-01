from .lib.ffmpeg_queue_v1 import FfmpegQueueEntity
from .lib.downloader_factory import DownloaderFactory
from framework import db
import os, shutil, re, logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AnimeQueueEntity(FfmpegQueueEntity):
    def __init__(self, P, module_logic, info):
        super(AnimeQueueEntity, self).__init__(P, module_logic, info)
        self.P = P

    def get_downloader(self, video_url, output_file, callback=None, **kwargs):
        """Returns the appropriate downloader using the factory."""
        method = self.P.ModelSetting.get(f"{self.module_logic.name}_download_method")
        threads = self.P.ModelSetting.get_int(f"{self.module_logic.name}_download_threads")
        if threads is None:
            threads = 16
        
        # Prepare headers and proxy
        headers = self.headers
        if headers is None:
            headers = getattr(self.module_logic, 'headers', None)
            
        proxy = getattr(self, 'proxy', None)
        if proxy is None:
            proxy = getattr(self.module_logic, 'proxy', None)

        # Build downloader arguments
        args = {
            'cookies_file': getattr(self, 'cookies_file', None),
            'iframe_src': getattr(self, 'iframe_src', None),
            'callback_id': self.entity_id,
            'callback_function': kwargs.get('callback_function') or getattr(self, 'ffmpeg_listener', None)
        }
        
        # Site specific referer defaults
        if self.module_logic.name == 'ohli24':
            args['referer_url'] = "https://ani.ohli24.com/"
        elif self.module_logic.name == 'anilife':
            args['referer_url'] = self.P.ModelSetting.get("anilife_url", "https://anilife.live")
            
        args.update(kwargs)

        return DownloaderFactory.get_downloader(
            method=method,
            video_url=video_url,
            output_file=output_file,
            headers=headers,
            callback=callback,
            proxy=proxy,
            threads=threads,
            **args
        )

    def prepare_extra(self):
        """
        [Lazy Extraction] 
        다운로드 직전에 호출되는 무거운 분석 로직 (URL 추출 등).
        자식 클래스에서 오버라이드하여 구현합니다.
        """
        pass

    def refresh_status(self):
        """Common status refresh logic"""
        if self.ffmpeg_status == -1:
            self.ffmpeg_status_kor = "대기"
        elif self.ffmpeg_status == 0:
            self.ffmpeg_status_kor = "대기"  # Waiting in queue
        elif self.ffmpeg_status == 1:
            self.ffmpeg_status_kor = "분석 중"
        elif self.ffmpeg_status == 2:
            self.ffmpeg_status_kor = "다운로드 중"
        elif self.ffmpeg_status == 3:
            self.ffmpeg_status_kor = "변환 중" # post-processing
        elif self.ffmpeg_status == 4:
            self.ffmpeg_status_kor = "실패"
        elif self.ffmpeg_status == 5:
            self.ffmpeg_status_kor = "다운로드 중" # downloading
        elif self.ffmpeg_status == 6:
            self.ffmpeg_status_kor = "취소"
        elif self.ffmpeg_status == 7:
            self.ffmpeg_status_kor = "완료"
        elif self.ffmpeg_status == 8:
            self.ffmpeg_status_kor = "완료(이미 있음)"
        elif self.ffmpeg_status == 9:
            self.ffmpeg_status_kor = "실패(파일 없음)"

    def download_completed(self):
        """Common file move logic"""
        try:
            # LogicCommon to move file
            # Specific implementation might vary but usually:
            # 1. Check self.savepath
            # 2. Check self.filename
            # 3. Move self.filepath to dest
            
            if not self.savepath or not self.filename:
                return

            if not os.path.exists(self.savepath):
                os.makedirs(self.savepath)

            # Clean filename
            # self.filename = Util.change_text_for_use_filename(self.filename) 
            # (Assuming Util available or do basic replace)
            self.filename = re.sub(r'[\\/:*?"<>|]', '', self.filename)

            dest_path = os.path.join(self.savepath, self.filename)
            
            # If already at destination, just return
            if self.filepath == dest_path:
                self.ffmpeg_status = 7
                self.ffmpeg_status_kor = "완료"
                self.end_time = datetime.now()
                return

            if self.filepath and os.path.exists(self.filepath):
                if os.path.exists(dest_path):
                     self.P.logger.info(f"Destination file exists, removing to overwrite: {dest_path}")
                     os.remove(dest_path)
                
                shutil.move(self.filepath, dest_path)
                self.filepath = dest_path # Update filepath to new location
                self.ffmpeg_status = 7
                self.ffmpeg_status_kor = "완료"
                self.end_time = datetime.now()
        except Exception as e:
            self.P.logger.error(f"Download completed error: {e}")
            self.ffmpeg_status = 4
            self.ffmpeg_status_kor = "이동 실패"

    def info_dict(self, tmp):
        """Default valid implementation"""
        return tmp
