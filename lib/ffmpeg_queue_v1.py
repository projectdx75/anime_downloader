import abc
import os
import queue
import threading
import time
import traceback
from datetime import datetime

import requests

# from flaskfarm.lib.plugin import get_model_setting
from flaskfarm.lib.support.expand.ffmpeg import SupportFfmpeg

# from flaskfarm.lib.system.setup import SystemModelSetting
from flaskfarm.lib.tool import ToolUtil

# from flaskfarm.lib.system.setup import P as SM
# from flaskfarm.lib.system.mod_setting import ModuleSetting as SM

from ..setup import *

logger = P.logger


class FfmpegQueueEntity(abc.ABCMeta("ABC", (object,), {"__slots__": ()})):
    def __init__(self, P, module_logic, info):
        self.P = P
        # SupportFfmpeg.initialize()
        self.module_logic = module_logic
        self.entity_id = -1
        self.entity_list = []
        # FfmpegQueueEntity.static_index
        self.info = info
        self.url = None
        self.ffmpeg_status = -1
        self.ffmpeg_status_kor = "대기중"
        self.ffmpeg_percent = 0
        self.ffmpeg_arg = None
        self.cancel = False
        self.created_time = datetime.now().strftime("%m-%d %H:%M:%S")
        self.savepath = None
        self.filename = None
        self.filepath = None
        self.quality = None
        self.headers = None
        self.proxy = None
        self.current_speed = ""  # 다운로드 속도
        self.download_time = ""  # 경과 시간
        # FfmpegQueueEntity.static_index += 1
        # FfmpegQueueEntity.entity_list.append(self)

    def get_video_url(self):
        return self.url

    def get_video_filepath(self):
        return self.filepath

    @abc.abstractmethod
    def refresh_status(self):
        pass

    @abc.abstractmethod
    def info_dict(self, tmp):
        pass

    def download_completed(self):
        pass

    def as_dict(self):
        tmp = {}
        tmp["entity_id"] = self.entity_id
        tmp["url"] = self.url
        tmp["ffmpeg_status"] = self.ffmpeg_status
        tmp["ffmpeg_status_kor"] = self.ffmpeg_status_kor
        tmp["ffmpeg_percent"] = self.ffmpeg_percent
        tmp["ffmpeg_arg"] = self.ffmpeg_arg
        tmp["cancel"] = self.cancel
        tmp["created_time"] = self.created_time  # .strftime('%m-%d %H:%M:%S')
        tmp["savepath"] = self.savepath
        tmp["filename"] = self.filename
        tmp["filepath"] = self.filepath
        tmp["quality"] = self.quality
        tmp["current_speed"] = self.current_speed
        tmp["download_time"] = self.download_time
        
        # 템플릿 호환 필드 추가 (queue.html에서 사용하는 필드명)
        tmp["idx"] = self.entity_id
        tmp["callback_id"] = getattr(self, 'name', 'anilife') if hasattr(self, 'name') else 'anilife'
        tmp["start_time"] = self.created_time
        tmp["status_kor"] = self.ffmpeg_status_kor
        # status_str: 템플릿에서 문자열 비교에 사용 (DOWNLOADING, COMPLETED, WAITING)
        status_map = {
            0: "WAITING",
            1: "STARTED", 
            5: "DOWNLOADING",
            7: "COMPLETED",
            -1: "FAILED"
        }
        tmp["status_str"] = status_map.get(self.ffmpeg_status, "WAITING")
        tmp["percent"] = self.ffmpeg_percent
        tmp["duration_str"] = ""
        tmp["duration"] = ""
        tmp["current_duration"] = ""
        tmp["current_pf_count"] = 0
        tmp["max_pf_count"] = 0
        tmp["current_bitrate"] = ""
        tmp["end_time"] = ""
        tmp["exist"] = False
        tmp["temp_fullpath"] = self.filepath or ""
        tmp["save_fullpath"] = self.filepath or ""
        
        tmp = self.info_dict(tmp)
        return tmp


