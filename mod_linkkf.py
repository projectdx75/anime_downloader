#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 3:44 PM
# @Author  : yommi
# @Site    :
# @File    : logic_linkkf
# @Software: PyCharm
import json
import ipaddress
import os
import random
import re
import sys
import time
import traceback
import urllib
from datetime import datetime
from urllib.parse import urlparse

# third-party
import requests
from bs4 import BeautifulSoup

# third-party
from flask import jsonify, render_template, request
from support.expand.ffmpeg import SupportFfmpeg

# sjva 공용
from framework import db, path_data, scheduler
from lxml import html
from .mod_base import AnimeModuleBase
from requests_cache import CachedSession

# GDM Integration
try:
    from gommi_downloader_manager.mod_queue import ModuleQueue
except ImportError:
    ModuleQueue = None

# cloudscraper는 lazy import로 처리
import cloudscraper

from anime_downloader.lib.ffmpeg_queue_v1 import FfmpegQueue, FfmpegQueueEntity
from anime_downloader.lib.util import Util
from .mod_ohli24 import LogicOhli24

# 패키지
# from .plugin import P
from anime_downloader.setup import *

# from linkkf.model import ModelLinkkfProgram

# from linkkf.model import ModelLinkkfProgram

# from tool_base import d


logger = P.logger
name = "linkkf"


