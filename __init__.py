# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 2:55 PM
# @Author  : yommi
# @Site    : 
# @File    : __init__
# @Software: PyCharm
from .setup import P
blueprint = P.blueprint
menu = P.menu
plugin_info = P.plugin_info

def plugin_load():
    if P.logic:
        P.logic.plugin_load()

def plugin_unload():
    if P.logic:
        P.logic.plugin_unload()
