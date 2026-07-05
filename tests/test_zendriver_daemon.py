import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import zendriver_daemon


class _FakePage:
    def __init__(self):
        self.closed = False

    async def get(self, url):
        return None

    async def get_content(self):
        return "<html>" + ("x" * 12000) + "post-list</html>"

    async def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self):
        self.calls = []
        self.page = _FakePage()

    async def get(self, url="about:blank", new_tab=False, new_window=False):
        self.calls.append(
            {
                "url": url,
                "new_tab": new_tab,
                "new_window": new_window,
            }
        )
        if not new_tab:
            raise StopIteration
        return self.page


class ZendriverDaemonTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_browser = zendriver_daemon.browser
        self.original_ensure_browser = zendriver_daemon.ensure_browser

    async def asyncTearDown(self):
        zendriver_daemon.browser = self.original_browser
        zendriver_daemon.ensure_browser = self.original_ensure_browser

    async def test_fetch_uses_new_tab_when_reopening_after_closed_page(self):
        fake_browser = _FakeBrowser()
        zendriver_daemon.browser = fake_browser

        async def fake_ensure_browser():
            return fake_browser

        zendriver_daemon.ensure_browser = fake_ensure_browser

        result = await zendriver_daemon.fetch_with_browser("https://example.com", timeout=5)

        self.assertTrue(result["success"])
        self.assertEqual(fake_browser.calls[0]["url"], "about:blank")
        self.assertTrue(fake_browser.calls[0]["new_tab"])
        self.assertTrue(fake_browser.page.closed)


if __name__ == "__main__":
    unittest.main()
