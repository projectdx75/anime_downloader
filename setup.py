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
            'uri': 'manual',
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

DEFINE_DEV = True

P = create_plugin_instance(setting)
try:
    if DEFINE_DEV:
        from .mod_ohli24 import LogicOhli24
        from .mod_anilife import LogicAniLife
        from .mod_linkkf import LogicLinkkf

    else:
        from support import SupportSC

        ModuleOhli24 = SupportSC.load_module_P(P, 'mod_ohli24').LogicOhli24
        ModuleAnilife = SupportSC.load_module_P(P, 'mod_anilife').LogicAnilife
        ModuleLinkkf = SupportSC.load_module_P(P, 'mod_linkkf').LogicLinkkf
        P.set_module_list([ModuleOhli24, ModuleAnilife, ModuleLinkkf])

    P.set_module_list([LogicOhli24, LogicAniLife, LogicLinkkf])

except Exception as e:
    P.logger.error(f'Exception:{str(e)}')
    P.logger.error(traceback.format_exc())