class LogicLinkkf(AnimeModuleBase):
    current_headers = None
    current_data = None
    referer = None
    download_queue = None
    download_thread = None
    current_download_count = 0
    _scraper = None  # cloudscraper 싱글톤
    _view_stream_cache = {}
    _view_stream_cache_ttl = 900  # 15분
    _view_session = requests.Session()
    queue = None  # 클래스 레벨에서 큐 관리

    cache_path = os.path.dirname(__file__)

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/71.0.3578.98 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "",
    }
    useragent = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
    }

    @staticmethod
    def _normalize_listing_item(item, rank=None):
        postid = str(item.get("postid") or item.get("code") or "")
        postname = item.get("postname") or item.get("title") or item.get("name") or ""
        postthum = item.get("postthum") or item.get("image_link") or ""
        postnote = item.get("postnote") or item.get("chapter") or item.get("postnoti") or item.get("seasontype") or ""

        normalized = {
            "postid": postid,
            "postname": postname,
            "postthum": postthum,
            "postnote": postnote,
        }
        if rank is not None:
            normalized["rank"] = rank
        return normalized

    @staticmethod
    def _build_listing_payload(items, page=1, total_page=1, extra=None):
        normalized_items = []
        for item in (items or []):
            normalized_items.append(
                LogicLinkkf._normalize_listing_item(item, rank=item.get("rank") if isinstance(item, dict) else None)
            )

        payload = {
            "ret": "success",
            "page": page,
            "total_page": total_page,
            "episode_count": len(normalized_items),
            "count": len(normalized_items),
            "data": normalized_items,
            "episode": [
                {
                    "code": item["postid"],
                    "title": item["postname"],
                    "image_link": item["postthum"],
                    "link": f"https://linkkf.live/{item['postid']}" if item["postid"] else "",
                    "chapter": item["postnote"],
                }
                for item in normalized_items
            ],
        }
        if extra:
            payload.update(extra)
        return payload

    def __init__(self, P):
        super(LogicLinkkf, self).__init__(P, setup_default=self.db_default, name=name, first_menu='setting', scheduler_desc="linkkf 자동 다운로드")
        # self.queue = None  # 인스턴스 레벨 초기화 제거 (클래스 레벨 사용)
        self.db_default = {
            "linkkf_db_version": "1",
            "linkkf_url": "https://linkkf.live",
            f"{self.name}_recent_code": "",
            "linkkf_download_path": os.path.join(path_data, P.package_name, "linkkf"),
            "linkkf_save_path": os.path.join(path_data, P.package_name, "linkkf"),
            "linkkf_auto_make_folder": "True",
            "linkkf_auto_make_season_folder": "True",
            "linkkf_finished_insert": "[완결]",
            "linkkf_max_ffmpeg_process_count": "2",
            f"{self.name}_max_download_count": "2",
            f"{self.name}_quality": "720p",
            "linkkf_order_desc": "False",
            "linkkf_auto_start": "False",
            "linkkf_interval": "* 5 * * *",
            "linkkf_auto_mode_all": "False",
            "linkkf_auto_code_list": "all",
            "linkkf_current_code": "",
            "linkkf_uncompleted_auto_enqueue": "False",
            "linkkf_image_url_prefix_series": "",
            "linkkf_image_url_prefix_episode": "",
            "linkkf_download_method": "ffmpeg",  # ffmpeg, ytdlp, aria2c
            "linkkf_download_threads": "16",     # yt-dlp/aria2c 병렬 쓰레드 수
            # 알림 설정
            "linkkf_notify_enabled": "False",
            "linkkf_discord_webhook_url": "",
            "linkkf_telegram_bot_token": "",
            "linkkf_telegram_chat_id": "",
        }
        # default_route_socketio(P, self)
        self.web_list_model = ModelLinkkfItem
        default_route_socketio_module(self, attach="/setting")
        self.current_data = None


    def process_ajax(self, sub, req):
        try:
            if sub == "analysis":
                # code = req.form['code']
                code = request.form["code"]

                wr_id = request.form.get("wr_id", None)
                bo_table = request.form.get("bo_table", None)
                data = []
                # print(code)
                # logger.info("code::: %s", code)
                P.ModelSetting.set("linkkf_current_code", code)
                data = self.get_series_info(code)
                self.current_data = data
                return jsonify({"ret": "success", "data": data, "code": code})
            elif sub == "anime_list":
                data = []
                cate = request.form["type"]
                page = request.form["page"]
                top_type = request.form.get("top_type", "month")

                data = self.get_anime_info(cate, page, top_type=top_type)
                # self.current_data = data
                return jsonify(
                    {"ret": "success", "cate": cate, "page": page, "data": data}
                )
            elif sub == "screen_movie_list":
                try:
                    # logger.debug("request:::> %s", request.form["page"])
                    page = request.form["page"]
                    data = self.get_screen_movie_info(page)
                    dummy_data = {"ret": "success", "data": data}
                    return jsonify(data)
                except Exception as e:
                    logger.error(f"Exception: {str(e)}")
                    logger.error(traceback.format_exc())
            elif sub == "complete_list":
                pass
            elif sub == "search":
                data = []
                # cate = request.form["type"]
                # page = request.form["page"]
                cate = request.form["type"]
                query = request.form["query"]
                page = request.form["page"]

                data = self.get_search_result(query, page, cate)
                # self.current_data = data
                return jsonify(
                    {
                        "ret": "success",
                        "cate": cate,
                        "page": page,
                        "query": query,
                        "data": data,
                    }
                )
            elif sub == "add_queue":
                logger.info("========= add_queue START =========")
                logger.debug("linkkf add_queue routine ===============")
                ret = {}
                try:
                    form_data = request.form.get("data")
                    if not form_data:
                        logger.error(f"No data in form. Form keys: {list(request.form.keys())}")
                        ret["ret"] = "error"
                        ret["log"] = "No data received"
                        return jsonify(ret)
                    info = json.loads(form_data)
                    logger.info(f"info:: {info}")
                    ret["ret"] = self.add(info)
                except Exception as e:
                    logger.error(f"add_queue error: {e}")
                    logger.error(traceback.format_exc())
                    ret["ret"] = "error"
                    ret["log"] = str(e)
                return jsonify(ret)
            elif sub == "add_queue_checked_list":
                # 선택된 에피소드 일괄 추가 (백그라운드 스레드로 처리)
                import threading
                from flask import current_app
                
                logger.info("========= add_queue_checked_list START =========")
                ret = {"ret": "success", "message": "백그라운드에서 추가 중..."}
                try:
                    form_data = request.form.get("data")
                    if not form_data:
                        ret["ret"] = "error"
                        ret["log"] = "No data received"
                        return jsonify(ret)
                    
                    episode_list = json.loads(form_data)
                    logger.info(f"Received {len(episode_list)} episodes to add in background")
                    
                    # Flask app 참조 저장 (스레드에서 사용)
                    app = current_app._get_current_object()
                    
                    # 백그라운드 스레드에서 추가 작업 수행
                    def add_episodes_background(flask_app, downloader_self, episodes):
                        added = 0
                        skipped = 0
                        with flask_app.app_context():
                            for episode_info in episodes:
                                try:
                                    result = downloader_self.add(episode_info)
                                    if result in ["enqueue_db_append", "enqueue_db_exist"]:
                                        added += 1
                                        logger.debug(f"Added episode {episode_info.get('_id')}")
                                    else:
                                        skipped += 1
                                        logger.debug(f"Skipped episode {episode_info.get('_id')}: {result}")
                                except Exception as ep_err:
                                    logger.error(f"Error adding episode: {ep_err}")
                                    skipped += 1
                            
                            logger.info(f"add_queue_checked_list completed: added={added}, skipped={skipped}")
                    
                    thread = threading.Thread(
                        target=add_episodes_background,
                        args=(app, self, episode_list)
                    )
                    thread.daemon = True
                    thread.start()
                    
                    ret["count"] = len(episode_list)
                    
                except Exception as e:
                    logger.error(f"add_queue_checked_list error: {e}")
                    logger.error(traceback.format_exc())
                    ret["ret"] = "error"
                    ret["log"] = str(e)
                return jsonify(ret)
            elif sub == "add_sub_queue_checked_list":
                # 선택된 에피소드 자막만 일괄 다운로드 (백그라운드 스레드로 처리)
                import threading
                from flask import current_app
                
                logger.info("========= add_sub_queue_checked_list START =========")
                ret = {"ret": "success", "message": "백그라운드에서 자막 다운로드 중..."}
                try:
                    form_data = request.form.get("data")
                    if not form_data:
                        ret["ret"] = "error"
                        ret["log"] = "No data received"
                        return jsonify(ret)
                    
                    episode_list = json.loads(form_data)
                    logger.info(f"Received {len(episode_list)} episodes to download subtitles in background")
                    
                    # Flask app 참조 저장
                    app = current_app._get_current_object()
                    
                    def download_subtitles_background(flask_app, episode_list):
                        added = 0
                        skipped = 0
                        with flask_app.app_context():
                            for episode_info in episode_list:
                                try:
                                    # LinkkfQueueEntity를 사용하여 자막 URL 추출 (prepare_extra 활용)
                                    entity = LinkkfQueueEntity(P, self, episode_info)
                                    entity.prepare_extra()
                                    
                                    if entity.vtt:
                                        # 자막 다운로드 및 변환
                                        # entity.filepath는 prepare_extra에서 설정됨 (기본 저장 경로 + 파일명)
                                        res = Util.download_subtitle(entity.vtt, entity.filepath, headers=entity.headers)
                                        if res:
                                            added += 1
                                            logger.debug(f"Downloaded subtitle for {episode_info.get('title')}")
                                        else:
                                            skipped += 1
                                            logger.info(f"Failed to download subtitle for {episode_info.get('title')}")
                                    else:
                                        skipped += 1
                                        logger.info(f"No subtitle found for {episode_info.get('title')}")
                                except Exception as e:
                                    logger.error(f"Error in download_subtitles_background for one episode: {e}")
                                    skipped += 1
                            
                            logger.info(f"add_sub_queue_checked_list completed: downloaded={added}, skipped={skipped}")

                    thread = threading.Thread(
                        target=download_subtitles_background,
                        args=(app, episode_list)
                    )
                    thread.daemon = True
                    thread.start()
                    
                    ret["count"] = len(episode_list)
                except Exception as e:
                    logger.error(f"add_sub_queue_checked_list error: {e}")
                    logger.error(traceback.format_exc())
                    ret["ret"] = "error"
                    ret["log"] = str(e)
                return jsonify(ret)
            elif sub == "web_list":
                ret = ModelLinkkfItem.web_list(req)
                return jsonify(ret)
            elif sub == "db_remove":
                db_id = request.form.get("id")
                if not db_id:
                    return jsonify({"ret": "error", "log": "No ID provided"})
                return jsonify(ModelLinkkfItem.delete_by_id(db_id))

            elif sub == "merge_subtitle":
                # 자막 합치기 - ffmpeg로 SRT를 MP4에 삽입
                import subprocess
                import shutil
                
                db_id = request.form.get("id")
                if not db_id:
                    return jsonify({"ret": "error", "message": "No ID provided"})
                
                try:
                    db_item = ModelLinkkfItem.get_by_id(int(db_id))
                    if not db_item:
                        return jsonify({"ret": "error", "message": "Item not found"})
                    
                    mp4_path = db_item.filepath
                    if not mp4_path or not os.path.exists(mp4_path):
                        return jsonify({"ret": "error", "message": f"MP4 file not found: {mp4_path}"})
                    
                    # SRT 파일 경로 (MP4와 동일 경로에 .srt 확장자)
                    srt_path = os.path.splitext(mp4_path)[0] + ".srt"
                    if not os.path.exists(srt_path):
                        return jsonify({"ret": "error", "message": f"SRT file not found: {srt_path}"})
                    
                    # 출력 파일: *_subed.mp4
                    base_name = os.path.splitext(mp4_path)[0]
                    output_path = f"{base_name}_subed.mp4"
                    
                    # 이미 존재하면 덮어쓰기 전 확인
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    
                    # ffmpeg 명령어: 자막을 soft embed (mov_text 코덱)
                    # -i mp4 -i srt -c:v copy -c:a copy -c:s mov_text output
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
                    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=300)
                    
                    if result.returncode != 0:
                        logger.error(f"ffmpeg error: {result.stderr}")
                        return jsonify({"ret": "error", "message": f"ffmpeg failed: {result.stderr[-200:]}"})
                    
                    if not os.path.exists(output_path):
                        return jsonify({"ret": "error", "message": "Output file was not created"})
                    
                    output_size = os.path.getsize(output_path)
                    logger.info(f"[Merge Subtitle] Created: {output_path} ({output_size} bytes)")
                    
                    return jsonify({
                        "ret": "success", 
                        "message": f"자막 합침 완료!",
                        "output_file": os.path.basename(output_path),
                        "output_size": output_size
                    })
                    
                except subprocess.TimeoutExpired:
                    return jsonify({"ret": "error", "message": "ffmpeg timeout (5분 초과)"})
                except Exception as e:
                    logger.error(f"merge_subtitle error: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"ret": "error", "message": str(e)})

            elif sub == "get_playlist":
                # 현재 파일과 같은 폴더에서 다음 에피소드들 찾기
                try:
                    file_path = request.args.get("path", "")
                    if not file_path or not os.path.exists(file_path):
                        return jsonify({"error": "File not found", "playlist": [], "current_index": 0}), 404
                    
                    # 보안 체크
                    download_path = P.ModelSetting.get("linkkf_download_path")
                    if not file_path.startswith(download_path):
                        return jsonify({"error": "Access denied", "playlist": [], "current_index": 0}), 403
                    
                    folder = os.path.dirname(file_path)
                    current_file = os.path.basename(file_path)
                    
                    # 파일명에서 SxxExx 패턴 추출
                    ep_match = re.search(r'\.S(\d+)E(\d+)\.', current_file, re.IGNORECASE)
                    if not ep_match:
                        # 패턴 없으면 현재 파일만 반환
                        return jsonify({
                            "playlist": [{"path": file_path, "name": current_file}],
                            "current_index": 0
                        })
                    
                    current_season = int(ep_match.group(1))
                    current_episode = int(ep_match.group(2))
                    
                    # 같은 폴더의 모든 mp4 파일 가져오기
                    all_files = []
                    for f in os.listdir(folder):
                        if f.endswith('.mp4'):
                            match = re.search(r'\.S(\d+)E(\d+)\.', f, re.IGNORECASE)
                            if match:
                                s = int(match.group(1))
                                e = int(match.group(2))
                                all_files.append({
                                    "path": os.path.join(folder, f),
                                    "name": f,
                                    "season": s,
                                    "episode": e
                                })
                    
                    # 시즌/에피소드 순으로 정렬
                    all_files.sort(key=lambda x: (x["season"], x["episode"]))
                    
                    # 현재 에피소드 이상인 것만 필터링 (현재 + 다음 에피소드들)
                    playlist = []
                    current_index = 0
                    for i, f in enumerate(all_files):
                        if f["season"] == current_season and f["episode"] >= current_episode:
                            entry = {"path": f["path"], "name": f["name"]}
                            if f["episode"] == current_episode:
                                current_index = len(playlist)
                            playlist.append(entry)
                    
                    logger.info(f"Linkkf Playlist: {len(playlist)} items, current_index: {current_index}")
                    return jsonify({
                        "playlist": playlist,
                        "current_index": current_index
                    })
                    
                except Exception as e:
                    logger.error(f"Get playlist error: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"error": str(e), "playlist": [], "current_index": 0}), 500

            elif sub == "stream_video":
                # 비디오 스트리밍 (MP4 파일 직접 서빙)
                try:
                    from flask import send_file, Response
                    import mimetypes
                    
                    file_path_raw = request.args.get("path", "")
                    if not file_path_raw:
                        return "File not found", 404

                    file_path = os.path.realpath(os.path.expanduser(file_path_raw))
                    if not os.path.isfile(file_path):
                        return "File not found", 404
                    
                    # 보안 체크: 다운로드 경로 내에 있는지 확인
                    download_path_raw = P.ModelSetting.get("linkkf_download_path") or ""
                    download_path = os.path.realpath(os.path.expanduser(download_path_raw))
                    if not download_path:
                        return "Access denied", 403
                    try:
                        if os.path.commonpath([file_path, download_path]) != download_path:
                            return "Access denied", 403
                    except ValueError:
                        return "Access denied", 403
                        
                    file_size = os.path.getsize(file_path)
                    mime_type = mimetypes.guess_type(file_path)[0] or "video/mp4"
                    range_header = request.headers.get('Range', None)
                    
                    if not range_header:
                        rv = send_file(file_path, mimetype=mime_type, as_attachment=False, conditional=True)
                        rv.headers.add('Accept-Ranges', 'bytes')
                        return rv
                    
                    # Range Request 처리 (seeking 지원)
                    byte1, byte2 = 0, None
                    m = re.search('(\d+)-(\d*)', range_header)
                    if m:
                        g = m.groups()
                        byte1 = int(g[0])
                        if g[1]:
                            byte2 = int(g[1])
                    
                    if byte2 is None:
                        byte2 = file_size - 1
                    if byte1 > byte2 or byte2 >= file_size:
                        return "Invalid range", 416
                    
                    length = byte2 - byte1 + 1
                    
                    with open(file_path, 'rb') as f:
                        f.seek(byte1)
                        data = f.read(length)
                    
                    rv = Response(data, 206, mimetype=mime_type, content_type=mime_type, direct_passthrough=True)
                    rv.headers.add('Content-Range', 'bytes {0}-{1}/{2}'.format(byte1, byte2, file_size))
                    rv.headers.add('Accept-Ranges', 'bytes')
                    rv.headers.add('Content-Length', str(length))
                    return rv
                except Exception as e:
                    logger.error(f"Stream video error: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"error": str(e)}), 500
            elif sub == "resolve_remote_stream":
                # 원본 사이트 playid URL -> 실제 스트림(m3u8) / 자막(vtt) 추출
                try:
                    playid_url = (
                        request.form.get("playid_url")
                        or request.form.get("url")
                        or request.args.get("playid_url")
                        or request.args.get("url")
                        or ""
                    ).strip()

                    if not playid_url:
                        return jsonify({"ret": "error", "log": "playid_url is required"})

                    stream_url, referer_url, subtitle_url = LogicLinkkf.extract_video_url_from_playid(
                        playid_url,
                        light_mode=True,
                    )
                    if not stream_url:
                        return jsonify(
                            {
                                "ret": "error",
                                "log": "스트림 URL(m3u8) 추출에 실패했습니다.",
                                "playid_url": playid_url,
                            }
                        )

                    return jsonify(
                        {
                            "ret": "success",
                            "stream_url": stream_url,
                            "subtitle_url": subtitle_url,
                            "referer_url": referer_url,
                            "playid_url": playid_url,
                            "cached": True if LogicLinkkf._get_cached_view_stream(playid_url) else False,
                        }
                    )
                except Exception as e:
                    logger.error(f"resolve_remote_stream error: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"ret": "error", "log": str(e)})
            elif sub == "prefetch_remote_stream":
                # request 분석 직후 첫 화 URL prewarm
                try:
                    playid_url = (
                        request.form.get("playid_url")
                        or request.form.get("url")
                        or request.args.get("playid_url")
                        or request.args.get("url")
                        or ""
                    ).strip()
                    if not playid_url:
                        return jsonify({"ret": "error", "log": "playid_url is required"})

                    cached = LogicLinkkf._get_cached_view_stream(playid_url)
                    if cached:
                        return jsonify({"ret": "success", "cached": True})

                    stream_url, referer_url, subtitle_url = LogicLinkkf.extract_video_url_from_playid(
                        playid_url,
                        light_mode=True,
                    )
                    if not stream_url:
                        return jsonify({"ret": "error", "cached": False, "log": "prefetch miss"})

                    return jsonify(
                        {
                            "ret": "success",
                            "cached": False,
                            "stream_url": stream_url,
                            "subtitle_url": subtitle_url,
                            "referer_url": referer_url,
                        }
                    )
                except Exception as e:
                    logger.error(f"prefetch_remote_stream error: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"ret": "error", "log": str(e)})
            elif sub == "proxy_remote_media":
                # CORS/핫링크 차단 회피를 위해 원격 HLS/자막을 서버 프록시로 중계
                try:
                    from flask import Response
                    from urllib.parse import quote, urljoin, urlparse

                    media_url = (request.args.get("url") or "").strip()
                    referer_url = (request.args.get("referer") or "https://linkkf.live/").strip()
                    if not media_url:
                        return jsonify({"ret": "error", "log": "url is required"}), 400

                    parsed = urlparse(media_url)
                    if parsed.scheme not in ("http", "https"):
                        return jsonify({"ret": "error", "log": "invalid url scheme"}), 400

                    # 최소한의 오픈 프록시 방지:
                    # localhost/사설망/loopback 주소로의 요청은 차단
                    host = (parsed.netloc or "").lower()
                    host_only = host.split(":", 1)[0]
                    if host_only in ("localhost",):
                        return jsonify({"ret": "error", "log": f"host not allowed: {host}"}), 403
                    try:
                        ip_obj = ipaddress.ip_address(host_only)
                        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                            return jsonify({"ret": "error", "log": f"host not allowed: {host}"}), 403
                    except ValueError:
                        # 도메인인 경우 통과
                        pass

                    req_headers = {
                        "User-Agent": LogicLinkkf.headers.get("User-Agent")
                        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": referer_url,
                        "Accept": "*/*",
                    }
                    range_header = request.headers.get("Range")
                    if range_header:
                        req_headers["Range"] = range_header

                    # 일부 CDN은 Origin 체크를 요구하는 경우가 있어 함께 전달
                    req_headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"

                    remote_res = requests.get(
                        media_url,
                        headers=req_headers,
                        timeout=20,
                        allow_redirects=True,
                    )

                    remote_ct = remote_res.headers.get("Content-Type", "")
                    remote_body = remote_res.content

                    if remote_res.status_code >= 400:
                        return Response(
                            remote_body,
                            status=remote_res.status_code,
                            content_type=remote_ct or "text/plain; charset=utf-8",
                        )

                    body_head = remote_body[:64].decode("utf-8", "ignore")
                    is_playlist = (
                        ".m3u8" in media_url.lower()
                        or "mpegurl" in remote_ct.lower()
                        or body_head.startswith("#EXTM3U")
                    )

                    def build_proxy_url(target_url):
                        return (
                            f"/{P.package_name}/ajax/{self.name}/proxy_remote_media"
                            f"?url={quote(target_url, safe='')}"
                            f"&referer={quote(referer_url, safe='')}"
                        )

                    if is_playlist:
                        playlist_text = remote_body.decode("utf-8", "ignore")
                        rewritten_lines = []
                        key_uri_pattern = re.compile(r'URI="([^"]+)"')

                        for raw_line in playlist_text.splitlines():
                            line = raw_line.strip()
                            if not line:
                                rewritten_lines.append(raw_line)
                                continue

                            if line.startswith("#"):
                                # #EXT-X-KEY, #EXT-X-MAP 등의 URI 속성 재작성
                                if 'URI="' in raw_line:
                                    def _replace_uri(match):
                                        abs_uri = urljoin(media_url, match.group(1))
                                        return f'URI="{build_proxy_url(abs_uri)}"'

                                    raw_line = key_uri_pattern.sub(_replace_uri, raw_line)
                                rewritten_lines.append(raw_line)
                                continue

                            abs_media = urljoin(media_url, line)
                            rewritten_lines.append(build_proxy_url(abs_media))

                        rewritten_playlist = "\n".join(rewritten_lines)
                        resp = Response(
                            rewritten_playlist,
                            status=200,
                            content_type="application/vnd.apple.mpegurl; charset=utf-8",
                        )
                        resp.headers["Cache-Control"] = "no-store"
                        return resp

                    resp = Response(
                        remote_body,
                        status=remote_res.status_code,
                        content_type=remote_ct or "application/octet-stream",
                    )
                    # 스트리밍 탐색(seek) 관련 헤더 전달
                    if "Content-Length" in remote_res.headers:
                        resp.headers["Content-Length"] = remote_res.headers["Content-Length"]
                    if "Accept-Ranges" in remote_res.headers:
                        resp.headers["Accept-Ranges"] = remote_res.headers["Accept-Ranges"]
                    if "Content-Range" in remote_res.headers:
                        resp.headers["Content-Range"] = remote_res.headers["Content-Range"]
                    resp.headers["Cache-Control"] = "no-store"
                    return resp
                except Exception as e:
                    logger.error(f"proxy_remote_media error: {e}")
                    logger.error(traceback.format_exc())
                    return jsonify({"ret": "error", "log": str(e)}), 500

            # 매치되는 sub가 없는 경우 기본 응답
            if sub == "browse_dir":
                try:
                    path = request.form.get("path", "")
                    if not path or not os.path.exists(path):
                        path = P.ModelSetting.get("linkkf_download_path") or os.path.expanduser("~")
                    path = os.path.abspath(path)
                    if not os.path.isdir(path):
                        path = os.path.dirname(path)
                    directories = []
                    try:
                        for item in sorted(os.listdir(path)):
                            item_path = os.path.join(path, item)
                            if os.path.isdir(item_path) and not item.startswith('.'):
                                directories.append({"name": item, "path": item_path})
                    except PermissionError:
                        pass
                    parent = os.path.dirname(path) if path != "/" else None
                    return jsonify({
                        "ret": "success",
                        "current_path": path,
                        "parent_path": parent,
                        "directories": directories
                    })
                except Exception as e:
                    logger.error(f"browse_dir error: {e}")
                    return jsonify({"ret": "error", "error": str(e)}), 500

            elif sub == "test_notification":
                # 테스트 알림 전송
                try:
                    discord_url = P.ModelSetting.get("linkkf_discord_webhook_url")
                    telegram_token = P.ModelSetting.get("linkkf_telegram_bot_token")
                    telegram_chat_id = P.ModelSetting.get("linkkf_telegram_chat_id")
                    
                    if not discord_url and not (telegram_token and telegram_chat_id):
                        return jsonify({"ret": "error", "msg": "Discord Webhook URL 또는 Telegram 설정을 입력하세요."})
                    
                    test_message = "🔔 **테스트 알림**\nLinkkf 알림 설정이 완료되었습니다!\n\n알림이 정상적으로 수신되고 있습니다."
                    sent_to = []
                    
                    if discord_url:
                        self.send_discord_notification(discord_url, "테스트", test_message)
                        sent_to.append("Discord")
                    
                    if telegram_token and telegram_chat_id:
                        self.send_telegram_notification(telegram_token, telegram_chat_id, test_message)
                        sent_to.append("Telegram")
                    
                    return jsonify({"ret": "success", "msg": f"{', '.join(sent_to)}으로 알림 전송 완료!"})
                except Exception as e:
                    logger.error(f"test_notification error: {e}")
                    return jsonify({"ret": "error", "msg": str(e)})

            return super().process_ajax(sub, req)

        except Exception as e:
            P.logger.error(f"Exception: {str(e)}")
            P.logger.error(traceback.format_exc())
            return jsonify({"ret": "error", "log": str(e)})

    def process_command(self, command, arg1, arg2, arg3, req):
        try:
            if command == "list":
                # 1. 자체 큐 목록 가져오기
                ret = self.queue.get_entity_list() if self.queue else []
                
                # 2. GDM 태스크 가져오기 (설치된 경우)
                try:
                    from gommi_downloader_manager.mod_queue import ModuleQueue
                    if ModuleQueue:
                        gdm_tasks = ModuleQueue.get_all_downloads()
                        # 이 모듈(linkkf)이 추가한 작업만 필터링
                        linkkf_tasks = [t for t in gdm_tasks if t.caller_plugin == f"{P.package_name}_{self.name}"]
                        
                        for task in linkkf_tasks:
                            # 템플릿 호환 형식으로 변환
                            gdm_item = self._convert_gdm_task_to_queue_item(task)
                            ret.append(gdm_item)
                except Exception as e:
                    logger.debug(f"GDM tasks fetch error: {e}")
                
                return jsonify(ret)
                
            elif command in ["stop", "remove", "cancel"]:
                entity_id = arg1
                if entity_id and str(entity_id).startswith("dl_"):
                    # GDM 작업 처리
                    try:
                        from gommi_downloader_manager.mod_queue import ModuleQueue
                        if ModuleQueue:
                            if command == "stop" or command == "cancel":
                                task = ModuleQueue.get_download(entity_id)
                                if task:
                                    task.cancel()
                                    return jsonify({"ret": "success", "log": "GDM 작업을 중지하였습니다."})
                            elif command == "remove":
                                # GDM에서 삭제 처리 (명령어 'delete' 사용)
                                # process_ajax의 delete 로직 참고
                                class DummyReq:
                                    def __init__(self, id):
                                        self.form = {"id": id}
                                ModuleQueue.process_ajax("delete", DummyReq(entity_id))
                                return jsonify({"ret": "success", "log": "GDM 작업을 삭제하였습니다."})
                    except Exception as e:
                        logger.error(f"GDM command error: {e}")
                        return jsonify({"ret": "error", "log": f"GDM 명령 실패: {e}"})
                
                # 자체 큐 처리
                return super().process_command(command, arg1, arg2, arg3, req)
                
            return super().process_command(command, arg1, arg2, arg3, req)
        except Exception as e:
            logger.error(f"process_command Error: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'ret': 'fail', 'log': str(e)})

    def _convert_gdm_task_to_queue_item(self, task):
        """GDM DownloadTask 객체를 FfmpegQueueEntity.as_dict() 호환 형식으로 변환"""
        # 상태 맵핑
        status_kor_map = {
            "pending": "대기중",
            "extracting": "분석중",
            "downloading": "다운로드중",
            "paused": "일시정지",
            "completed": "완료",
            "error": "실패",
            "cancelled": "취소됨"
        }
        
        status_str_map = {
            "pending": "WAITING",
            "extracting": "ANALYZING",
            "downloading": "DOWNLOADING",
            "paused": "PAUSED",
            "completed": "COMPLETED",
            "error": "FAILED",
            "cancelled": "FAILED"
        }
        
        # GDM task는 as_dict()를 제공함
        t_dict = task.as_dict()
        
        return {
            "entity_id": t_dict["id"],
            "url": t_dict["url"],
            "filename": t_dict["filename"] or t_dict["title"],
            "status_kor": status_kor_map.get(t_dict["status"], "알수없음"),
            "percent": t_dict["progress"],
            "created_time": t_dict["created_time"],
            "current_speed": t_dict["speed"] or "0 B/s",
            "download_time": t_dict["eta"] or "-",
            "status_str": status_str_map.get(t_dict["status"], "WAITING"),
            "idx": t_dict["id"],
            "callback_id": "linkkf",
            "start_time": t_dict["start_time"] or t_dict["created_time"],
            "save_fullpath": t_dict["filepath"],
            "duration_str": "GDM",
            "current_pf_count": 0,
            "duration": "-",
            "current_duration": "-",
            "current_bitrate": "-",
            "max_pf_count": 0,
            "is_gdm": True
        }

    def plugin_callback(self, data):
        """
        GDM 모듈로부터 다운로드 상태 업데이트 수신
        data = {
            'callback_id': self.callback_id,
            'status': self.status,
            'filepath': self.filepath,
            'filename': os.path.basename(self.filepath) if self.filepath else '',
            'error': self.error_message
        }
        """
        try:
            callback_id = data.get('callback_id')
            status = data.get('status')
            
            logger.info(f"[Linkkf] Received GDM callback: id={callback_id}, status={status}")
            
            # DB 상태 업데이트
            if callback_id:
                from framework import F
                with F.app.app_context():
                    db_item = ModelLinkkfItem.get_by_linkkf_id(callback_id)
                    if db_item:
                        if status == "completed":
                            db_item.status = "completed"
                            db_item.completed_time = datetime.now()
                            # 경로 정규화 후 저장
                            new_filepath = data.get('filepath')
                            if new_filepath:
                                db_item.filepath = os.path.normpath(new_filepath)
                            db_item.save()
                            logger.info(f"[Linkkf] Successfully updated DB item {db_item.id} (Linkkf ID: {callback_id}) to COMPLETED via GDM callback")
                            logger.info(f"[Linkkf] Final filepath in DB: {db_item.filepath}")
                            
                            # 알림 전송 (필요 시)
                            # self.socketio_callback("list_refresh", "")
                        elif status == "error":
                            # 필요 시 에러 처리
                            pass
        except Exception as e:
            logger.error(f"[Linkkf] Callback processing error: {e}")
            logger.error(traceback.format_exc())

    def socketio_callback(self, refresh_type, data):
        """
        socketio를 통해 클라이언트에 상태 업데이트 전송
        refresh_type: 'add', 'status', 'last' 등
        data: entity.as_dict() 데이터
        """
        logger.info(f">>> socketio_callback called: {refresh_type}, {data.get('percent', 'N/A')}%")
        try:
            from framework import socketio
            
            # FlaskFarm의 기존 패턴: /framework namespace로 emit
            # queue 페이지의 소켓이 이 메시지를 받아서 처리
            namespace = f"/{P.package_name}/{self.name}/queue"
            
            # 먼저 queue에 직접 emit (기존 방식)
            socketio.emit(refresh_type, data, namespace=namespace)
            
            # /framework namespace로도 notify 이벤트 전송
            notify_data = {
                "type": "success",
                "msg": f"다운로드중 {data.get('percent', 0)}% - {data.get('filename', '')}",
            }
            socketio.emit("notify", notify_data, namespace="/framework")
            logger.info(f">>> socketio.emit completed to /framework")
                
        except Exception as e:
            logger.error(f"socketio_callback error: {e}")

    @staticmethod
    def _extract_cat1_urls(html_content):
        """cat1 = [...] 패턴에서 URL 목록 추출 (중복 코드 제거용 헬퍼)"""
        regex = r"cat1 = [^\[]*([^\]]*)"
        cat_match = re.findall(regex, html_content)
        if not cat_match:
            return []
        url_regex = r"\"([^\"]*)\""
        return re.findall(url_regex, cat_match[0])

    @staticmethod
    def get_html(url, cached=False, timeout=10):
        try:
            if LogicLinkkf.referer is None:
                LogicLinkkf.referer = f"{P.ModelSetting.get('linkkf_url')}"

            return LogicLinkkf.get_html_cloudflare(url, timeout=timeout)

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_html_cloudflare(url, cached=False, timeout=10):
        """Cloudflare 보호 우회를 위한 HTTP 요청 ( Zendriver Daemon -> Subprocess -> Camoufox -> Scraper 순)"""
        start_time = time.time()
        
        # 0. Referer 설정
        if LogicLinkkf.referer is None:
            LogicLinkkf.referer = f"{P.ModelSetting.get('linkkf_url')}"
        
        LogicLinkkf.headers["Referer"] = LogicLinkkf.referer or ""

        # 1. Zendriver Daemon 시도 (최우선)
        try:
            if LogicOhli24.is_zendriver_daemon_running():
                logger.info(f"[Linkkf] Trying Zendriver Daemon: {url}")
                daemon_res = LogicOhli24.fetch_via_daemon(url, timeout=30, headers=LogicLinkkf.headers)
                if daemon_res.get("success") and daemon_res.get("html"):
                    elapsed = time.time() - start_time
                    logger.info(f"[Linkkf] Daemon success in {elapsed:.2f}s")
                    return daemon_res["html"]
        except Exception as e:
            logger.warning(f"[Linkkf] Daemon error: {e}")

        # 2. Scraper 시도 (기본)
        try:
            if LogicLinkkf._scraper is None:
                LogicLinkkf._scraper = cloudscraper.create_scraper(
                    delay=10,
                    browser={"custom": "linkkf"},
                )
            
            user_agents_list = [
                "Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.83 Safari/537.36",
            ]
            LogicLinkkf.headers["User-Agent"] = random.choice(user_agents_list)
            
            response = LogicLinkkf._scraper.get(url, headers=LogicLinkkf.headers, timeout=timeout)
            
            # 챌린지 페이지가 아닌 실제 콘텐츠가 포함되었는지 확인
            content = response.text
            if "Cloudflare" not in content or "video-player" in content or "iframe" in content:
                return content
            
            logger.warning("[Linkkf] Scraper returned challenge page, falling back to browser...")
        except Exception as e:
            logger.warning(f"[Linkkf] Scraper error: {e}")

        # 3. Zendriver Subprocess Fallback
        try:
            if LogicOhli24.ensure_zendriver_installed():
                logger.info(f"[Linkkf] Trying Zendriver subprocess: {url}")
                script_path = os.path.join(os.path.dirname(__file__), "lib", "zendriver_ohli24.py")
                cmd = [sys.executable, script_path, url, str(30)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0 and result.stdout.strip():
                    zd_result = json.loads(result.stdout.strip())
                    if zd_result.get("success") and zd_result.get("html"):
                        return zd_result["html"]
        except Exception as e:
            logger.warning(f"[Linkkf] Zendriver fallback error: {e}")

        # 4. Camoufox Fallback
        try:
            logger.info(f"[Linkkf] Trying Camoufox fallback: {url}")
            script_path = os.path.join(os.path.dirname(__file__), "lib", "camoufox_ohli24.py")
            result = subprocess.run([sys.executable, script_path, url, str(30)], capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and result.stdout.strip():
                cf_result = json.loads(result.stdout.strip())
                if cf_result.get("success") and cf_result.get("html"):
                    return cf_result["html"]
        except Exception as e:
            logger.warning(f"[Linkkf] Camoufox fallback error: {e}")

        return ""

    @staticmethod
    def add_whitelist(*args):
        ret = {}

        logger.debug(f"args: {args}")
        try:
            if len(args) == 0:
                code = str(LogicLinkkf.current_data["code"])
            else:
                code = str(args[0])

            logger.debug(f"add_whitelist code: {code}")

            whitelist_program = P.ModelSetting.get("linkkf_auto_code_list")
            # whitelist_programs = [
            #     str(x.strip().replace(" ", ""))
            #     for x in whitelist_program.replace("\n", "|").split("|")
            # ]
            whitelist_programs = [
                str(x.strip()) for x in whitelist_program.replace("\n", "|").split("|")
            ]

            if code not in whitelist_programs:
                whitelist_programs.append(code)
                whitelist_programs = filter(
                    lambda x: x != "", whitelist_programs
                )  # remove blank code
                whitelist_program = "|".join(whitelist_programs)
                entity = (
                    db.session.query(P.ModelSetting)
                    .filter_by(key="linkkf_auto_code_list")
                    .with_for_update()
                    .first()
                )
                entity.value = whitelist_program
                db.session.commit()
                ret["ret"] = True
                ret["code"] = code
                if len(args) == 0:
                    return LogicLinkkf.current_data
                else:
                    return ret
            else:
                ret["ret"] = False
                ret["log"] = "이미 추가되어 있습니다."
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            ret["ret"] = False
            ret["log"] = str(e)
        return ret

    def setting_save_after(self, change_list=None):
        if self.queue.get_max_ffmpeg_count() != P.ModelSetting.get_int(
            "linkkf_max_ffmpeg_process_count"
        ):
            self.queue.set_max_ffmpeg_count(
                P.ModelSetting.get_int("linkkf_max_ffmpeg_process_count")
            )

    @staticmethod
    def _cleanup_view_stream_cache(now_ts=None):
        now_ts = now_ts or time.time()
        expired_keys = [
            key
            for key, value in LogicLinkkf._view_stream_cache.items()
            if (now_ts - value.get("ts", 0)) > LogicLinkkf._view_stream_cache_ttl
        ]
        for key in expired_keys:
            LogicLinkkf._view_stream_cache.pop(key, None)

    @staticmethod
    def _get_cached_view_stream(playid_url):
        if not playid_url:
            return None
        now_ts = time.time()
        LogicLinkkf._cleanup_view_stream_cache(now_ts)
        item = LogicLinkkf._view_stream_cache.get(playid_url)
        if not item:
            return None
        if (now_ts - item.get("ts", 0)) > LogicLinkkf._view_stream_cache_ttl:
            LogicLinkkf._view_stream_cache.pop(playid_url, None)
            return None
        return item.get("value")

    @staticmethod
    def _set_cached_view_stream(playid_url, video_url, referer_url, vtt_url):
        if not playid_url or not video_url:
            return
        LogicLinkkf._view_stream_cache[playid_url] = {
            "ts": time.time(),
            "value": (video_url, referer_url, vtt_url),
        }
        LogicLinkkf._cleanup_view_stream_cache()

    @staticmethod
    def _fetch_html_for_view(url, referer=None, timeout=8):
        if not url:
            return ""
        headers = {
            "User-Agent": LogicLinkkf.headers.get("User-Agent")
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Referer": referer or LogicLinkkf.referer or P.ModelSetting.get("linkkf_url") or "https://linkkf.live/",
        }
        res = LogicLinkkf._view_session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        res.raise_for_status()
        return res.text or ""

    @staticmethod
    def _extract_stream_config_from_iframe_html(iframe_content, iframe_src):
        if not iframe_content:
            return None, None

        video_url = None
        vtt_url = None

        m3u8_pattern = re.compile(r"url:\s*['\"]([^'\"]*\.m3u8[^'\"]*)['\"]")
        m3u8_match = m3u8_pattern.search(iframe_content)

        if not m3u8_match:
            source_pattern = re.compile(r"<source[^>]+src=['\"]([^'\"]*\.m3u8[^'\"]*)['\"]", re.IGNORECASE)
            m3u8_match = source_pattern.search(iframe_content)

        if not m3u8_match:
            src_pattern = re.compile(r"src\s*=\s*['\"]([^'\"]*\.m3u8[^'\"]*)['\"]", re.IGNORECASE)
            m3u8_match = src_pattern.search(iframe_content)

        if not m3u8_match:
            art_pattern = re.compile(r"url\s*:\s*['\"]([^'\"]+)['\"]")
            for matched in art_pattern.findall(iframe_content):
                if ".m3u8" in matched:
                    video_url = matched
                    break

        if not m3u8_match and not video_url:
            video_url_pattern = re.compile(r"videoUrl\s*:\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
            video_url_match = video_url_pattern.search(iframe_content)
            if video_url_match:
                video_url = video_url_match.group(1)

        if m3u8_match and not video_url:
            video_url = m3u8_match.group(1)

        if video_url:
            video_url = video_url.replace("\\/", "/")
            if video_url.startswith("cache/") or video_url.startswith("/cache/") or video_url.startswith("/r2/"):
                from urllib.parse import urljoin
                video_url = urljoin(iframe_src, video_url)

        vtt_pattern = re.compile(r"['\"]src['\"]?:\s*['\"]([^'\"]*\.vtt)['\"]", re.IGNORECASE)
        vtt_match = vtt_pattern.search(iframe_content)
        if not vtt_match:
            vtt_pattern = re.compile(r"url:\s*['\"]([^'\"]*\.vtt[^'\"]*)['\"]", re.IGNORECASE)
            vtt_match = vtt_pattern.search(iframe_content)
        if not vtt_match:
            vtt_pattern = re.compile(r"['\"]file['\"]\s*:\s*['\"]([^'\"]*\.vtt[^'\"]*)['\"]", re.IGNORECASE)
            vtt_match = vtt_pattern.search(iframe_content)
        if vtt_match:
            vtt_url = vtt_match.group(1).replace("\\/", "/")
            if vtt_url.startswith("s/") or vtt_url.startswith("/s/") or vtt_url.startswith("/r2/"):
                from urllib.parse import urljoin
                vtt_url = urljoin(iframe_src, vtt_url)

        return video_url, vtt_url

    @staticmethod
    def extract_video_url_from_playid(playid_url, light_mode=False):
        """
        linkkf.live의 playid URL에서 실제 비디오 URL(m3u8)과 자막 URL(vtt)을 추출합니다.
        
        예시:
        - playid_url: https://linkkf.live/playid/403116/?server=12&slug=11
        - iframe: https://play.sub3.top/r2/play.php?id=n8&url=403116s11
        - m3u8: https://n8.hlz3.top/403116s11/index.m3u8
        
        Returns:
            (video_url, referer_url, vtt_url)
        """
        video_url = None
        referer_url = None
        vtt_url = None
        playid_url = (playid_url or "").strip()
        if not playid_url:
            return None, None, None

        # 0) cache
        cached_value = LogicLinkkf._get_cached_view_stream(playid_url)
        if cached_value:
            return cached_value

        # 1) fast path (보기 버튼용)
        try:
            html_content = LogicLinkkf._fetch_html_for_view(playid_url, timeout=8)
            if html_content:
                soup = BeautifulSoup(html_content, "html.parser")
                iframe = soup.select_one("iframe#video-player-iframe")
                if not iframe:
                    iframe = soup.select_one("iframe[src*='play.sub'], iframe[src*='playv2'], iframe[src*='play.php']")
                if not iframe:
                    for found_iframe in soup.select("iframe[src]"):
                        src = (found_iframe.get("src") or "").strip()
                        if not src:
                            continue
                        if any(blocked in src for blocked in ["googlead", "googletag", "adsystem", "cloud.google"]):
                            continue
                        iframe = found_iframe
                        break

                if iframe and iframe.get("src"):
                    import html as html_lib
                    iframe_src = html_lib.unescape(iframe.get("src"))
                    if iframe_src.startswith("/"):
                        iframe_src = urllib.parse.urljoin(playid_url, iframe_src)
                    referer_url = iframe_src
                    iframe_content = LogicLinkkf._fetch_html_for_view(
                        iframe_src,
                        referer=playid_url,
                        timeout=8,
                    )
                    video_url, vtt_url = LogicLinkkf._extract_stream_config_from_iframe_html(iframe_content, iframe_src)
                    if video_url:
                        LogicLinkkf._set_cached_view_stream(playid_url, video_url, referer_url, vtt_url)
                        return video_url, referer_url, vtt_url
        except Exception as fast_e:
            logger.debug(f"[Linkkf][FastView] extraction failed: {fast_e}")

        if light_mode:
            # 보기 버튼 경로는 속도 우선: 무거운 fallback 생략
            return None, None, None
        
        try:
            logger.info(f"Extracting video URL from: {playid_url}")
            
            # Step 1: playid 페이지에서 iframe src 추출 (cloudscraper 사용)
            html_content = LogicLinkkf.get_html(playid_url, timeout=15)
            if not html_content:
                logger.error(f"Failed to fetch playid page (Timeout or Error): {playid_url}")
                return None, None, None
                
            soup = BeautifulSoup(html_content, "html.parser")
            
            # iframe 찾기 (광고 iframe 제외를 위해 id나 src 패턴 강조)
            iframe = soup.select_one("iframe#video-player-iframe")
            if not iframe:
                iframe = soup.select_one("iframe[src*='play.sub']")
            if not iframe:
                iframe = soup.select_one("iframe[src*='play.php']")
            
            # fallback if strictly needed but skip ad domains
            if not iframe:
                all_iframes = soup.select("iframe")
                for f in all_iframes:
                    src = f.get("src", "")
                    if any(x in src for x in ["googletag", "googlead", "adsystem", "cloud.google"]): 
                        continue
                    if src.startswith("http"):
                        iframe = f
                        break
            
            if iframe and iframe.get("src"):
                iframe_src = iframe.get("src")
                # HTML entity decoding (&#038; -> &, &amp; -> &, etc.)
                import html as html_lib
                iframe_src = html_lib.unescape(iframe_src)
                
                logger.info(f"Found player iframe: {iframe_src}")
                
                # Step 2: iframe 페이지에서 m3u8 URL과 vtt URL 추출
                iframe_content = LogicLinkkf.get_html(iframe_src, timeout=15)
                if not iframe_content:
                    logger.error(f"Failed to fetch iframe content (Timeout or Error): {iframe_src}")
                    return None, iframe_src, None
                
                video_url, vtt_url = LogicLinkkf._extract_stream_config_from_iframe_html(iframe_content, iframe_src)

                if video_url:
                    logger.info(f"Extracted m3u8 URL: {video_url}")
                else:
                    logger.warning(f"m3u8 URL not found in iframe for: {playid_url}")
                    # HTML 내용이 너무 길면 앞부분만 로깅
                    snippet = iframe_content.replace('\n', ' ')
                    logger.debug(f"Iframe Content snippet (500 chars): {snippet[:500]}...")
                    # 'cache/' 가 들어있는지 확인
                    if 'cache/' in iframe_content:
                        logger.debug("Found 'cache/' keyword in iframe content but regex failed. Inspection required.")

                if vtt_url:
                    logger.info(f"Extracted VTT URL: {vtt_url}")
                
                referer_url = iframe_src
            else:
                logger.warning(f"No player iframe found in playid page. HTML snippet: {html_content[:200]}...")
                
        except Exception as e:
            logger.error(f"Error in extract_video_url_from_playid: {e}")
            logger.error(traceback.format_exc())
        
        if video_url:
            LogicLinkkf._set_cached_view_stream(playid_url, video_url, referer_url, vtt_url)
        return video_url, referer_url, vtt_url

    def get_video_url_from_url(url, url2):
        video_url = None
        referer_url = None
        vtt_url = None
        LogicLinkkf.referer = url2
        # logger.info("dx download url : %s , url2 : %s" % (url, url2))
        # logger.debug(LogicLinkkfYommi.referer)

        try:
            if "ani1" in url2:
                # kfani 계열 처리 => 방문해서 m3u8을 받아온다.
                logger.debug("ani1 routine=========================")
                LogicLinkkf.referer = "https://linkkf.app"
                # logger.debug(f"url2: {url2}")
                ani1_html = LogicLinkkf.get_html(url2)

                tree = html.fromstring(ani1_html)
                option_url = tree.xpath("//select[@id='server-list']/option[1]/@value")

                # logger.debug(f"option_url:: {option_url}")

                data = LogicLinkkf.get_html(option_url[0])
                # print(type(data))
                regex2 = r'"([^\"]*m3u8)"|<source[^>]+src=\"([^"]+)'

                temp_url = re.findall(regex2, data)[0]
                video_url = ""
                ref = "https://ani1.app"
                for i in temp_url:
                    if i is None:
                        continue
                    video_url = i
                    # video_url = '{1} -headers \'Referer: "{0}"\' -user_agent "Mozilla/5.0 (Windows NT 10.0; Win64;
                    # x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3554.0 Safari/537.36"'.format(ref,
                    # video_url)

                data_tree = html.fromstring(data)
                # print(data_tree.xpath("//video/source/@src"))
                vtt_elem = data_tree.xpath("//track/@src")[0]
                # vtt_elem = data_tree.xpath("//*[contains(@src, '.vtt']")[0]

                # print(vtt_elem)

                match = re.compile(
                    r"<track.+src=\"(?P<vtt_url>.*?.vtt)\"", re.MULTILINE
                ).search(data)

                vtt_url = match.group("vtt_url")

                referer_url = "https://kfani.me/"

            elif "kfani" in url2:
                # kfani 계열 처리 => 방문해서 m3u8을 받아온다.
                logger.debug("kfani routine=================================")
                LogicLinkkf.referer = url2
                # logger.debug(f"url2: {url2}")
                data = LogicLinkkf.get_html(url2)
                # logger.info("dx: data", data)
                regex2 = r'"([^\"]*m3u8)"|<source[^>]+src=\"([^"]+)'

                temp_url = re.findall(regex2, data)[0]
                video_url = ""
                ref = "https://kfani.me"
                for i in temp_url:
                    if i is None:
                        continue
                    video_url = i
                    # video_url = '{1} -headers \'Referer: "{0}"\' -user_agent "Mozilla/5.0 (Windows NT 10.0; Win64;
                    # x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3554.0 Safari/537.36"'.format(ref,
                    # video_url)

                # @k45734
                vtt_url = None
                try:
                    _match1 = re.compile(
                        r"<track.+src=\"(?P<vtt_url>.*?.vtt)", re.MULTILINE
                    ).search(data)
                    vtt_url = _match1.group("vtt_url")
                except:
                    _match2 = re.compile(
                        r"url: \'(?P<vtt_url>.*?.vtt)", re.MULTILINE
                    ).search(data)
                    vtt_url = _match2.group("vtt_url")

                logger.info("vtt_url: %s", vtt_url)

                referer_url = url2

            elif "kftv" in url2:
                # kftv 계열 처리 => url의 id로 https://yt.kftv.live/getLinkStreamMd5/df6960891d226e24b117b850b44a2290 페이지
                # 접속해서 json 받아오고, json에서 url을 추출해야함
                if "=" in url2:
                    md5 = urlparse.urlparse(url2).query.split("=")[1]
                elif "embedplay" in url2:
                    md5 = url2.split("/")[-1]
                url3 = "https://yt.kftv.live/getLinkStreamMd5/" + md5
                # logger.info("download url : %s , url3 : %s" % (url, url3))
                data3 = LogicLinkkf.get_html(url3)
                data3dict = json.loads(data3)
                # print(data3dict)
                video_url = data3dict[0]["file"]

            elif "k40chan" in url2:
                # k40chan 계열 처리 => 방문해서 m3u8을 받아온다.
                # k45734 님 소스 반영 (확인은 안해봄 잘 동작할꺼라고 믿고,)
                logger.debug("k40chan routine=================================")
                LogicLinkkf.referer = url2
                data = LogicLinkkf.get_html(url2)

                regex2 = r'"([^\"]*m3u8)"|<source[^>]+src=\"([^"]+)'

                temp_url = re.findall(regex2, data)[0]
                video_url = ""
                # ref = "https://kfani.me"
                for i in temp_url:
                    if i is None:
                        continue
                    video_url = i

                match = re.compile(r"<track.+src\=\"(?P<vtt_url>.*?.vtt)").search(data)
                vtt_url = match.group("vtt_url")

                referer_url = url2

            elif "linkkf" in url2:
                logger.debug("linkkf routine")
                # linkkf 계열 처리 => URL 리스트를 받아오고, 하나 골라 방문 해서 m3u8을 받아온다.
                referer_url = url2
                data2 = LogicLinkkf.get_html(url2)
                # print(data2)
                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                # logger.info("cat: %s", cat)
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("url3: %s", url3)
                # logger.info("download url : %s , url3 : %s" % (url, url3))
                if "kftv" in url3:
                    return LogicLinkkf.get_video_url_from_url(url2, url3)
                elif url3.startswith("/"):
                    url3 = urlparse.urljoin(url2, url3)
                    logger.debug(f"url3 = {url3}")
                    LogicLinkkf.referer = url2
                    data3 = LogicLinkkf.get_html(url3)
                    # logger.info('data3: %s', data3)
                    # regex2 = r'"([^\"]*m3u8)"'
                    regex2 = r'"([^\"]*mp4|m3u8)"'
                    video_url = re.findall(regex2, data3)[0]
                    # logger.info('video_url: %s', video_url)
                    referer_url = url3

                else:
                    logger.error("새로운 유형의 url 발생! %s %s %s" % (url, url2, url3))
            elif "kakao" in url2:
                # kakao 계열 처리, 외부 API 이용
                payload = {"inputUrl": url2}
                kakao_url = (
                    "http://webtool.cusis.net/wp-pages/download-kakaotv-video/video.php"
                )
                data2 = requests.post(
                    kakao_url,
                    json=payload,
                    headers={
                        "referer": "http://webtool.cusis.net/download-kakaotv-video/"
                    },
                ).content
                time.sleep(
                    3
                )  # 서버 부하 방지를 위해 단시간에 너무 많은 URL전송을 하면 IP를 차단합니다.
                url3 = json.loads(data2)
                # logger.info("download url2 : %s , url3 : %s" % (url2, url3))
                video_url = url3
            elif "#V" in url2:  # V 패턴 추가
                logger.debug("#v routine")

                data2 = LogicLinkkf.get_html(url2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))
                if "kftv" in url3:
                    return LogicLinkkf.get_video_url_from_url(url2, url3)
                elif url3.startswith("/"):
                    url3 = urlparse.urljoin(url2, url3)
                    LogicLinkkf.referer = url2
                    data3 = LogicLinkkf.get_html(url3)

                    regex2 = r'"([^\"]*mp4)"'
                    video_url = re.findall(regex2, data3)[0]
                else:
                    logger.error("새로운 유형의 url 발생! %s %s %s" % (url, url2, url3))

            elif "#M2" in url2:
                LogicLinkkf.referer = url2
                data2 = LogicLinkkf.get_html(url2)
                # print(data2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))
                if "kftv" in url3:
                    return LogicLinkkf.get_video_url_from_url(url2, url3)
                elif url3.startswith("/"):
                    url3 = urlparse.urljoin(url2, url3)
                    LogicLinkkf.referer = url2
                    data3 = LogicLinkkf.get_html(url3)
                    # print("내용: %s", data3)
                    # logger.info("movie content: %s", data3)
                    # regex2 = r'"([^\"]*m3u8)"'
                    regex2 = r'"([^\"]*mp4)"'
                    video_url = re.findall(regex2, data3)[0]
                else:
                    logger.error("새로운 유형의 url 발생! %s %s %s" % (url, url2, url3))
            elif "😀#i" in url2:
                LogicLinkkf.referer = url2
                data2 = LogicLinkkf.get_html(url2)
                # logger.info(data2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))

            elif "#k" in url2:
                data2 = LogicLinkkf.get_html(url2)
                # logger.info(data2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))

            elif "#k2" in url2:
                data2 = LogicLinkkf.get_html(url2)
                # logger.info(data2)

                regex = r"cat1 = [^\[]*([^\]]*)"
                cat = re.findall(regex, data2)[0]
                regex = r"\"([^\"]*)\""
                url3s = re.findall(regex, cat)
                url3 = random.choice(url3s)
                # logger.info("download url : %s , url3 : %s" % (url, url3))
            elif "mopipi" in url2:
                LogicLinkkf.referer = url
                data2 = LogicLinkkf.get_html(url2)
                # logger.info(data2)
                match = re.compile(r"src\=\"(?P<video_url>http.*?\.mp4)").search(data2)
                video_url = match.group("video_url")

                match = re.compile(r"src\=\"(?P<vtt_url>http.*?.vtt)").search(data2)
                logger.info("match group: %s", match.group("video_url"))
                vtt_url = match.group("vtt_url")

                # logger.info("download url : %s , url3 : %s" % (url, url3))

            else:
                logger.error("새로운 유형의 url 발생! %s %s" % (url, url2))
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

        return [video_url, referer_url, vtt_url]

    @staticmethod
    def get_html_episode_content(url: str) -> str:
        if url.startswith("http"):
            html_data = LogicLinkkf.get_html(url)
        else:
            url = f"https://linkkf.app{url}"

            logger.info("get_video_url(): url: %s" % url)
            data = LogicLinkkf.get_html(url)

            tree = html.fromstring(data)

            tree = html.fromstring(data)

            pattern = re.compile("var player_data=(.*)")

            js_scripts = tree.xpath("//script")

            iframe_info = None
            index = 0

            for js_script in js_scripts:
                # print(f"{index}.. {js_script.text_content()}")
                if pattern.match(js_script.text_content()):
                    # logger.debug("match::::")
                    match_data = pattern.match(js_script.text_content())
                    iframe_info = json.loads(
                        match_data.groups()[0].replace("path:", '"path":')
                    )
                    # logger.debug(f"iframe_info:: {iframe_info}")

                index += 1

            ##################################################
            # iframe url:: https://s2.ani1c12.top/player/index.php?data='+player_data.url+'
            ####################################################

            url = f"https://s2.ani1c12.top/player/index.php?data={iframe_info['url']}"
            html_data = LogicLinkkf.get_html(url)

        return html_data

    def get_anime_info(self, cate, page, top_type="month"):
        try:
            items_xpath = '//div[@class="ext-json-item"]'
            title_xpath = ""

            if cate == "ing":
                # url = f"{P.ModelSetting.get('linkkf_url')}/airing/page/{page}"
                # User requested to use 'anime-list' ID (categorytagid=2) for 'ing'
                url = "https://linkkf.5imgdarr.top/api/singlefilter.php?categorytagid=2&page={}&limit=20".format(page)
                items_xpath = None # JSON fetching
                title_xpath = None
            elif cate == "movie":
                # API Spec: season type movie
                url = "https://linkkf.5imgdarr.top/api/singlefilter.php?postseasontypetagid=5061&page={}&limit=20".format(page)
                items_xpath = None
                title_xpath = None

            elif cate == "complete":
                # User requested to comment out for now (25-12-31)
                # url = "https://linkkf.5imgdarr.top/api/singlefilter.php?categorytagid=2&page={}&limit=20".format(page)
                url = "" # Disable
                items_xpath = None
                title_xpath = None
            elif cate == "top_view":
                # API Spec: type=day|week|month|all
                normalized_top_type = top_type if top_type in ["day", "week", "month", "all"] else "month"
                url = "https://linkkf.5imgdarr.top/api/apiview.php?type={}&limit=100".format(normalized_top_type)
                items_xpath = None # JSON fetching
                title_xpath = None
            elif cate == "adult":
                # 16+ 카테고리
                # 원본 사이트 16+ 필터 파라미터
                url = "https://linkkf.5imgdarr.top/api/singlefilter.php?postseasontypetagid=5085&page={}&limit=20".format(page)
                items_xpath = None
                title_xpath = None
            else:
                # Default: ing 목록
                url = "https://linkkf.5imgdarr.top/api/singlefilter.php?categorytagid=2&page={}&limit=20".format(page)
                items_xpath = None  # JSON fetching
                title_xpath = None

            logger.info("url:::> %s", url)
            
            if self.referer is None:
                self.referer = "https://linkkf.live"

            data = {"ret": "success", "page": page}
            if cate == "top_view":
                data["top_type"] = top_type if top_type in ["day", "week", "month", "all"] else "month"
            response_data = LogicLinkkf.get_html(url, timeout=10)
            
            # JSON 응답 처리 (Top View 포함)
            # Zendriver returns HTML-wrapped JSON: <html>...<pre>JSON</pre>...</html>
            json_text = response_data
            if response_data.strip().startswith('<html') or response_data.strip().startswith('<!'):
                try:
                    tree_temp = html.fromstring(response_data)
                    pre_content = tree_temp.xpath('//pre/text()')
                    if pre_content:
                        json_text = pre_content[0]
                except Exception:
                    pass
            
            try:
                json_data = json.loads(json_text)
                # P.logger.debug(json_data)
                
                # top_view 처리는 별도 로직 (구조가 다름)
                if cate == "top_view":
                    if isinstance(json_data, dict):
                        items = json_data.get("data", []) if isinstance(json_data.get("data", []), list) else []
                        top_type_value = json_data.get("type", data.get("top_type", top_type))
                    elif isinstance(json_data, list):
                        items = json_data
                        top_type_value = data.get("top_type", top_type)
                    else:
                        items = []
                        top_type_value = data.get("top_type", top_type)

                    normalized_items = []

                    for index, item in enumerate(items, start=1):
                        note_text = ""
                        if top_type_value == "day":
                            note_text = f"일간 {item.get('day_views', 0):,}"
                        elif top_type_value == "week":
                            note_text = f"주간 {item.get('week_views', 0):,}"
                        elif top_type_value == "month":
                            note_text = f"월간 {item.get('month_views', 0):,}"
                        elif top_type_value == "all":
                            note_text = f"누적 {item.get('total_views', 0):,}"

                        normalized_items.append({
                            "postid": str(item.get("postid", "")),
                            "postname": item.get("postname", ""),
                            "postthum": item.get("postthum", ""),
                            "postnote": note_text or item.get("postnote") or f"TOP {index}",
                            "rank": index,
                        })
                    return self._build_listing_payload(
                        normalized_items,
                        page=page,
                        total_page=1,
                        extra={"top_type": top_type_value, "type": top_type_value},
                    )
                
                # 기존 JSON 처리 (ing 등)
                if isinstance(json_data, dict):
                    if "data" in json_data and isinstance(json_data["data"], list):
                        total_page = json_data.get("pagination", {}).get("total_pages", json_data.get("total_page", 1)) if isinstance(json_data.get("pagination"), dict) else json_data.get("total_page", 1)
                        return self._build_listing_payload(
                            json_data["data"],
                            page=page,
                            total_page=total_page,
                            extra={k: v for k, v in json_data.items() if k not in ["data", "episode", "episode_count", "count", "ret", "page", "total_page"]},
                        )
                    return json_data
                else:
                    normalized_items = json_data if isinstance(json_data, list) else []
                    return self._build_listing_payload(normalized_items, page=page, total_page=1)
            except (json.JSONDecodeError, ValueError):
                pass

            # JSON API인 경우 items_xpath가 None이므로, 이 경우 HTML 파싱 스킵
            if items_xpath is None:
                P.logger.error("JSON parsing failed but items_xpath is None - invalid API response")
                return {"ret": "error", "log": "Invalid API response (expected JSON)"}

            tree = html.fromstring(response_data)
            tmp_items = tree.xpath(items_xpath)

            if tree.xpath('//div[@id="wp_page"]//text()'):
                data["total_page"] = tree.xpath('//div[@id="wp_page"]//text()')[-1]
            else:
                data["total_page"] = 0
            normalized_items = []

            for item in tmp_items:
                entity = dict()
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["postid"] = re.search(r"[0-9]+", entity["link"]).group()
                entity["postname"] = item.xpath(title_xpath)[0].strip()
                entity["postthum"] = item.xpath("./a/@data-original")[0]
                entity["postnote"] = (
                    item.xpath("./a/span//text()")[0].strip()
                    if len(item.xpath("./a/span//text()")) > 0
                    else ""
                )
                normalized_items.append(entity)

            # logger.debug(data)

            return self._build_listing_payload(normalized_items, page=page, total_page=data["total_page"])
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    def get_search_result(self, query, page, cate):
        try:
            # API URL: https://linkkf.5imgdarr.top/api/search.php
            api_url = "https://linkkf.5imgdarr.top/api/search.php"
            params = {
                "keyword": query,
                "page": page,
                "limit": 20
            }
            logger.info(f"get_search_result API: {api_url}, params: {params}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                "Referer": "https://linkkf.live/"
            }
            
            response = requests.get(api_url, params=params, headers=headers, timeout=10)
            result_json = response.json()
            
            data = {"ret": "success", "page": page, "episode": []}
            
            if result_json.get("status") == "success":
                items = result_json.get("data", [])
                pagination = result_json.get("pagination", {})
                
                data["total_page"] = pagination.get("total_pages", 0)
                data["episode_count"] = pagination.get("total_results", 0)
                
                normalized_items = []
                for item in items:
                    entity = {}
                    entity["postid"] = str(item.get("postid"))
                    entity["postname"] = item.get("name")
                    
                    thumb = item.get("thumb")
                    if thumb:
                         if thumb.startswith("http"):
                             entity["postthum"] = thumb
                         else:
                             entity["postthum"] = f"https://rez1.ims1.top/350x/{thumb}"
                    else:
                        entity["postthum"] = ""
                        
                    entity["postnote"] = item.get("postnoti") or item.get("seasontype") or ""
                    normalized_items.append(entity)
                return self._build_listing_payload(
                    normalized_items,
                    page=page,
                    total_page=pagination.get("total_pages", 0),
                )
            else:
                 data["total_page"] = 0
                 data["episode_count"] = 0

            return data
        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}

    def get_series_info(self, code):
        data = {"code": code, "ret": False}
        try:
            # 이전 데이터가 있다면, 리턴 (# If you have previous data, return)
            if (
                LogicLinkkf.current_data is not None
                and LogicLinkkf.current_data["code"] == code
                and LogicLinkkf.current_data["ret"]
            ):
                # 포스터/에피소드가 정상 포함된 캐시만 재사용
                if LogicLinkkf.current_data.get("poster_url"):
                    return LogicLinkkf.current_data
                logger.info("Cached current_data has no poster_url; refreshing from source.")
            
            url = "%s/%s/" % (P.ModelSetting.get("linkkf_url"), code)
            
            logger.info(f"get_series_info URL: {url}")

            html_content = LogicLinkkf.get_html(url, cached=False)
            
            if not html_content:
                data["log"] = "Failed to fetch page content"
                data["ret"] = "error"
                return data

            soup = BeautifulSoup(html_content, "html.parser")
            
            # === 제목 추출 ===
            # 방법 1: #anime-details > h3 (가장 정확)
            title_elem = soup.select_one("#anime-details > h3")
            if not title_elem:
                # 방법 2: .anime-tab-content > h3
                title_elem = soup.select_one(".anime-tab-content > h3")
            
            title_text = ""
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                # "11/12 - 너와 넘어 사랑이 된다" 형식에서 제목만 추출
                if " - " in title_text:
                    data["title"] = title_text.split(" - ", 1)[1]
                else:
                    data["title"] = title_text
            else:
                # 방법 3: gemini-dark-card__link의 title 속성
                card_link = soup.select_one("a.gemini-dark-card__link")
                if card_link and card_link.get("title"):
                    data["title"] = card_link.get("title")
                else:
                    # 방법 4: 포스터 이미지의 alt 속성
                    poster_img = soup.select_one(
                        "img.gemini-dark-card__image, img.animeimglink-dark-card__image"
                    )
                    if poster_img and poster_img.get("alt"):
                        data["title"] = poster_img.get("alt")
                    else:
                        # 방법 5: 페이지 title에서 추출
                        page_title = soup.select_one("title")
                        if page_title:
                            title_text = page_title.get_text(strip=True)
                            # "제목 자막 / 더빙 / Linkkf" 형식 처리
                            data["title"] = title_text.split(" 자막")[0].split(" /")[0].strip()
                        else:
                            data["title"] = f"Unknown-{code}"
            
            # 제목 정리
            data["title"] = Util.change_text_for_use_filename(data["title"]).strip()
            data["_id"] = str(code)
            
            # === 시즌 추출 ===
            match = re.compile(r"(?P<season>\d+)기").search(data.get("title", ""))
            if match:
                data["season"] = match.group("season")
                data["title"] = data["title"].replace(data["season"] + "기", "").strip()
            else:
                data["season"] = "1"
            
            # === 포스터 이미지 ===
            poster_elem = soup.select_one(
                "img.gemini-dark-card__image, img.animeimglink-dark-card__image"
            )
            if poster_elem:
                # lazy loading 대응: data-lazy-src (사이트에서 사용하는 속성), data-src, src 순서로 확인
                data["poster_url"] = (
                    poster_elem.get("data-lazy-src") or 
                    poster_elem.get("data-src") or 
                    poster_elem.get("src") or ""
                )
                # placeholder SVG 제외
                if data["poster_url"].startswith("data:image/svg"):
                    data["poster_url"] = poster_elem.get("data-lazy-src") or poster_elem.get("data-src") or ""
            else:
                # 대안 선택자
                poster_alt = soup.select_one(
                    "a.gemini-dark-card__link img, .animeimglink-dark-card img, .animeimglink-ratio-16-9 img"
                )
                if poster_alt:
                    data["poster_url"] = (
                        poster_alt.get("data-lazy-src") or 
                        poster_alt.get("data-src") or 
                        poster_alt.get("src") or ""
                    )
                else:
                    # 최종 fallback: og:image/twitter:image 메타
                    og_image = soup.select_one("meta[property='og:image']")
                    tw_image = soup.select_one("meta[name='twitter:image']")
                    data["poster_url"] = (og_image.get("content") if og_image else None) or (
                        tw_image.get("content") if tw_image else None
                    )

            if data.get("poster_url"):
                data["poster_url"] = data["poster_url"].replace("\\/", "/").strip()
            
            # === 상세 정보 ===
            data["detail"] = []
            info_items = soup.select("li")
            for item in info_items:
                text = item.get_text(strip=True)
                if any(keyword in text for keyword in ["방영일", "제작사", "장르", "분류", "년"]):
                    data["detail"].append({"info": text})
            
            if not data["detail"]:
                data["detail"] = [{"정보없음": ""}]
            
            # === 에피소드 목록 - API에서 가져오기 ===
            data["episode"] = []
            data["save_folder"] = data["title"]
            
            # 에피소드 API 호출
            episode_api_url = f"https://linkkfep.5imgdarr.top/api2.php?epid={code}"
            try:
                episode_response = requests.get(episode_api_url, timeout=10)
                episode_data = episode_response.json()
                
                logger.debug(f"Episode API response: {len(episode_data)} servers found")
                
                # 첫 번째 서버 (보통 자막-S)의 에피소드 목록 사용
                if episode_data and len(episode_data) > 0:
                    server_data = episode_data[0].get("server_data", [])
                    # 역순 정렬 (최신 에피소드가 위로)
                    server_data = list(reversed(server_data))
                    
                    for idx, ep_info in enumerate(server_data):
                        ep_name = ep_info.get("name", str(idx + 1))
                        ep_slug = ep_info.get("slug", str(idx + 1))
                        ep_link = ep_info.get("link", "")
                        
                        # 화면 표시용 title은 "01화" 형태
                        ep_title = f"{ep_name}화"
                        
                        # 에피소드별 고유 ID 생성 (프로그램코드 + 에피소드번호)
                        episode_unique_id = data["code"] + ep_name.zfill(4)
                        
                        entity = {
                            "_id": episode_unique_id,  # 에피소드별 고유 ID
                            "program_code": data["code"],
                            "program_title": data["title"],
                            "save_folder": Util.change_text_for_use_filename(data["save_folder"]),
                            "title": ep_title,
                            "ep_num": ep_name,
                            "season": data["season"],
                        }
                        
                        # 에피소드 코드 = _id와 동일
                        entity["code"] = episode_unique_id
                        
                        # URL 생성: playid/{code}/?server=12&slug={slug} 형태
                        entity["url"] = f"https://linkkf.live/playid/{code}/?server=12&slug={ep_slug}"
                        
                        # 저장 경로 설정
                        tmp_save_path = P.ModelSetting.get("linkkf_download_path")
                        if not tmp_save_path:
                            tmp_save_path = "/tmp/anime_downloads"
                            
                        if P.ModelSetting.get("linkkf_auto_make_folder") == "True":
                            program_path = os.path.join(tmp_save_path, entity["save_folder"])
                            entity["save_path"] = os.path.normpath(program_path)
                            if P.ModelSetting.get("linkkf_auto_make_season_folder"):
                                entity["save_path"] = os.path.normpath(os.path.join(
                                    entity["save_path"], "Season %s" % int(entity["season"])
                                ))
                        else:
                            # 기본 경로 설정
                            entity["save_path"] = os.path.normpath(tmp_save_path)
                        
                        entity["image"] = data["poster_url"]
                        # filename 생성 시 숫자만 전달 ("01화" 아님)
                        entity["filename"] = LogicLinkkf.get_filename(
                            data["save_folder"], data["season"], ep_name
                        )

                        # Check for existing file (for Play button)
                        entity["filepath"] = os.path.normpath(os.path.join(entity["save_path"], entity["filename"]))
                        if os.path.exists(entity["filepath"]):
                            entity["exist_video"] = True
                            if "first_exist_filepath" not in data:
                                data["first_exist_filepath"] = entity["filepath"]
                                data["first_exist_filename"] = entity["filename"]
                        else:
                            entity["exist_video"] = False
                        
                        data["episode"].append(entity)
                        
            except Exception as ep_error:
                logger.error(f"Episode API error: {ep_error}")
                logger.error(traceback.format_exc())
            
            data["episode_count"] = str(len(data["episode"]))
            data["ret"] = True
            self.current_data = data
            
            logger.info(f"Parsed series: {data['title']}, Episodes: {data['episode_count']}")
            return data

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            data["log"] = str(e)
            data["ret"] = "error"
            return data

    def get_screen_movie_info(self, page):
        try:
            url = f"{P.ModelSetting.get('linkkf_url')}/ani/page/{page}"

            html_content = self.get_html_requests(url, cached=True)
            # html_content = LogicLinkkfYommi.get_html_cloudflare(url, cached=False)
            download_path = P.ModelSetting.get("linkkf_download_path")
            tree = html.fromstring(html_content)
            tmp_items = tree.xpath('//div[@class="myui-vodlist__box"]')
            title_xpath = './/a[@class="text-fff"]//text()'
            # logger.info('tmp_items:::', tmp_items)
            data = dict()
            data = {"ret": "success", "page": page}

            normalized_items = []

            for item in tmp_items:
                entity = dict()
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["postid"] = re.search(r"[0-9]+", entity["link"]).group()
                entity["postname"] = item.xpath(title_xpath)[0].strip()
                if len(item.xpath("./a/@style")) > 0:
                    print(
                        re.search(
                            r"url\(((http|https|ftp|ftps)\:\/\/[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,3}(\/\S*)?)\)",
                            item.xpath("./a/@style")[0],
                        ).group()
                    )

                if item.xpath(".//a/@data-original"):
                    entity["postthum"] = item.xpath(".//a/@data-original")[0]

                else:
                    entity["postthum"] = ""
                # entity["image_link"] = item.xpath("./a/@data-original")[0]
                entity["postnote"] = (
                    item.xpath("./a/span//text()")[0]
                    if len(item.xpath("./a/span//text()")) > 0
                    else ""
                )
                normalized_items.append(entity)

            # json_file_path = os.path.join(download_path, "airing_list.json")
            # logger.debug("json_file_path:: %s", json_file_path)
            #
            # with open(json_file_path, "w") as outfile:
            #     json.dump(data, outfile)

            return self._build_listing_payload(normalized_items, page=page, total_page=1)

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())


    def get_html_requests(self, url, cached=False):
        if LogicLinkkf.session is None:
            if cached:
                logger.debug("cached===========++++++++++++")

                LogicLinkkf.session = CachedSession(
                    os.path.join(self.cache_path, "linkkf_cache"),
                    backend="sqlite",
                    expire_after=300,
                    cache_control=True,
                )
                # print(f"{cache_path}")
                # print(f"cache_path:: {LogicLinkkfYommi.session.cache}")
            else:
                LogicLinkkf.session = requests.Session()

        LogicLinkkf.referer = "https://linkkf.live"

        LogicLinkkf.headers["Referer"] = LogicLinkkf.referer

        # logger.debug(
        #     f"get_html()::LogicLinkkfYommi.referer = {LogicLinkkfYommi.referer}"
        # )
        page = LogicLinkkf.session.get(url, headers=LogicLinkkf.headers)
        # logger.info(f"page: {page}")

        return page.content.decode("utf8", errors="replace")

    @staticmethod
    def get_filename(maintitle, season, title):
        try:
            # logger.debug("get_filename()===")
            # logger.info("title:: %s", title)
            # logger.info("maintitle:: %s", maintitle)
            match = re.compile(
                r"(?P<title>.*?)\s?((?P<season>\d+)기)?\s?((?P<epi_no>\d+)화?)"
            ).search(title)
            if match:
                epi_no = int(match.group("epi_no"))
                if epi_no < 10:
                    epi_no = "0%s" % epi_no
                else:
                    epi_no = "%s" % epi_no

                if int(season) < 10:
                    season = "0%s" % season
                else:
                    season = "%s" % season

                # title_part = match.group('title').strip()
                # ret = '%s.S%sE%s%s.720p-SA.mp4' % (maintitle, season, epi_no, date_str)
                ret = "%s.S%sE%s.720p-LK.mp4" % (maintitle, season, epi_no)
            else:
                logger.debug("NOT MATCH")
                ret = "%s.720p-SA.mp4" % maintitle

            return Util.change_text_for_use_filename(ret)
        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())

    def add(self, episode_info):
        """Add episode to download queue with early skip checks."""
        # 큐가 초기화되지 않았으면 초기화 (클래스 레벨 큐 확인)
        if LogicLinkkf.queue is None:
            logger.warning("Queue is None in add(), initializing...")
            try:
                LogicLinkkf.queue = FfmpegQueue(
                    P, P.ModelSetting.get_int("linkkf_max_ffmpeg_process_count"), "linkkf", caller=self
                )
                LogicLinkkf.queue.queue_start()
            except Exception as e:
                logger.error(f"Failed to initialize queue: {e}")
                return "queue_init_error"
        
        # self.queue를 LogicLinkkf.queue로 바인딩 (프로세스 내부 공유 보장)
        self.queue = LogicLinkkf.queue
        
        # 1. Check if already in queue
        if self.is_exist(episode_info):
            logger.info(f"is_exist returned True for _id: {episode_info.get('_id')}")
            return "queue_exist"
        
        # 2. Check DB for completion status FIRST (before expensive operations)
        db_entity = ModelLinkkfItem.get_by_linkkf_id(episode_info["_id"])
        
        # 3. Early file existence check - filepath is already in episode_info from get_series_info
        filepath = episode_info.get("filepath")
        if filepath:
            filepath = os.path.normpath(filepath)
        
        # 미완성 다운로드 감지 (Frag 파일, .ytdl 파일, .part 파일이 있으면 재다운로드 허용)
        has_incomplete_files = False
        if filepath:
            import glob
            dirname = os.path.normpath(os.path.dirname(filepath))
            has_ytdl = os.path.exists(filepath + ".ytdl")
            has_part = os.path.exists(filepath + ".part")
            has_frag = False
            if dirname and os.path.exists(dirname):
                frag_pattern = os.path.join(dirname, "*Frag*")
                has_frag = len(glob.glob(frag_pattern)) > 0
            has_incomplete_files = has_ytdl or has_part or has_frag
            
            if has_incomplete_files:
                logger.info(f"[Resume] Incomplete download detected, allowing re-download: {filepath}")
                # DB 상태가 completed이면 wait로 변경
                if db_entity is not None and db_entity.status == "completed":
                    db_entity.status = "wait"
                    db_entity.save()
        
        # DB 완료 체크 (미완성 파일이 없는 경우에만)
        if db_entity is not None and db_entity.status == "completed" and not has_incomplete_files:
            logger.info(f"[Skip] Already completed in DB: {episode_info.get('program_title')} {episode_info.get('title')}")
            return "db_completed"
        
        # 파일 존재 체크 (미완성 파일이 없는 경우에만)
        if filepath and os.path.exists(filepath) and not has_incomplete_files:
            logger.info(f"[Skip] File already exists: {filepath}")
            # Update DB status to completed if not already
            if db_entity is not None and db_entity.status != "completed":
                db_entity.status = "completed"
                db_entity.filepath = filepath
                db_entity.save()
            return "file_exists"
        
        # 4. Try GDM if available (like Ohli24/Anilife)
        if ModuleQueue is not None:
            entity = LinkkfQueueEntity(P, self, episode_info)
            
            # URL 추출 수행 (GDM 위임을 위해 필수)
            try:
                entity.prepare_extra()
                if not entity.url or entity.url == entity.playid_url:
                     logger.error("Failed to extract Linkkf video URL")
                     return "extract_failed"
            except Exception as e:
                logger.error(f"Linkkf extraction error: {e}")
                return "extract_failed"

            logger.debug("entity:::> %s", entity.as_dict())
            
            # Save to DB first
            if db_entity is None:
                ModelLinkkfItem.append(entity.as_dict())
            
            # 설정에서 다운로드 방식 및 쓰레드 수 읽기
            download_method = P.ModelSetting.get("linkkf_download_method") or "ytdlp"
            download_threads = P.ModelSetting.get_int("linkkf_download_threads") or 16
            
            # Linkkf는 항상 'linkkf' source_type 사용 (GDM에서 YtdlpAria2Downloader로 매핑됨)
            gdm_source_type = "linkkf"

            # Prepare GDM options
            gdm_options = {
                "url": entity.url,
                "save_path": os.path.normpath(entity.savepath),
                "filename": entity.filename,
                "source_type": gdm_source_type,
                "caller_plugin": f"{P.package_name}_{self.name}",
                "callback_id": episode_info["_id"],
                "title": entity.filename or episode_info.get('title'),
                "thumbnail": episode_info.get('image'),
                "meta": {
                    "series": entity.content_title,
                    "season": entity.season,
                    "episode": entity.epi_queue,
                    "source": "linkkf"
                },
                "headers": entity.headers,
                "subtitles": getattr(entity, 'vtt', None),
                "connections": download_threads,
            }
            
            task = ModuleQueue.add_download(**gdm_options)
            if task:
                logger.info(f"Delegated Linkkf download to GDM: {entity.filename} (Method: {download_method})")
                return "enqueue_gdm_success"
        
        # 5. Fallback to FfmpegQueue if GDM not available
        logger.warning("GDM Module not found, falling back to FfmpegQueue")
        queue_len = len(self.queue.entity_list) if self.queue else 0
        logger.info(f"add() - Queue length: {queue_len}, episode _id: {episode_info.get('_id')}")
        
        if db_entity is None:
            entity = LinkkfQueueEntity(P, self, episode_info)
            logger.debug("entity:::> %s", entity.as_dict())
            ModelLinkkfItem.append(entity.as_dict())
            self.queue.add_queue(entity)
            return "enqueue_db_append"
        else:
            # db_entity exists but status is not completed
            status = db_entity.get("status") if isinstance(db_entity, dict) else db_entity.status
            logger.info(f"db_entity status: {status}, adding to queue")
            
            try:
                entity = LinkkfQueueEntity(P, self, episode_info)
                logger.info(f"LinkkfQueueEntity created, url: {entity.url}, filepath: {entity.filepath}")
                result = self.queue.add_queue(entity)
                logger.info(f"add_queue result: {result}, queue length after: {len(self.queue.entity_list)}")
            except Exception as e:
                logger.error(f"Error creating entity or adding to queue: {e}")
                logger.error(traceback.format_exc())
                return "entity_creation_error"
            
            return "enqueue_db_exist"


    # def is_exist(self, info):
    #     print(self.download_queue.entity_list)
    #     for en in self.download_queue.entity_list:
    #         if en.info["_id"] == info["_id"]:
    #             return True

    def is_exist(self, info):
        if LogicLinkkf.queue is None:
            return False
            
        for _ in LogicLinkkf.queue.entity_list:
            if _.info["_id"] == info["_id"]:
                return True
        return False

    def plugin_load(self):
        try:
            logger.debug("%s plugin_load", P.package_name)
            
            # 새 설정 초기화 (기존 설치에서 누락된 설정 추가)
            new_settings = {
                "linkkf_notify_enabled": "False",
                "linkkf_discord_webhook_url": "",
                "linkkf_telegram_bot_token": "",
                "linkkf_telegram_chat_id": "",
            }
            for key, default_value in new_settings.items():
                if P.ModelSetting.get(key) is None:
                    P.ModelSetting.set(key, default_value)
                    logger.info(f"[Linkkf] Initialized new setting: {key}")
            
            # 추가 설정: 자동 다운로드 vs 알림만
            if P.ModelSetting.get("linkkf_auto_download_new") is None:
                P.ModelSetting.set("linkkf_auto_download_new", "True")
                logger.info("[Linkkf] Initialized setting: linkkf_auto_download_new")
            
            # 모니터링 주기 설정 (기본 10분)
            if P.ModelSetting.get("linkkf_monitor_interval") is None:
                P.ModelSetting.set("linkkf_monitor_interval", "10")
                logger.info("[Linkkf] Initialized setting: linkkf_monitor_interval")
            
            # 클래스 레벨 큐 초기화
            if LogicLinkkf.queue is None:
                LogicLinkkf.queue = FfmpegQueue(
                    P, P.ModelSetting.get_int("linkkf_max_ffmpeg_process_count"), "linkkf", caller=self
                )
                LogicLinkkf.queue.queue_start()
            
            self.queue = LogicLinkkf.queue
            self.current_data = None

            # new version Todo:
            # if self.download_queue is None:
            #     self.download_queue = queue.Queue()
            #
            # if self.download_thread is None:
            #     self.download_thread = threading.Thread(target=self.download_thread_function, args=())
            #     self.download_thread.daemon = True
            #     self.download_thread.start()

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    def plugin_unload(self):
        pass

    def scheduler_function(self):
        """스케줄러 함수 - linkkf 자동 다운로드 처리"""
        from framework import F
        logger.info("linkkf scheduler_function::=========================")
        
        # Flask 앱 컨텍스트 내에서 실행 (스케줄러는 별도 스레드)
        with F.app.app_context():
            try:
                content_code_list = P.ModelSetting.get_list("linkkf_auto_code_list", "|")
                auto_mode_all = P.ModelSetting.get_bool("linkkf_auto_mode_all")
                
                logger.info(f"Auto-download codes: {content_code_list}")
                logger.info(f"Auto mode all episodes: {auto_mode_all}")
                
                if not content_code_list:
                    logger.info("[Scheduler] No auto-download codes configured")
                    return
                
                # 각 작품 코드별 처리
                for code in content_code_list:
                    code = code.strip()
                    if not code:
                        continue
                        
                    if code.lower() == "all":
                        # 사이트 전체 최신 에피소드 스캔
                        logger.info("[Scheduler] 'all' mode - scanning latest episodes from site")
                        self.scan_latest_episodes(auto_mode_all)
                        continue
                    
                    logger.info(f"[Scheduler] Processing code: {code}")
                    
                    try:
                        # 작품 정보 조회
                        series_info = self.get_series_info(code)
                        
                        if not series_info or "episode" not in series_info:
                            logger.warning(f"[Scheduler] No episode info for: {code}")
                            continue
                        
                        episodes = series_info.get("episode", [])
                        logger.info(f"[Scheduler] Found {len(episodes)} episodes for: {series_info.get('title', code)}")
                        
                        # 에피소드 순회 및 자동 등록
                        added_count = 0
                        added_episodes = []
                        for episode_info in episodes:
                            try:
                                result = self.add(episode_info)
                                if result and result.startswith("enqueue"):
                                    added_count += 1
                                    added_episodes.append(episode_info.get('title', 'Unknown'))
                                    logger.info(f"[Scheduler] Auto-enqueued: {episode_info.get('title', 'Unknown')}")
                                    self.socketio_callback("list_refresh", "")
                                    
                                # auto_mode_all이 False면 최신 1개만 (리스트가 최신순이라고 가정)
                                if not auto_mode_all and added_count > 0:
                                    logger.info(f"[Scheduler] Auto mode: latest only - stopping after 1 episode")
                                    break
                                    
                            except Exception as ep_err:
                                logger.error(f"[Scheduler] Episode add error: {ep_err}")
                                continue
                        
                        # 새 에피소드 추가됨 → 알림 전송
                        if added_count > 0:
                            self.send_notification(
                                title=series_info.get('title', code),
                                episodes=added_episodes,
                                count=added_count
                            )
                        
                        logger.info(f"[Scheduler] Completed {code}: added {added_count} episodes")
                        
                    except Exception as code_err:
                        logger.error(f"[Scheduler] Error processing {code}: {code_err}")
                        logger.error(traceback.format_exc())
                        continue
                        
            except Exception as e:
                logger.error(f"[Scheduler] Fatal error: {e}")
                logger.error(traceback.format_exc())

    def send_notification(self, title, episodes, count):
        """Discord/Telegram 알림 전송"""
        if not P.ModelSetting.get_bool("linkkf_notify_enabled"):
            return
        
        # 메시지 생성
        episode_list = "\n".join([f"• {ep}" for ep in episodes[:5]])
        if count > 5:
            episode_list += f"\n... 외 {count - 5}개"
        
        message = f"🎬 **{title}**\n새 에피소드 {count}개가 다운로드 큐에 추가되었습니다!\n\n{episode_list}"
        
        # Discord Webhook
        discord_url = P.ModelSetting.get("linkkf_discord_webhook_url")
        if discord_url:
            self.send_discord_notification(discord_url, title, message)
        
        # Telegram Bot
        telegram_token = P.ModelSetting.get("linkkf_telegram_bot_token")
        telegram_chat_id = P.ModelSetting.get("linkkf_telegram_chat_id")
        if telegram_token and telegram_chat_id:
            self.send_telegram_notification(telegram_token, telegram_chat_id, message)

    def scan_latest_episodes(self, auto_mode_all):
        """사이트에서 최신 에피소드 목록을 스캔하고 새 에피소드 감지"""
        try:
            auto_download = P.ModelSetting.get_bool("linkkf_auto_download_new")
            
            # 최신 방영 목록 가져오기 (1페이지만 - 가장 최신)
            latest_data = self.get_anime_info("ing", 1)
            
            if not latest_data or "episode" not in latest_data:
                logger.warning("[Scheduler] Failed to fetch latest anime list")
                return
            
            items = latest_data.get("episode", [])
            logger.info(f"[Scheduler] Scanned {len(items)} items from 'ing' page")
            
            total_added = 0
            all_new_episodes = []
            
            # 각 작품의 최신 에피소드 확인
            for item in items[:20]:  # 상위 20개만 처리 (성능 고려)
                try:
                    code = item.get("code")
                    if not code:
                        continue
                    
                    # 해당 작품의 에피소드 목록 조회
                    series_info = self.get_series_info(code)
                    if not series_info or "episode" not in series_info:
                        continue
                    
                    episodes = series_info.get("episode", [])
                    series_title = series_info.get("title", code)
                    
                    # 새 에피소드만 추가 (add 메서드가 중복 체크함)
                    for ep in episodes[:5]:  # 최신 5개만 확인
                        try:
                            if auto_download:
                                result = self.add(ep)
                                if result and result.startswith("enqueue"):
                                    total_added += 1
                                    all_new_episodes.append(f"{series_title} - {ep.get('title', '')}")
                                    self.socketio_callback("list_refresh", "")
                            else:
                                # 알림만 (다운로드 안함) - DB 체크로 새 에피소드인지 확인
                                ep_code = ep.get("code", "")
                                existing = ModelLinkkfItem.get_by_code(ep_code) if ep_code else None
                                if not existing:
                                    all_new_episodes.append(f"{series_title} - {ep.get('title', '')}")
                            
                            if not auto_mode_all and total_added > 0:
                                break
                        except Exception:
                            continue
                    
                    if not auto_mode_all and total_added > 0:
                        break
                        
                except Exception as e:
                    logger.debug(f"[Scheduler] Error scanning {item.get('code', 'unknown')}: {e}")
                    continue
            
            # 결과 알림
            if all_new_episodes:
                mode_text = "자동 다운로드" if auto_download else "새 에피소드 감지"
                self.send_notification(
                    title=f"[{mode_text}] 사이트 모니터링",
                    episodes=all_new_episodes,
                    count=len(all_new_episodes)
                )
                logger.info(f"[Scheduler] 'all' mode completed: {len(all_new_episodes)} new episodes found")
            else:
                logger.info("[Scheduler] 'all' mode: No new episodes found")
                
        except Exception as e:
            logger.error(f"[Scheduler] scan_latest_episodes error: {e}")
            logger.error(traceback.format_exc())

    def send_discord_notification(self, webhook_url, title, message):
        """Discord Webhook으로 알림 전송"""
        try:
            payload = {
                "embeds": [{
                    "title": f"📺 Linkkf 자동 다운로드",
                    "description": message,
                    "color": 0x10B981,  # 초록색
                    "footer": {"text": "FlaskFarm Anime Downloader"}
                }]
            }
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code in [200, 204]:
                logger.info(f"[Notify] Discord 알림 전송 성공: {title}")
            else:
                logger.warning(f"[Notify] Discord 알림 실패: {response.status_code}")
        except Exception as e:
            logger.error(f"[Notify] Discord 알림 오류: {e}")

    def send_telegram_notification(self, bot_token, chat_id, message):
        """Telegram Bot API로 알림 전송"""
        try:
            # Markdown 형식으로 변환 (** -> *)
            telegram_message = message.replace("**", "*")
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": telegram_message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            if result.get("ok"):
                logger.info(f"[Notify] Telegram 알림 전송 성공")
            else:
                logger.warning(f"[Notify] Telegram 알림 실패: {result.get('description', 'Unknown')}")
        except Exception as e:
            logger.error(f"[Notify] Telegram 알림 오류: {e}")

    def download_thread_function(self):
        while True:
            try:
                while True:
                    logger.debug(self.current_download_count)
                    if self.current_download_count < P.ModelSetting.get_int(
                        f"{self.name}_max_download_count"
                    ):
                        break
                    time.sleep(5)

                db_item = self.download_queue.get()
                if db_item.status == "CANCEL":
                    self.download_queue.task_done()
                    continue
                if db_item is None:
                    self.download_queue.task_done()
                    continue

            except Exception as e:
                logger.error(f"Exception: {str(e)}")
                logger.error(traceback.format_exc())


class LinkkfQueueEntity(FfmpegQueueEntity):
    def __init__(self, P, module_logic, info):
        super(LinkkfQueueEntity, self).__init__(P, module_logic, info)
        self._vi = None
        self.epi_queue = None
        self.vtt = None
        self.srt_url = None
        self.headers = None
        
        # info에서 필요한 정보 설정
        playid_url = info.get("url", "")
        self.filename = info.get("filename", "")
        self.quality = info.get("quality", "720p")
        self.season = info.get("season", "1")
        self.content_title = info.get("program_title", "")
        self.savepath = info.get("save_path", "")
        
        # savepath가 비어있으면 기본값 설정
        if not self.savepath:
            default_path = P.ModelSetting.get("linkkf_download_path")
            logger.info(f"[DEBUG] linkkf_download_path from DB: '{default_path}'")
            logger.info(f"[DEBUG] info save_path: '{info.get('save_path', 'NOT SET')}'")
            logger.info(f"[DEBUG] info save_folder: '{info.get('save_folder', 'NOT SET')}'")
            
            if default_path:
                save_folder = info.get("save_folder", "Unknown")
                self.savepath = os.path.normpath(os.path.join(default_path, save_folder))
            else:
                self.savepath = "/tmp/anime_downloads"
            logger.info(f"[DEBUG] Final savepath set to: '{self.savepath}'")
        
        # filepath = savepath + filename (전체 경로)
        self.filepath = os.path.normpath(os.path.join(self.savepath, self.filename)) if self.filename else self.savepath
        logger.info(f"[DEBUG] filepath set to: '{self.filepath}'")
        
        # playid URL에서 실제 비디오 URL과 자막 URL 추출은 prepare_extra에서 수행합니다.
        self.playid_url = playid_url
        self.url = playid_url # 초기값 설정

    def get_downloader(self, video_url, output_file, callback=None, callback_function=None):
        """
        Factory를 통해 다운로더 인스턴스를 반환합니다.
        설정에서 다운로드 방식을 읽어옵니다.
        """
        from .lib.downloader_factory import DownloaderFactory
        
        # 설정에서 다운로드 방식 및 쓰레드 수 읽기
        method = self.P.ModelSetting.get("linkkf_download_method") or "ytdlp"
        threads = self.P.ModelSetting.get_int("linkkf_download_threads") or 16
        logger.info(f"Linkkf get_downloader using method: {method}, threads: {threads}")
        
        return DownloaderFactory.get_downloader(
            method=method,
            video_url=video_url,
            output_file=output_file,
            headers=self.headers,
            callback=callback,
            callback_id="linkkf",
            threads=threads,
            callback_function=callback_function
        )

    def prepare_extra(self):
        """
        [Lazy Extraction] 
        다운로드 직전에 실제 비디오 URL과 자막 URL을 추출합니다.
        """
        try:
            logger.info(f"Linkkf Queue prepare_extra starting for: {self.content_title} - {self.filename}")
            video_url, referer_url, vtt_url = LogicLinkkf.extract_video_url_from_playid(self.playid_url)
            
            if video_url:
                self.url = video_url
                # HLS 다운로드를 위한 헤더 설정
                self.headers = {
                    "Referer": referer_url or "https://linkkf.live/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                }
                logger.info(f"Video URL extracted: {self.url}")
                
                # 자막 URL 저장
                if vtt_url:
                    self.vtt = vtt_url
                    logger.info(f"Subtitle URL saved: {self.vtt}")
            else:
                # 추출 실패 시 원본 URL 사용 (fallback)
                self.url = self.playid_url
            
            # ------------------------------------------------------------------
            # [IMMEDIATE SYNC] - Update DB with all extracted metadata
            # ------------------------------------------------------------------
            try:
                from .mod_linkkf import ModelLinkkfItem
                db_item = ModelLinkkfItem.get_by_linkkf_id(self.info.get("_id"))
                if db_item:
                    logger.debug(f"[SYNC] Syncing metadata for Linkkf _id: {self.info.get('_id')}")
                    # Parse episode number if possible for DB field
                    epi_no = None
                    try:
                        match = re.search(r"(?P<epi_no>\d+)", str(self.info.get("ep_num", "")))
                        if match:
                            epi_no = int(match.group("epi_no"))
                    except:
                        pass

                    db_item.title = self.content_title
                    db_item.season = int(self.season) if self.season else 1
                    db_item.episode_no = epi_no
                    db_item.quality = self.quality
                    db_item.savepath = self.savepath
                    db_item.filename = self.filename
                    db_item.filepath = self.filepath
                    db_item.video_url = self.url
                    db_item.vtt_url = self.vtt
                    db_item.save()
            except Exception as sync_err:
                logger.error(f"[SYNC] Failed to sync Linkkf metadata in prepare_extra: {sync_err}")

        except Exception as e:
            logger.error(f"Exception in video URL extraction: {e}")
            logger.error(traceback.format_exc())
            self.url = self.playid_url

    def download_completed(self):
        """다운로드 완료 후 처리 (파일 이동, DB 업데이트 등)"""
        try:
            logger.info(f"LinkkfQueueEntity.download_completed called for index {self.entity_id}")
            
            from framework import app
            with app.app_context():
                # DB 상태 업데이트
                db_item = ModelLinkkfItem.get_by_linkkf_id(self.info.get("_id"))
                if db_item:
                    db_item.status = "completed"
                    db_item.completed_time = datetime.now()
                    db_item.filepath = self.filepath
                    db_item.filename = self.filename
                    db_item.savepath = self.savepath
                    db_item.quality = self.quality
                    db_item.video_url = self.url
                    db_item.vtt_url = self.vtt
                    db_item.save()
                    logger.info(f"Updated DB status to 'completed' for episode {db_item.id}")
                else:
                    logger.warning(f"Could not find DB item to update for _id {self.info.get('_id')}")
                
            # 전체 목록 갱신을 위해 소켓IO 발신 (필요 시)
            # from framework import socketio
            # socketio.emit("linkkf_refresh", {"idx": self.entity_id}, namespace="/framework")
        except Exception as e:
            logger.error(f"Error in LinkkfQueueEntity.download_completed: {e}")
            logger.error(traceback.format_exc())

    def refresh_status(self):
        try:
            # from framework import socketio (FlaskFarm 표준 방식)
            from framework import socketio
            
            data = self.as_dict()
            
            # /framework namespace로 linkkf_status 이벤트 전송
            socketio.emit("linkkf_status", data, namespace="/framework")
            
        except Exception as e:
            logger.error(f"refresh_status error: {e}")

    def info_dict(self, tmp):
        # logger.debug('self.info::> %s', self.info)
        for key, value in self.info.items():
            tmp[key] = value
        tmp["vtt"] = self.vtt
        tmp["season"] = self.season
        tmp["content_title"] = self.content_title
        tmp["linkkf_info"] = self.info
        tmp["epi_queue"] = self.epi_queue
        
        # 템플릿이 기대하는 필드들 추가
        tmp["idx"] = self.entity_id
        tmp["callback_id"] = "linkkf"
        tmp["start_time"] = self.created_time.strftime("%m-%d %H:%M") if hasattr(self, 'created_time') and self.created_time and hasattr(self.created_time, 'strftime') else (self.created_time if self.created_time else "")
        tmp["status_kor"] = self.ffmpeg_status_kor if self.ffmpeg_status_kor else "대기중"
        tmp["percent"] = self.ffmpeg_percent if self.ffmpeg_percent else 0
        tmp["duration_str"] = ""
        tmp["current_pf_count"] = 0
        tmp["current_speed"] = self.current_speed if hasattr(self, 'current_speed') and self.current_speed else ""
        tmp["download_time"] = self.download_time if hasattr(self, 'download_time') and self.download_time else ""
        tmp["status_str"] = "WAITING" if not self.ffmpeg_status else ("DOWNLOADING" if self.ffmpeg_status == 5 else "COMPLETED" if self.ffmpeg_status == 7 else "WAITING")
        tmp["temp_fullpath"] = ""
        tmp["save_fullpath"] = self.filepath if self.filepath else ""
        tmp["duration"] = ""
        tmp["current_duration"] = ""
        tmp["current_bitrate"] = ""
        tmp["end_time"] = ""
        tmp["max_pf_count"] = 0
        tmp["exist"] = False
        
        return tmp

    def make_episode_info(self):
        url2s = []
        url = None

        try:
            data = LogicLinkkf.get_html_episode_content(self.url)
            tree = html.fromstring(data)

            xpath_select_query = '//*[@id="body"]/div/span/center/select/option'

            if len(tree.xpath(xpath_select_query)) > 0:
                # by k45734
                logger.debug("make_episode_info: select found")
                xpath_select_query = '//select[@class="switcher"]/option'
                for tag in tree.xpath(xpath_select_query):
                    url2s2 = tag.attrib["value"]
                    if "k40chan" in url2s2:
                        pass
                    elif "ani1c12" in url2s2:
                        pass
                    else:
                        url2s.append(url2s2)
            else:
                logger.debug("make_episode_info: else branch")

                tt = re.search(r"var player_data=(.*?)<", data, re.S)
                json_string = tt.group(1)
                tt2 = re.search(r'"url":"(.*?)"', json_string, re.S)
                json_string2 = tt2.group(1)
                ttt = "https://s2.ani1c12.top/player/index.php?data=" + json_string2
                response = LogicLinkkf.get_html(ttt)
                tree = html.fromstring(response)
                xpath_select_query = '//select[@id="server-list"]/option'
                for tag in tree.xpath(xpath_select_query):
                    url2s2 = tag.attrib["value"]
                    # if 'k40chan' in url2s2:
                    #    pass
                    # elif 'k39aha' in url2s2:
                    if "ds" in url2s2:
                        pass
                    else:
                        url2s.append(url2s2)

                # logger.info('dx: url', url)
                logger.info("dx: urls2:: %s", url2s)

                video_url = None
                referer_url = None  # dx

                for url2 in url2s:
                    try:
                        if video_url is not None:
                            continue
                        # logger.debug(f"url: {url}, url2: {url2}")
                        ret = LogicLinkkf.get_video_url_from_url(url, url2)
                        # logger.debug(f"ret::::> {ret}")

                        if ret is not None:
                            video_url = ret
                            referer_url = url2
                    except Exception as e:
                        logger.error("Exception:%s", e)
                        logger.error(traceback.format_exc())

                # logger.info(video_url)
                # return [video_url, referer_url]
                return video_url
            logger.info("dx: urls2:: %s", url2s)

            video_url = None
            referer_url = None  # dx

        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            logger.error(traceback.format_exc())


class ModelLinkkfItem(db.Model):
    __tablename__ = "{package_name}_linkkf_item".format(package_name=P.package_name)
    __table_args__ = {"mysql_collate": "utf8_general_ci", "extend_existing": True}
    __bind_key__ = P.package_name
    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)
    completed_time = db.Column(db.DateTime)
    reserved = db.Column(db.JSON)
    content_code = db.Column(db.String)
    season = db.Column(db.Integer)
    episode_no = db.Column(db.Integer)
    title = db.Column(db.String)
    episode_title = db.Column(db.String)
    # linkkf_va = db.Column(db.String)
    linkkf_vi = db.Column(db.String)
    linkkf_id = db.Column(db.String)
    quality = db.Column(db.String)
    filepath = db.Column(db.String)
    filename = db.Column(db.String)
    savepath = db.Column(db.String)
    video_url = db.Column(db.String)
    vtt_url = db.Column(db.String)
    thumbnail = db.Column(db.String)
    status = db.Column(db.String)
    linkkf_info = db.Column(db.JSON)

    def __init__(self):
        self.created_time = datetime.now()

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret["created_time"] = self.created_time.strftime("%Y-%m-%d %H:%M:%S")
        ret["completed_time"] = (
            self.completed_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.completed_time is not None
            else None
        )
        return ret

    def save(self):
        from framework import F
        with F.app.app_context():
            db.session.add(self)
            db.session.commit()

    @classmethod
    def get_by_id(cls, idx):
        from framework import F
        with F.app.app_context():
            return db.session.query(cls).filter_by(id=idx).first()

    @classmethod
    def get_by_linkkf_id(cls, linkkf_id):
        from framework import F
        with F.app.app_context():
            return db.session.query(cls).filter_by(linkkf_id=linkkf_id).first()

    @classmethod
    def append(cls, q):
        from framework import F
        with F.app.app_context():
            logger.debug(q)
            item = ModelLinkkfItem()
            item.content_code = q["program_code"]
            item.season = q["season"]
            item.episode_no = q["epi_queue"]
            item.title = q["content_title"]
            item.episode_title = q["title"]
            # item.linkkf_va = q["va"]
            item.linkkf_code = q["code"]
            item.linkkf_id = q["_id"]
            item.quality = q["quality"]
            item.filepath = q["filepath"]
            item.filename = q["filename"]
            item.savepath = q["savepath"]
            item.video_url = q["url"]
            item.vtt_url = q["vtt"]
            item.thumbnail = q.get("image", "")
            item.status = "wait"
            item.linkkf_info = q["linkkf_info"]
            item.save()

    @classmethod
    def get_paging_info(cls, count, page, page_size):
        total_page = int(count / page_size) + (1 if count % page_size != 0 else 0)
        start_page = (int((page - 1) / 10)) * 10 + 1
        last_page = start_page + 9
        if last_page > total_page:
            last_page = total_page
            
        ret = {
            "start_page": start_page,
            "last_page": last_page,
            "total_page": total_page,
            "current_page": page,
            "count": count,
            "page_size": page_size,
        }
        ret["prev_page"] = True if ret["start_page"] != 1 else False
        ret["next_page"] = (
            True
            if (ret["start_page"] + 10) <= ret["total_page"]
            else False
        )
        return ret

    @classmethod
    def delete_by_id(cls, idx):
        from framework import F
        with F.app.app_context():
            db.session.query(cls).filter_by(id=idx).delete()
            db.session.commit()
        return True

    @classmethod
    def web_list(cls, req):
        from framework import F
        with F.app.app_context():
            ret = {}
            page = int(req.form["page"]) if "page" in req.form else 1
            page_size = 30
            job_id = ""
            search = req.form["search_word"] if "search_word" in req.form else ""
            option = req.form["option"] if "option" in req.form else "all"
            order = req.form["order"] if "order" in req.form else "desc"
            query = cls.make_query(search=search, order=order, option=option)
            count = query.count()
            query = query.limit(page_size).offset((page - 1) * page_size)
            lists = query.all()
            ret["list"] = [item.as_dict() for item in lists]
            ret["paging"] = cls.get_paging_info(count, page, page_size)
            return ret

    @classmethod
    def make_query(cls, search="", order="desc", option="all"):
        from framework import F
        with F.app.app_context():
            query = db.session.query(cls)
            if search is not None and search != "":
                if search.find("|") != -1:
                    tmp = search.split("|")
                    conditions = []
                    for tt in tmp:
                        if tt != "":
                            conditions.append(cls.filename.like("%" + tt.strip() + "%"))
                    query = query.filter(or_(*conditions))
                elif search.find(",") != -1:
                    tmp = search.split(",")
                    for tt in tmp:
                        if tt != "":
                            query = query.filter(cls.filename.like("%" + tt.strip() + "%"))
                else:
                    query = query.filter(cls.filename.like("%" + search + f"%"))
            
            if option == "completed":
                query = query.filter(cls.status == "completed")
                
            if order == "desc":
                query = query.order_by(desc(cls.id))
            else:
                query = query.order_by(cls.id)
            return query