class FfmpegQueue(object):
    def __init__(self, P, max_ffmpeg_count, sub_package_name, caller=None):

        self.P = P
        self.static_index = 1
        self.entity_list = []
        self.current_ffmpeg_count = 0
        self.download_queue = None
        self.download_thread = None
        self.max_ffmpeg_count = max_ffmpeg_count
        self.name = sub_package_name
        if self.max_ffmpeg_count is None or self.max_ffmpeg_count == "":
            self.max_ffmpeg_count = 1
        self.caller = None
        if caller is not None:
            self.caller = caller
        # self.support_init()

    def support_init(self):
        SupportFfmpeg.initialize(
            "ffmpeg",
            os.path.join(F.config["path_data"], "tmp"),
            self.callback_function,
            P.ModelSetting.get(f"{self.name}_max_ffmpeg_process_count"),
        )

    def queue_start(self):
        try:
            if self.download_queue is None:
                self.download_queue = queue.Queue()
            if self.download_thread is None:
                self.download_thread = threading.Thread(
                    target=self.download_thread_function, args=()
                )
                self.download_thread.daemon = True
                # todo: 동작 방식 고찰
                self.download_thread.start()
        except Exception as exception:
            self.P.logger.error(f"Exception: {exception}")
            self.P.logger.error(traceback.format_exc())

    def download_thread_function(self):
        while True:
            try:
                while True:
                    try:
                        if self.current_ffmpeg_count < self.max_ffmpeg_count:
                            break
                        time.sleep(5)
                    except Exception as exception:
                        self.P.logger.error(f"Exception: {exception}")
                        self.P.logger.error(traceback.format_exc())
                        self.P.logger.error(
                            "current_ffmpeg_count : %s", self.current_ffmpeg_count
                        )
                        self.P.logger.error(
                            "max_ffmpeg_count : %s", self.max_ffmpeg_count
                        )
                        break
                entity = self.download_queue.get()
                logger.debug(f"entity: {entity}")
                if entity.cancel:
                    continue

                # from .logic_ani24 import LogicAni24
                # entity.url = LogicAni24.get_video_url(entity.info['code'])
                video_url = entity.get_video_url()
                if video_url is None:
                    entity.ffmpeg_status_kor = "URL실패"
                    entity.refresh_status()
                    # plugin.socketio_list_refresh()
                    continue

                # import ffmpeg

                # max_pf_count = 0
                # save_path = ModelSetting.get('download_path')
                # if ModelSetting.get('auto_make_folder') == 'True':
                #    program_path = os.path.join(save_path, entity.info['filename'].split('.')[0])
                #    save_path = program_path
                # try:
                #    if not os.path.exists(save_path):
                #        os.makedirs(save_path)
                # except:
                #    logger.debug('program path make fail!!')
                # 파일 존재여부 체크
                print("here...................")
                P.logger.info(entity.info)
                filepath = entity.get_video_filepath()
                P.logger.debug(f"filepath:: {filepath}")
                if os.path.exists(filepath):
                    entity.ffmpeg_status_kor = "파일 있음"
                    entity.ffmpeg_percent = 100
                    entity.refresh_status()
                    # plugin.socketio_list_refresh()
                    continue
                dirname = os.path.dirname(filepath)
                filename = os.path.basename(filepath)
                if not os.path.exists(dirname):
                    os.makedirs(dirname)
                # f = ffmpeg.Ffmpeg(video_url, os.path.basename(filepath), plugin_id=entity.entity_id, listener=self.ffmpeg_listener, call_plugin=self.P.package_name, save_path=dirname, headers=entity.headers)
                # print(filepath)
                # print(os.path.basename(filepath))
                # print(dirname)
                # aa_sm = get_model_setting("system", P.logger)
                P.logger.debug(P)
                # P.logger.debug(P.system_setting.get("port"))
                P.logger.debug(filename)
                # P.logger.debug(filepath)

                # entity.headers가 있으면 우선 사용, 없으면 caller.headers 사용
                _headers = entity.headers
                if _headers is None and self.caller is not None:
                    _headers = self.caller.headers
                
                # SupportFfmpeg 초기화
                self.support_init()
                
                # proxy 가져오기
                _proxy = getattr(entity, 'proxy', None)
                if _proxy is None and self.caller is not None:
                    _proxy = getattr(self.caller, 'proxy', None)
                
                logger.info(f"Starting ffmpeg download - video_url: {video_url}")
                logger.info(f"save_path: {dirname}, filename: {filename}")
                logger.info(f"headers: {_headers}")
                
                # 자막 URL 로그
                vtt_url = getattr(entity, 'vtt', None)
                logger.info(f"Subtitle URL (vtt): {vtt_url}")
                
                # 터미널에서 수동 테스트용 ffmpeg 명령어
                output_file = os.path.join(dirname, filename)
                referer = _headers.get("Referer", "") if _headers else ""
                user_agent = _headers.get("User-Agent", "") if _headers else ""
                ffmpeg_cmd = f'ffmpeg -headers "Referer: {referer}\\r\\nUser-Agent: {user_agent}\\r\\n" -i "{video_url}" -c copy "{output_file}"'
                logger.info(f"=== MANUAL TEST COMMAND ===")
                logger.info(ffmpeg_cmd)
                logger.info(f"=== END COMMAND ===")

                # m3u8 URL인 경우 다운로드 방법 설정에 따라 분기
                if video_url.endswith('.m3u8') or 'master.txt' in video_url or 'gcdn.app' in video_url:
                    # 다운로드 방법 설정 확인
                    download_method = P.ModelSetting.get(f"{self.name}_download_method")
                    
                    # cdndania.com 감지 시 YtdlpDownloader 사용 (CDN 세션 쿠키 + Impersonate로 보안 우회)
                    if 'cdndania.com' in video_url:
                        logger.info("Detected cdndania.com URL - forcing YtdlpDownloader with cookies (CDN security bypass)")
                        download_method = "ytdlp"
                    
                    logger.info(f"Download method: {download_method}")

                    
                    # 다운로드 시작 전 카운트 증가
                    self.current_ffmpeg_count += 1
                    logger.info(f"Download started, current_ffmpeg_count: {self.current_ffmpeg_count}/{self.max_ffmpeg_count}")
                    
                    # 별도 스레드에서 다운로드 실행 (동시 다운로드 지원)
                    def run_download(downloader_self, entity_ref, output_file_ref, headers_ref, method):
                        def progress_callback(percent, current, total, speed="", elapsed=""):
                            entity_ref.ffmpeg_status = 5  # DOWNLOADING
                            if method == "ytdlp":
                                entity_ref.ffmpeg_status_kor = f"다운로드중 (yt-dlp) {percent}%"
                            else:
                                entity_ref.ffmpeg_status_kor = f"다운로드중 ({current}/{total})"
                            entity_ref.ffmpeg_percent = percent
                            entity_ref.current_speed = speed
                            entity_ref.download_time = elapsed
                            entity_ref.refresh_status()
                        
                        if method == "ytdlp":
                            # yt-dlp 사용
                            from .ytdlp_downloader import YtdlpDownloader
                            logger.info("Using yt-dlp downloader...")
                            # 엔티티에서 쿠키 파일 가져오기 (있는 경우)
                            _cookies_file = getattr(entity_ref, 'cookies_file', None)
                            downloader = YtdlpDownloader(
                                url=video_url,
                                output_path=output_file_ref,
                                headers=headers_ref,
                                callback=progress_callback,
                                proxy=_proxy,
                                cookies_file=_cookies_file
                            )

                        else:
                            # 기본: HLS 다운로더 사용
                            from .hls_downloader import HlsDownloader
                            logger.info("Using custom HLS downloader for m3u8 URL...")
                            downloader = HlsDownloader(
                                m3u8_url=video_url,
                                output_path=output_file_ref,
                                headers=headers_ref,
                                callback=progress_callback,
                                proxy=_proxy
                            )
                        
                        success, message = downloader.download()
                        
                        # 다운로드 완료 후 카운트 감소
                        downloader_self.current_ffmpeg_count -= 1
                        logger.info(f"Download finished, current_ffmpeg_count: {downloader_self.current_ffmpeg_count}/{downloader_self.max_ffmpeg_count}")
                        
                        if success:
                            entity_ref.ffmpeg_status = 7  # COMPLETED
                            entity_ref.ffmpeg_status_kor = "완료"
                            entity_ref.ffmpeg_percent = 100
                            entity_ref.download_completed()
                            entity_ref.refresh_status()
                            logger.info(f"Download completed: {output_file_ref}")
                            
                            # 자막 파일 다운로드 (vtt_url이 있는 경우)
                            vtt_url = getattr(entity_ref, 'vtt', None)
                            if vtt_url:
                                try:
                                    import requests
                                    # 자막 파일 경로 생성 (비디오 파일명.srt)
                                    video_basename = os.path.splitext(output_file_ref)[0]
                                    srt_path = video_basename + ".srt"
                                    
                                    logger.info(f"Downloading subtitle from: {vtt_url}")
                                    sub_response = requests.get(vtt_url, headers=headers_ref, timeout=30)
                                    
                                    if sub_response.status_code == 200:
                                        vtt_content = sub_response.text
                                        
                                        # VTT를 SRT로 변환 (간단한 변환)
                                        srt_content = vtt_content
                                        if vtt_content.startswith("WEBVTT"):
                                            # WEBVTT 헤더 제거
                                            lines = vtt_content.split("\n")
                                            srt_lines = []
                                            cue_index = 1
                                            i = 0
                                            while i < len(lines):
                                                line = lines[i].strip()
                                                # WEBVTT, NOTE, STYLE 등 메타데이터 스킵
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
                                                    i += 1
                                            srt_content = "\n".join(srt_lines)
                                        
                                        with open(srt_path, "w", encoding="utf-8") as f:
                                            f.write(srt_content)
                                        logger.info(f"Subtitle saved: {srt_path}")
                                    else:
                                        logger.warning(f"Subtitle download failed: HTTP {sub_response.status_code}")
                                except Exception as sub_err:
                                    logger.error(f"Subtitle download error: {sub_err}")
                        else:
                            entity_ref.ffmpeg_status = -1
                            entity_ref.ffmpeg_status_kor = f"실패: {message}"
                            entity_ref.refresh_status()
                            logger.error(f"Download failed: {message}")
                    
                    # 스레드 시작
                    download_thread = threading.Thread(
                        target=run_download,
                        args=(self, entity, output_file, _headers, download_method)
                    )
                    download_thread.daemon = True
                    download_thread.start()
                    
                    self.download_queue.task_done()
                else:
                    # 일반 URL은 기존 SupportFfmpeg 사용 (비동기 방식)
                    self.current_ffmpeg_count += 1
                    
                    ffmpeg = SupportFfmpeg(
                        url=video_url,
                        filename=filename,
                        callback_function=self.callback_function,
                        headers=_headers,
                        max_pf_count=0,
                        save_path=ToolUtil.make_path(dirname),
                        timeout_minute=60,
                        proxy=_proxy,
                    )
                    #
                    # todo: 임시로 start() 중지
                    logger.info("Calling ffmpeg.start()...")
                    ffmpeg.start()
                    logger.info("ffmpeg.start() returned")
                    
                    self.download_queue.task_done()


            except Exception as exception:
                self.P.logger.error("Exception:%s", exception)
                self.P.logger.error(traceback.format_exc())

    def callback_function(self, **args):
        refresh_type = None
        # entity = self.get_entity_by_entity_id(arg['plugin_id'])
        entity = self.get_entity_by_entity_id(args["data"]["callback_id"])

        if args["type"] == "status_change":
            if args["status"] == SupportFfmpeg.Status.DOWNLOADING:
                refresh_type = "status_change"
            elif args["status"] == SupportFfmpeg.Status.COMPLETED:
                logger.debug("ffmpeg_queue_v1.py:: download completed........")
                refresh_type = "status_change"
            elif args["status"] == SupportFfmpeg.Status.READY:
                data = {
                    "type": "info",
                    "msg": "다운로드중 Duration(%s)" % args["data"]["duration_str"]
                    + "<br>"
                    + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "add"
        elif args["type"] == "last":
            if args["status"] == SupportFfmpeg.Status.WRONG_URL:
                data = {"type": "warning", "msg": "잘못된 URL입니다"}
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "add"
            elif args["status"] == SupportFfmpeg.Status.WRONG_DIRECTORY:
                data = {
                    "type": "warning",
                    "msg": "잘못된 디렉토리입니다.<br>" + args["data"]["save_fullpath"],
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "add"
            elif (
                args["status"] == SupportFfmpeg.Status.ERROR
                or args["status"] == SupportFfmpeg.Status.EXCEPTION
            ):
                data = {
                    "type": "warning",
                    "msg": "다운로드 시작 실패.<br>" + args["data"]["save_fullpath"],
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "add"
            elif args["status"] == SupportFfmpeg.Status.USER_STOP:
                data = {
                    "type": "warning",
                    "msg": "다운로드가 중지 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.COMPLETED:
                print("print():: ffmpeg download completed..")
                logger.debug("ffmpeg download completed......")
                entity.download_completed()
                data = {
                    "type": "success",
                    "msg": "다운로드가 완료 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }

                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.TIME_OVER:
                data = {
                    "type": "warning",
                    "msg": "시간초과로 중단 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.PF_STOP:
                data = {
                    "type": "warning",
                    "msg": "PF초과로 중단 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.FORCE_STOP:
                data = {
                    "type": "warning",
                    "msg": "강제 중단 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.HTTP_FORBIDDEN:
                data = {
                    "type": "warning",
                    "msg": "403에러로 중단 되었습니다.<br>" + args["data"]["save_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "last"
            elif args["status"] == SupportFfmpeg.Status.ALREADY_DOWNLOADING:
                data = {
                    "type": "warning",
                    "msg": "임시파일폴더에 파일이 있습니다.<br>" + args["data"]["temp_fullpath"],
                    "url": "/ffmpeg/download/list",
                }
                socketio.emit("notify", data, namespace="/framework")
                refresh_type = "last"
        elif args["type"] == "normal":
            if args["status"] == SupportFfmpeg.Status.DOWNLOADING:
                refresh_type = "status"
        # P.logger.info(refresh_type)
        # Todo:
        if self.caller is not None:
            self.caller.socketio_callback(refresh_type, args["data"])
        else:
            logger.warning("caller is None, cannot send socketio_callback")

    # def ffmpeg_listener(self, **arg):
    #     import ffmpeg
    #
    #     entity = self.get_entity_by_entity_id(arg["plugin_id"])
    #     if entity is None:
    #         return
    #     if arg["type"] == "status_change":
    #         if arg["status"] == ffmpeg.Status.DOWNLOADING:
    #             pass
    #         elif arg["status"] == ffmpeg.Status.COMPLETED:
    #             entity.download_completed()
    #         elif arg["status"] == ffmpeg.Status.READY:
    #             pass
    #     elif arg["type"] == "last":
    #         self.current_ffmpeg_count += -1
    #     elif arg["type"] == "log":
    #         pass
    #     elif arg["type"] == "normal":
    #         pass
    #
    #     entity.ffmpeg_arg = arg
    #     entity.ffmpeg_status = int(arg["status"])
    #     entity.ffmpeg_status_kor = str(arg["status"])
    #     entity.ffmpeg_percent = arg["data"]["percent"]
    #     entity.ffmpeg_arg["status"] = str(arg["status"])
    #     # self.P.logger.debug(arg)
    #     # import plugin
    #     # arg['status'] = str(arg['status'])
    #     # plugin.socketio_callback('status', arg)
    #     entity.refresh_status()
    #
    #     # FfmpegQueueEntity.static_index += 1
    #     # FfmpegQueueEntity.entity_list.append(self)

    def add_queue(self, entity):
        try:
            entity.entity_id = self.static_index
            self.static_index += 1
            self.entity_list.append(entity)
            self.download_queue.put(entity)
            
            # 소켓IO로 추가 이벤트 전송
            try:
                from framework import socketio
                namespace = f"/{self.P.package_name}/{self.name}/queue"
                socketio.emit("add", entity.as_dict(), namespace=namespace)
                logger.debug(f"Emitted 'add' event for entity {entity.entity_id}")
            except Exception as e:
                logger.debug(f"Socket emit error (non-critical): {e}")
            
            return True
        except Exception as exception:
            self.P.logger.error("Exception:%s", exception)
            self.P.logger.error(traceback.format_exc())
        return False

    def set_max_ffmpeg_count(self, max_ffmpeg_count):
        self.max_ffmpeg_count = max_ffmpeg_count

    def get_max_ffmpeg_count(self):
        return self.max_ffmpeg_count

    def command(self, cmd, entity_id):
        self.P.logger.debug("command :%s %s", cmd, entity_id)
        ret = {}
        try:
            if cmd == "cancel":
                self.P.logger.debug("command :%s %s", cmd, entity_id)
                entity = self.get_entity_by_entity_id(entity_id)
                if entity is not None:
                    if entity.ffmpeg_status == -1:
                        entity.cancel = True
                        entity.ffmpeg_status_kor = "취소"
                        # entity.refresh_status()
                        ret["ret"] = "refresh"
                    elif entity.ffmpeg_status != 5:
                        ret["ret"] = "notify"
                        ret["log"] = "다운로드중 상태가 아닙니다."
                    else:
                        idx = entity.ffmpeg_arg["data"]["idx"]
                        import ffmpeg

                        ffmpeg.Ffmpeg.stop_by_idx(idx)
                        entity.refresh_status()
                        ret["ret"] = "refresh"
            elif cmd == "reset":
                if self.download_queue is not None:
                    with self.download_queue.mutex:
                        self.download_queue.queue.clear()
                    for _ in self.entity_list:
                        if _.ffmpeg_status == 5:
                            import ffmpeg

                            idx = _.ffmpeg_arg["data"]["idx"]
                            ffmpeg.Ffmpeg.stop_by_idx(idx)
                self.entity_list = []
                ret["ret"] = "refresh"
            elif cmd == "delete_completed":
                new_list = []
                for _ in self.entity_list:
                    if _.ffmpeg_status_kor in ["파일 있음", "취소", "사용자중지"]:
                        continue
                    if _.ffmpeg_status != 7:
                        new_list.append(_)
                self.entity_list = new_list
                ret["ret"] = "refresh"
            elif cmd == "remove":
                new_list = []
                for _ in self.entity_list:
                    if _.entity_id == entity_id:
                        continue
                    new_list.append(_)
                self.entity_list = new_list
                ret["ret"] = "refresh"
            return ret
        except Exception as exception:
            self.P.logger.error("Exception:%s", exception)
            self.P.logger.error(traceback.format_exc())

    def get_entity_by_entity_id(self, entity_id):
        for _ in self.entity_list:
            if _.entity_id == int(entity_id):
                return _
        return None

    def get_entity_list(self):
        ret = []
        #P.logger.debug(self)
        for x in self.entity_list:
            tmp = x.as_dict()
            ret.append(tmp)
        return ret
