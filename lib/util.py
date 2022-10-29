# -*- coding: utf-8 -*-
#########################################################
# python
import os
import re
import json
import traceback
import platform
import subprocess
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
