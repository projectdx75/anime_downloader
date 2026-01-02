# -*- coding: utf-8 -*-
#########################################################
# python
import os
import re
import json
import time
import traceback
import platform
import subprocess
from functools import wraps

# third-party
from sqlalchemy.ext.declarative import DeclarativeMeta
# sjva 공용
from framework import app, logger


#########################################################

def download(url, file_name):
    try:
        import requests
        with open(file_name, "wb") as file_is:  # open in binary mode
            response = requests.get(url)  # get request
            file_is.write(response.content)  # write to file
    except Exception as exception:
        logger.debug('Exception:%s', exception)
        logger.debug(traceback.format_exc())


def read_file(filename):
    try:
        import codecs
        ifp = codecs.open(filename, 'r', encoding='utf8')
        data = ifp.read()
        ifp.close()
        return data
    except Exception as exception:
        logger.error('Exception:%s', exception)
        logger.error(traceback.format_exc())


def yommi_timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        print(f'Function {func.__name__}{args} {kwargs} Took {total_time:.4f} seconds')
        return result

    return timeit_wrapper


class Util(object):

    @staticmethod
    def change_text_for_use_filename(text):
        # text = text.replace('/', '')
        # 2021-07-31 X:X
        # text = text.replace(':', ' ')
        text = re.sub('[\\/:*?\"<>|]', ' ', text).strip()
        text = re.sub("\s{2,}", ' ', text)
        return text

    @staticmethod
    def write_file(data, filename):
        try:
            import codecs
            ofp = codecs.open(filename, 'w', encoding='utf8')
            ofp.write(data)
            ofp.close()
        except Exception as exception:
            logger.debug('Exception:%s', exception)
            logger.debug(traceback.format_exc())

    @staticmethod
    def download_subtitle(vtt_url, output_path, headers=None):
        try:
            import requests
            # 자막 파일 경로 생성 (비디오 파일명.srt)
            video_basename = os.path.splitext(output_path)[0]
            srt_path = video_basename + ".srt"
            
            logger.info(f"Downloading subtitle from: {vtt_url}")
            response = requests.get(vtt_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                vtt_content = response.text
                srt_content = Util.vtt_to_srt(vtt_content)
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)
                logger.info(f"Subtitle saved to: {srt_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to download subtitle: {e}")
            logger.error(traceback.format_exc())
        return False

    @staticmethod
    def vtt_to_srt(vtt_content):
        if not vtt_content.startswith("WEBVTT"):
            return vtt_content
            
        lines = vtt_content.split("\n")
        srt_lines = []
        cue_index = 1
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # WEBWTT, NOTE, STYLE 등 메타데이터 스킵
            if line.startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("STYLE"):
                i += 1
                continue
            # 빈 줄 스킵
            if not line:
                i += 1
                continue
            # 타임코드 라인 (00:00:00.000 --> 00:00:00.000)
            if "-->" in line:
                # VTT 타임코드를 SRT 형식으로 변환 (. -> ,)
                srt_timecode = line.replace(".", ",")
                srt_lines.append(str(cue_index))
                srt_lines.append(srt_timecode)
                cue_index += 1
                i += 1
                # 자막 텍스트 읽기
                while i < len(lines) and lines[i].strip():
                    srt_lines.append(lines[i].rstrip())
                    i += 1
                srt_lines.append("")
            else:
                # 캡션 텍스트가 바로 나오는 경우 등을 대비
                i += 1
        return "\n".join(srt_lines)

    @staticmethod
    def merge_subtitle(P, db_item):
        """
        ffmpeg를 사용하여 SRT 자막을 MP4에 삽입 (soft embed)
        """
        try:
            import subprocess
            mp4_path = db_item.filepath
            if not mp4_path or not os.path.exists(mp4_path):
                logger.error(f"MP4 file not found: {mp4_path}")
                return
            
            srt_path = os.path.splitext(mp4_path)[0] + ".srt"
            if not os.path.exists(srt_path):
                logger.error(f"SRT file not found: {srt_path}")
                return
            
            # 출력 파일: *_subed.mp4
            base_name = os.path.splitext(mp4_path)[0]
            output_path = f"{base_name}_subed.mp4"
            
            if os.path.exists(output_path):
                os.remove(output_path)
            
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", mp4_path,
                "-i", srt_path,
                "-c:v", "copy",
                "-c:a", "copy",
                "-c:s", "mov_text",
                "-metadata:s:s:0", "language=kor",
                output_path
            ]
            
            logger.info(f"[Merge Subtitle] Running ffmpeg: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"[Merge Subtitle] Success: {output_path}")
                # 원본 삭제 옵션 등이 필요할 수 있으나 여기서는 생성만 함
            else:
                logger.error(f"ffmpeg failed: {result.stderr}")
        except Exception as e:
            logger.error(f"merge_subtitle error: {e}")
            logger.error(traceback.format_exc())
