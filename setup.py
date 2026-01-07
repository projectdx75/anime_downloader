__menu = {
    'uri': __package__,
    'name': '애니 다운로더',
    'list': [
        {
            'uri': 'ohli24',
            'name': '애니24',
            'list': [
                {
                    'uri': 'setting',
                    'name': '설정'
                },
                {
                    'uri': 'request',
                    'name': '요청'
                },
                {
                    'uri': 'queue',
                    'name': '큐'
                },
                {
                    'uri': 'search',
                    'name': '검색',
                },
                {
                    'uri': 'list',
                    'name': '목록',
                }

            ]
        },
        {
            'uri': 'anilife',
            'name': '애니라이프',
            'list': [
                {
                    'uri': 'setting',
                    'name': '설정'
                },
                {
                    'uri': 'request',
                    'name': '요청'
                },
                {
                    'uri': 'queue',
                    'name': '큐'
                },
                {
                    'uri': 'search',
                    'name': '검색',
                },
                {
                    'uri': 'list',
                    'name': '목록',
                }

            ]
        },
        {
            'uri': 'linkkf',
            'name': '링크애니',
            'list': [
                {
                    'uri': 'setting',
                    'name': '설정'
                },
                {
                    'uri': 'request',
                    'name': '요청'
                },
                {
                    'uri': 'queue',
                    'name': '큐'
                },
                {
                    'uri': 'search',
                    'name': '검색',
                },
                {
                    'uri': 'list',
                    'name': '목록',
                }

            ]
        },
        {
            'uri': 'guide',
            'name': '매뉴얼',
            'list': [
                {
                    'uri': 'README.md',
                    'name': 'README',
                },
            ]
        },
        {
            'uri': 'log',
            'name': '로그',
        },
    ]
}

setting = {
    'filepath': __file__,
    'use_db': True,
    'use_default_setting': True,
    'home_module': 'ohli24',
    'menu': __menu,
    # 'setting_menu': None,
    'default_route': 'normal',
}

from plugin import *
import os
import traceback
from flask import render_template
import subprocess
import sys

# curl_cffi 자동 설치 루틴
try:
    import curl_cffi
except ImportError:
    try:
        P.logger.info("curl_cffi not found. Attempting to install...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "curl-cffi"])
        P.logger.info("curl_cffi installed successfully.")
    except Exception as e:
        P.logger.error(f"Failed to install curl_cffi: {e}")

class LogicLog(PluginModuleBase):
    def __init__(self, P):
        super(LogicLog, self).__init__(P, name='log', first_menu='log')

    def process_menu(self, sub, req):
        return render_template('anime_downloader_log.html', package=self.P.package_name)

class LogicGuide(PluginModuleBase):
    def __init__(self, P):
        super(LogicGuide, self).__init__(P, name='guide', first_menu='README.md')

    def process_menu(self, sub, req):
        try:
            # sub is likely the filename e.g., 'README.md'
            plugin_root = os.path.dirname(self.P.blueprint.template_folder)
            filepath = os.path.join(plugin_root, *sub.split('/'))
            from support import SupportFile
            data = SupportFile.read_file(filepath)
            # Override to use our custom manual template
            return render_template('anime_downloader_manual.html', data=data)
        except Exception as e:
            self.P.logger.error(f"Exception:{str(e)}")
            self.P.logger.error(traceback.format_exc())
            return render_template('sample.html', title=f"Error loading manual: {sub}")

DEFINE_DEV = True

P = create_plugin_instance(setting)
try:
    if DEFINE_DEV:
        from .mod_ohli24 import LogicOhli24
        from .mod_anilife import LogicAniLife
        from .mod_linkkf import LogicLinkkf
        
        # Include our custom logic modules
        P.set_module_list([LogicOhli24, LogicAniLife, LogicLinkkf, LogicLog, LogicGuide])

    else:
        from support import SupportSC

        ModuleOhli24 = SupportSC.load_module_P(P, 'mod_ohli24').LogicOhli24
        ModuleAnilife = SupportSC.load_module_P(P, 'mod_anilife').LogicAnilife
        ModuleLinkkf = SupportSC.load_module_P(P, 'mod_linkkf').LogicLinkkf
        
        # Note: LogicLog/Guide are defined here, we can use them in prod too if needed, 
        # but focused on dev environment for now.
        P.set_module_list([ModuleOhli24, ModuleAnilife, ModuleLinkkf, LogicLog, LogicGuide])

except Exception as e:
    P.logger.error(f'Exception: {str(e)}')
    P.logger.error(traceback.format_exc())

