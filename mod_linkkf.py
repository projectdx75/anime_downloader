#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 3:44 PM
# @Author  : yommi
# @Site    :
# @File    : logic_linkkf
# @Software: PyCharm
import os
import re
import sys
import traceback
from datetime import datetime

import PIL.Image
# third-party
import requests
from bs4 import BeautifulSoup
# third-party
from flask import jsonify, render_template, request
# sjva 공용
from framework import db, path_data, scheduler
from lxml import html
from plugin import PluginModuleBase

from anime_downloader.lib.util import Util
# 패키지
# from .plugin import P
from anime_downloader.setup import *

# from linkkf.model import ModelLinkkfProgram

# from linkkf.model import ModelLinkkfProgram

# from tool_base import d


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
    referer = None

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
                P.ModelSetting.set("linkkf_current_code", code)
                data = self.get_series_info(code)
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
                url = f"{P.ModelSetting.get('linkkf_url')}/airing/page/{page}"
                items_xpath = '//div[@class="myui-vodlist__box"]'
                title_xpath = './/a[@class="text-fff"]//text()'
            elif cate == "movie":
                url = f"{P.ModelSetting.get('linkkf_url')}/ani/page/{page}"
                items_xpath = '//div[@class="myui-vodlist__box"]'
                title_xpath = './/a[@class="text-fff"]//text()'
            elif cate == "complete":
                url = f"{P.ModelSetting.get('linkkf_url')}/anime-list/page/{page}"
                items_xpath = '//div[@class="myui-vodlist__box"]'
                title_xpath = './/a[@class="text-fff"]//text()'
            elif cate == "top_view":
                url = f"{P.ModelSetting.get('linkkf_url')}/topview/page/{page}"
                items_xpath = '//div[@class="myui-vodlist__box"]'
                title_xpath = './/a[@class="text-fff"]//text()'

            logger.info("url:::> %s", url)
            logger.info("test..........................")
            logger.info("test..........................")
            if self.referer is None:
                self.referer = "https://linkkf.app"

            data = {"ret": "success", "page": page}
            response_data = LogicLinkkf.get_html(url, timeout=10)
            # P.logger.debug(response_data)
            P.logger.debug("debug.....................")
            tree = html.fromstring(response_data)
            tmp_items = tree.xpath(items_xpath)

            if tree.xpath('//div[@id="wp_page"]//text()'):
                data["total_page"] = tree.xpath('//div[@id="wp_page"]//text()')[-1]
            else:
                data["total_page"] = 0
            data["episode_count"] = len(tmp_items)
            data["episode"] = []

            for item in tmp_items:
                entity = dict()
                entity["link"] = item.xpath(".//a/@href")[0]
                entity["code"] = re.search(r"[0-9]+", entity["link"]).group()
                entity["title"] = item.xpath(title_xpath)[0].strip()
                entity["image_link"] = item.xpath("./a/@data-original")[0]
                entity["chapter"] = (
                    item.xpath("./a/span//text()")[0].strip()
                    if len(item.xpath("./a/span//text()")) > 0
                    else ""
                )
                # logger.info('entity:::', entity['title'])
                data["episode"].append(entity)

            # logger.debug(data)

            return data
        except Exception as e:
            P.logger.error("Exception:%s", e)
            P.logger.error(traceback.format_exc())
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
                return LogicLinkkf.current_data
            url = "%s/%s" % (P.ModelSetting.get("linkkf_url"), code)
            logger.info(url)

            logger.debug(LogicLinkkf.headers)
            html_content = LogicLinkkf.get_html(url, cached=False)
            # html_content = LogicLinkkf.get_html_playwright(url)
            # html_content = LogicLinkkf.get_html_cloudflare(url, cached=False)

            sys.setrecursionlimit(10 ** 7)
            # logger.info(html_content)
            tree = html.fromstring(html_content)
            # tree = etree.fromstring(
            #     html_content, parser=etree.XMLParser(huge_tree=True)
            # )
            # tree1 = BeautifulSoup(html_content, "lxml")

            soup = BeautifulSoup(html_content, "html.parser")
            # tree = etree.HTML(str(soup))
            # logger.info(tree)

            tmp2 = soup.select("ul > a")
            if len(tmp2) == 0:
                tmp = soup.select("u > a")
            else:
                tmp = soup.select("ul > a")

            # logger.debug(f"tmp1 size:=> {str(len(tmp))}")

            try:
                tmp = (
                    tree.xpath('//div[@class="hrecipe"]/article/center/strong')[0]
                    .text_content()
                    .strip()
                )
            except IndexError:
                tmp = tree.xpath("//article/center/strong")[0].text_content().strip()

            # logger.info(tmp)
            match = re.compile(r"(?P<season>\d+)기").search(tmp)
            if match:
                data["season"] = match.group("season")
            else:
                data["season"] = "1"

            data["_id"] = str(code)
            data["title"] = tmp.replace(data["season"] + "기", "").strip()
            data["title"] = data["title"].replace("()", "").strip()
            data["title"] = (
                Util.change_text_for_use_filename(data["title"])
                .replace("OVA", "")
                .strip()
            )

            try:
                data["poster_url"] = tree.xpath(
                    '//div[@class="myui-content__thumb"]/a/@data-original'
                )
                # print(tree.xpath('//div[@class="myui-content__detail"]/text()'))
                if len(tree.xpath('//div[@class="myui-content__detail"]/text()')) > 3:
                    data["detail"] = [
                        {
                            "info": str(tree.xpath(
                                "//div[@class='myui-content__detail']/text()"
                            )[3])
                        }
                    ]
                else:
                    data["detail"] = [{"정보없음": ""}]
            except Exception as e:
                logger.error(e)
                data["detail"] = [{"정보없음": ""}]
                data["poster_url"] = None

            data["rate"] = tree.xpath('span[@class="tag-score"]')

            tag_score = tree.xpath('//span[@class="taq-score"]')[0].text_content()
            # logger.debug(tag_score)
            tag_count = (
                tree.xpath('//span[contains(@class, "taq-count")]')[0]
                .text_content()
                .strip()
            )
            data_rate = tree.xpath('//div[@class="rating"]/div/@data-rate')

            tmp2 = soup.select("ul > a")
            if len(tmp) == 0:
                tmp = soup.select("u > a")
            else:
                tmp = soup.select("ul > a")

            if tmp is not None:
                data["episode_count"] = str(len(tmp))
            else:
                data["episode_count"] = "0"

            data["episode"] = []
            # tags = tree.xpath(
            #     '//*[@id="syno-nsc-ext-gen3"]/article/div[1]/article/a')
            # tags = tree.xpath("//ul/a")
            tags = soup.select("ul > u > a")
            if len(tags) > 0:
                pass
            else:
                tags = soup.select("ul > a")

            logger.debug(len(tags))

            # logger.info("tags", tags)
            # re1 = re.compile(r'\/(?P<code>\d+)')
            re1 = re.compile(r"\-([^-])+\.")

            data["save_folder"] = data["title"]
            # logger.debug(f"save_folder::> {data['save_folder']}")

            # program = (
            #     db.session.query(ModelLinkkfProgram).filter_by(programcode=code).first()
            # )

            idx = 1
            for t in tags:
                entity = {
                    "_id": data["code"],
                    "program_code": data["code"],
                    "program_title": data["title"],
                    "save_folder": Util.change_text_for_use_filename(
                        data["save_folder"]
                    ),
                    "title": t.text.strip(),
                    # "title": t.text_content().strip(),
                }
                # entity['code'] = re1.search(t.attrib['href']).group('code')

                # logger.debug(f"title ::>{entity['title']}")

                # 고유id임을 알수 없는 말도 안됨..
                # 에피소드 코드가 고유해야 상태값 갱신이 제대로 된 값에 넣어짐
                p = re.compile(r"([0-9]+)화?")
                m_obj = p.match(entity["title"])
                # logger.info(m_obj.group())
                # entity['code'] = data['code'] + '_' +str(idx)

                episode_code = None
                # logger.debug(f"m_obj::> {m_obj}")
                if m_obj is not None:
                    episode_code = m_obj.group(1)
                    entity["code"] = data["code"] + episode_code.zfill(4)
                else:
                    entity["code"] = data["code"]

                aa = t["href"]
                if "/player" in aa:
                    entity["url"] = "https://linkkf.app" + t["href"]
                else:
                    entity["url"] = t["href"]
                entity["season"] = data["season"]

                # 저장 경로 저장
                # Todo: db
                tmp_save_path = P.ModelSetting.get(f"linkkf_download_path")
                if P.ModelSetting.get("linkkf_auto_make_folder") == "True":
                    program_path = os.path.join(tmp_save_path, entity["save_folder"])
                    entity["save_path"] = program_path
                    if P.ModelSetting.get("linkkf_auto_make_season_folder"):
                        entity["save_path"] = os.path.join(
                            entity["save_path"], "Season %s" % int(entity["season"])
                        )

                entity["image"] = data["poster_url"]

                entity["filename"] = LogicLinkkf.get_filename(
                    data["save_folder"], data["season"], entity["title"]
                )
                data["episode"].append(entity)
                idx = idx + 1

            data["ret"] = True
            # logger.info('data', data)
            self.current_data = data

            return data

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            data["log"] = str(e)
            data["ret"] = "error"
            return data
        except IndexError as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            data["log"] = str(e)
            data["ret"] = "error"
            return data

    @staticmethod
    def get_html(url: str, referer: str = None, cached: bool = False, stream: bool = False, timeout: int = 5):
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
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())



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
