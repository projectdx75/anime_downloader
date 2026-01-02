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

                # [Lazy Extraction] 다운로드 시작 전 무거운 분석 로직 수행
                try:
                    entity.ffmpeg_status = 1  # ANALYZING
                    entity.ffmpeg_status_kor = "분석 중"
                    entity.refresh_status()
                    
                    if hasattr(entity, 'prepare_extra'):
                        logger.info(f"Starting background extraction: {entity.info.get('title')}")
                        entity.prepare_extra()
                        logger.info(f"Extraction finished for: {entity.info.get('title')}")
                except Exception as e:
                    logger.error(f"Failed to prepare entity: {e}")
                    logger.error(traceback.format_exc())
                    entity.ffmpeg_status = -1
                    entity.ffmpeg_status_kor = "분석 실패"
                    entity.refresh_status()
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
                filepath = entity.get_video_filepath()
                P.logger.debug(f"filepath:: {filepath}")
                
                # 다운로드 방법 확인
                download_method = P.ModelSetting.get(f"{self.name}_download_method")
                
                # .ytdl 파일이 있거나, ytdlp/aria2c 모드인 경우 '파일 있음'으로 건너뛰지 않음 (이어받기 허용)
                is_ytdlp = download_method in ['ytdlp', 'aria2c']
                has_ytdl_file = os.path.exists(filepath + ".ytdl")
                
                if os.path.exists(filepath) and not (is_ytdlp or has_ytdl_file):
                    logger.info(f"File already exists: {filepath}")
                    entity.ffmpeg_status = 8 # COMPLETED_EXIST
                    entity.ffmpeg_status_kor = "파일 있음"
                    entity.ffmpeg_percent = 100
                    entity.download_completed()
                    entity.refresh_status()
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

                # 다운로드 시작 전 카운트 증가
                self.current_ffmpeg_count += 1
                logger.info(f"Download started, current_ffmpeg_count: {self.current_ffmpeg_count}/{self.max_ffmpeg_count}")
                
                # 별도 스레드에서 다운로드 실행 (동시 다운로드 지원)
                def run_download(downloader_self, entity_ref, output_file_ref):
                    method = P.ModelSetting.get(f"{downloader_self.name}_download_method")
                    
                    def progress_callback(percent, current, total, speed="", elapsed=""):
                        entity_ref.ffmpeg_status = 5  # DOWNLOADING
                        if method in ["ytdlp", "aria2c"]:
                            entity_ref.ffmpeg_status_kor = f"다운로드중 (yt-dlp) {percent}%"
                        elif method in ["ffmpeg", "normal"]:
                             # SupportFfmpeg handles its own kor status via listener
                             pass
                        else:
                            entity_ref.ffmpeg_status_kor = f"다운로드중 ({percent}%)"
                        
                        entity_ref.ffmpeg_percent = percent
                        entity_ref.current_speed = speed
                        entity_ref.download_time = elapsed
                        entity_ref.refresh_status()
                    
                    # Factory를 통해 다운로더 인스턴스 획득
                    downloader = entity_ref.get_downloader(
                        video_url=video_url,
                        output_file=output_file_ref,
                        callback=progress_callback,
                        callback_function=downloader_self.callback_function
                    )
                    
                    if not downloader:
                        logger.error(f"Failed to create downloader for method: {method}")
                        downloader_self.current_ffmpeg_count -= 1
                        entity_ref.ffmpeg_status = 4 # ERROR
                        entity_ref.ffmpeg_status_kor = "다운로더 생성 실패"
                        entity_ref.refresh_status()
                        return

                    entity_ref.downloader = downloader
                    
                    # 조기 취소 체크
                    if entity_ref.cancel:
                        downloader.cancel()
                        entity_ref.ffmpeg_status_kor = "취소됨"
                        entity_ref.refresh_status()
                        downloader_self.current_ffmpeg_count -= 1
                        return
                    
                    # 다운로드 실행 (blocking)
                    logger.info(f"Executing downloader[{method}] for {output_file_ref}")
                    success = downloader.download()
                    
                    # 슬롯 반환
                    downloader_self.current_ffmpeg_count -= 1
                    logger.info(f"Download finished ({'SUCCESS' if success else 'FAILED'}), slot released. count: {downloader_self.current_ffmpeg_count}")
                    
                    if success:
                        entity_ref.ffmpeg_status = 7  # COMPLETED
                        entity_ref.ffmpeg_status_kor = "완료"
                        entity_ref.ffmpeg_percent = 100
                        entity_ref.download_completed()
                        entity_ref.refresh_status()
                        
                        # 자막 다운로드 (vtt_url이 있는 경우)
                        vtt_url = getattr(entity_ref, 'vtt', None)
                        if vtt_url:
                            from .util import Util
                            Util.download_subtitle(vtt_url, output_file_ref, headers=entity_ref.headers)
                    else:
                        # 취소 혹은 실패 처리
                        if entity_ref.cancel:
                            entity_ref.ffmpeg_status = -1
                            entity_ref.ffmpeg_status_kor = "취소됨"
                            logger.info(f"Download cancelled by user: {output_file_ref}")
                        else:
                            entity_ref.ffmpeg_status = -1
                            entity_ref.ffmpeg_status_kor = "실패"
                            logger.error(f"Download failed: {output_file_ref}")
                        entity_ref.refresh_status()

                # 스레드 시작
                download_thread = threading.Thread(
                    target=run_download,
                    args=(self, entity, output_file)
                )
                download_thread.daemon = True
                download_thread.start()
                
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
                # entity.download_completed() # Removed! Handled in run_download thread
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
                        # ffmpeg_arg가 있는 경우에만 ffmpeg 모듈로 중지
                        if entity.ffmpeg_arg is not None and entity.ffmpeg_arg.get("data") is not None:
                            try:
                                idx = entity.ffmpeg_arg["data"].get("idx")
                                if idx is not None:
                                    import ffmpeg
                                    ffmpeg.Ffmpeg.stop_by_idx(idx)
                            except Exception as e:
                                logger.debug(f"ffmpeg stop error (non-critical): {e}")
                        # 커스텀 다운로더의 경우 downloader.cancel() 호출
                        if hasattr(entity, 'downloader') and entity.downloader is not None:
                            try:
                                entity.downloader.cancel()
                                logger.info(f"Called downloader.cancel() for entity {entity_id}")
                            except Exception as e:
                                logger.debug(f"downloader cancel error: {e}")
                        entity.cancel = True
                        entity.ffmpeg_status_kor = "취소"
                        entity.refresh_status()
                        ret["ret"] = "refresh"
            elif cmd == "reset":
                if self.download_queue is not None:
                    with self.download_queue.mutex:
                        self.download_queue.queue.clear()
                    for _ in self.entity_list:
                        # 다운로드중 상태인 경우에만 중지 시도
                        if _.ffmpeg_status == 5:
                            # ffmpeg_arg가 있는 경우에만 ffmpeg 모듈로 중지
                            if _.ffmpeg_arg is not None and _.ffmpeg_arg.get("data") is not None:
                                try:
                                    import ffmpeg
                                    idx = _.ffmpeg_arg["data"].get("idx")
                                    if idx is not None:
                                        ffmpeg.Ffmpeg.stop_by_idx(idx)
                                except Exception as e:
                                    logger.debug(f"ffmpeg stop error (non-critical): {e}")
                            # 커스텀 다운로더의 경우 cancel 플래그만 설정
                            _.cancel = True
                            _.ffmpeg_status_kor = "취소"
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
