#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 3:44 PM
# @Author  : yommi
# @Site    :
# @File    : logic_linkkf
# @Software: PyCharm
import os, sys, traceback, re, json, threading
from datetime import datetime
import copy

# third-party
import requests
from lxml import html
from urllib import parse

# third-party
from flask import request, render_template, jsonify
from sqlalchemy import or_, and_, func, not_, desc

# sjva 공용
from framework import db, scheduler, path_data, socketio
from framework.util import Util
from framework import F
from plugin import (
    PluginModuleBase
)
from flaskfarm.lib.plugin._ffmpeg_queue import FfmpegQueueEntity, FfmpegQueue

# from tool_base import d

# 패키지
# from .plugin import P
from .setup import *

logger = P.logger


class LogicLinkkf(PluginModuleBase):
    db_default = {
        "linkkf_db_version": "1",
        "linkkf_url": "https://linkkf.app",
        "linkkf_download_path": os.path.join(path_data, P.package_name, "linkkf"),
        "linkkf_auto_make_folder": "True",
        "linkkf_auto_make_season_folder": "True",
        "linkkf_finished_insert": "[완결]",
        "linkkf_max_ffmpeg_process_count": "1",
        "linkkf_order_desc": "False",
        "linkkf_auto_start": "False",
        "linkkf_interval": "* 5 * * *",
        "linkkf_auto_mode_all": "False",
        "linkkf_auto_code_list": "all",
        "linkkf_current_code": "",
        "linkkf_uncompleted_auto_enqueue": "False",
        "linkkf_image_url_prefix_series": "",
        "linkkf_image_url_prefix_episode": "",
        "linkkf_discord_notify": "True",
    }
    current_headers = None
    current_data = None

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

    def __init__(self, P):
        super(LogicLinkkf, self).__init__(P, "setting", scheduler_desc="linkkf 자동 다운로드")
        self.name = "linkkf"
        # default_route_socketio(P, self)
        default_route_socketio_module(self, attach='/setting')

    def process_menu(self, sub, req):
        arg = P.ModelSetting.to_dict()
        arg["sub"] = self.name
        if sub in ["setting", "queue", "category", "list", "request", "search"]:
            if sub == "request" and req.args.get("content_code") is not None:
                arg["linkkf_current_code"] = req.args.get("content_code")
            if sub == "setting":
                job_id = "%s_%s" % (self.P.package_name, self.name)
                arg["scheduler"] = str(scheduler.is_include(job_id))
                arg["is_running"] = str(scheduler.is_running(job_id))
            return render_template(
                "{package_name}_{module_name}_{sub}.html".format(
                    package_name=P.package_name, module_name=self.name, sub=sub
                ),
                arg=arg,
            )
        return render_template("sample.html", title="%s - %s" % (P.package_name, sub))

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
                P.ModelSetting.set("ohli24_current_code", code)
                data = self.get_series_info(code, wr_id, bo_table)
                self.current_data = data
                return jsonify({"ret": "success", "data": data, "code": code})
            elif sub == "anime_list":
                data = []
                cate = request.form["type"]
                page = request.form["page"]

                data = self.get_anime_info(cate, page)
                # self.current_data = data
                return jsonify(
                    {"ret": "success", "cate": cate, "page": page, "data": data}
                )
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
                pass
            elif sub == "entity_list":
                pass
            elif sub == "queue_command":
                pass
            elif sub == "add_queue_checked_list":
                pass
            elif sub == "web_list":
                pass
            elif sub == "db_remove":
                pass
            elif sub == "add_whitelist":
                pass

        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())

    def get_anime_info(self, cate, page):
        try:
            if cate == "ing":
                url = (
                        P.ModelSetting.get("ohli24_url")
                        + "/bbs/board.php?bo_table="
                        + cate
                        + "&page="
                        + page
                )
            elif cate == "movie":
                url = (
                        P.ModelSetting.get("ohli24_url")
                        + "/bbs/board.php?bo_table="
                        + cate
                        + "&page="
                        + page
                )
            else:
                url = (
                        P.ModelSetting.get("ohli24_url")
                        + "/bbs/board.php?bo_table="
                        + cate
                        + "&page="
                        + page
                )
                # cate == "complete":
            logger.info("url:::> %s", url)
            data = {}
            response_data = LogicOhli24.get_html(url, timeout=10)
            tree = html.fromstring(response_data)
            tmp_items = tree.xpath('//div[@class="list-row"]')
            data["anime_count"] = len(tmp_items)
            data["anime_list"] = []

            for item in tmp_items:
                entity = {}
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["code"] = entity["link"].split("/")[-1]
                entity["title"] = item.xpath(".//div[@class='post-title']/text()")[
                    0
                ].strip()
                entity["image_link"] = item.xpath(".//div[@class='img-item']/img/@src")[
                    0
                ].replace("..", P.ModelSetting.get("ohli24_url"))
                data["ret"] = "success"
                data["anime_list"].append(entity)

            return data
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
            return {"ret": "exception", "log": str(e)}
    @staticmethod
    def get_html(url, referer=None, stream=False, timeout=5):
        data = ""
        headers = {
            "referer": f"https://linkkf.app",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/96.0.4664.110 Whale/3.12.129.46 Safari/537.36"
                          "Mozilla/5.0 (Macintosh; Intel "
                          "Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 "
                          "Whale/3.12.129.46 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:

            if LogicOhli24.session is None:
                LogicOhli24.session = requests.session()

            # logger.debug('get_html :%s', url)
            headers["Referer"] = "" if referer is None else referer
            page_content = LogicOhli24.session.get(
                url, headers=headers, timeout=timeout
            )
            data = page_content.text
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
        return data
class ModelLinkkfItem(db.Model):
    __tablename__ = "{package_name}_linkkf_item".format(package_name=P.package_name)
    __table_args__ = {"mysql_collate": "utf8_general_ci"}
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
    linkkf_va = db.Column(db.String)
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
        db.session.add(self)
        db.session.commit()

    @classmethod
    def get_by_id(cls, idx):
        return db.session.query(cls).filter_by(id=idx).first()
