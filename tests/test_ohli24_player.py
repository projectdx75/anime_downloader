import json
import sys
import unittest
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ohli24_player import extract_player_url


class PlayerUrlTests(unittest.TestCase):
    episode = "https://ani.ohli24.com/e/episode"
    player = "https://cdndania.com/video/abc?t=123.signature&lang=ko"

    def page(self):
        return json.dumps({"props": {"playing": {"body": {"url": self.player}}}})

    def test_script_json_before_iframe_rendering(self):
        text = '<iframe src="https://ads.example/ad"></iframe>'
        text += '<script data-page="app" type="application/json">' + self.page().replace('/', r'\/') + '</script>'
        self.assertEqual(extract_player_url(text, self.episode), self.player)

    def test_inertia_attribute(self):
        text = '<div data-page="' + escape(self.page(), quote=True) + '"></div>'
        self.assertEqual(extract_player_url(text, self.episode), self.player)

    def test_legacy_and_lazy_iframe(self):
        for attr in ('src', 'data-src'):
            with self.subTest(attr=attr):
                text = '<div class="mcpalyer"><iframe ' + attr + '="//cdndania.com/video/abc?t=1&amp;x=2"></iframe></div>'
                self.assertEqual(extract_player_url(text, self.episode), 'https://cdndania.com/video/abc?t=1&x=2')

    def test_invalid_json_falls_back(self):
        text = '<script data-page="app">broken</script><iframe src="https://cdndania.com/video/abc"></iframe>'
        self.assertEqual(extract_player_url(text, self.episode), 'https://cdndania.com/video/abc')

    def test_missing_player_does_not_select_ad(self):
        self.assertIsNone(extract_player_url('<iframe src="https://ads.example/ad"></iframe>', self.episode))

    def test_reject_non_http_player(self):
        text = '<script data-page="app">' + self.page().replace(self.player, 'javascript:alert(1)') + '</script>'
        self.assertIsNone(extract_player_url(text, self.episode))


if __name__ == '__main__':
    unittest.main()
