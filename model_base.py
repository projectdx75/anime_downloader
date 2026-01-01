from .lib.ffmpeg_queue_v1 import FfmpegQueueEntity
from framework import db
import os, shutil, re
from datetime import datetime

class AnimeQueueEntity(FfmpegQueueEntity):
    def __init__(self, P, module_logic, info):
        super(AnimeQueueEntity, self).__init__(P, module_logic, info)
        self.P = P

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
            if self.filepath and os.path.exists(self.filepath):
                if os.path.exists(dest_path):
                     self.P.logger.info(f"File exists, removing source: {dest_path}")
                     # policy: overwrite or skip? usually overwrite or skip
                     # Here assume overwrite or just move
                     os.remove(dest_path) # overwrite
                
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
