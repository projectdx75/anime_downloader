import unittest
from unittest.mock import patch

from lib import zendriver_daemon


class FakePage:
    def __init__(self, html):
        self.html = html
        self.closed = False
        self.urls = []

    async def get(self, url):
        self.urls.append(url)
        return self

    async def get_content(self):
        return self.html

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, page):
        self.page = page
        self.urls = []

    async def get(self, url):
        self.urls.append(url)
        return self.page


class ZendriverDaemonTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_closes_page_after_success(self):
        page = FakePage("<html>" + ("x" * 12000) + "</html>")
        browser = FakeBrowser(page)

        with patch.object(zendriver_daemon, "ensure_browser") as ensure_browser:
            zendriver_daemon.browser = browser
            ensure_browser.return_value = browser

            result = await zendriver_daemon.fetch_with_browser("https://example.com", timeout=1)

        self.assertTrue(result["success"])
        self.assertTrue(page.closed)


if __name__ == "__main__":
    unittest.main()
