# -*- coding: utf-8 -*-
# @Time    : 2022/02/08 2:55 PM
# @Author  : yommi
# @Site    : 
# @File    : __init__
# @Software: PyCharm
from .setup import P
import threading
blueprint = P.blueprint
menu = P.menu
plugin_info = P.plugin_info

def plugin_load():
    if P.logic:
        P.logic.plugin_load()
        try:
            from .mod_ohli24 import LogicOhli24
            P.logger.info("[ZendriverDaemon] Shared bootstrap requested")
            threading.Thread(target=LogicOhli24.bootstrap_zendriver_service, daemon=True).start()
        except Exception as e:
            P.logger.warning(f"[ZendriverDaemon] Shared bootstrap skipped: {e}")

def plugin_unload():
    if P.logic:
        P.logic.plugin_unload()
