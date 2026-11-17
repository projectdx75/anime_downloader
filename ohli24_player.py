"""Extract the episode player from current Inertia pages and legacy HTML."""

import json
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def extract_player_url(text, episode_url):
    soup = BeautifulSoup(text, "lxml")

    def normalize(value):
        if not isinstance(value, str) or not value.strip():
            return None
        url = urljoin(episode_url, value.strip())
        parsed = urlparse(url)
        return url if parsed.scheme in ("http", "https") and parsed.netloc else None

    # Inertia now supplies the player before Vue has rendered an iframe.
    for node in soup.select('script[data-page], [data-page]'):
        raw = node.get("data-page")
        if node.name == "script":
            raw = node.string or node.get_text()
        try:
            page = json.loads(raw or "")
            url = normalize(page["props"]["playing"]["body"]["url"])
            if url:
                return url
        except (ValueError, KeyError, TypeError):
            continue

    frames = soup.select('.mcpalyer iframe, .embed-responsive iframe')
    frames += [frame for frame in soup.find_all("iframe")
               if "cdndania" in (frame.get("src") or frame.get("data-src") or "")]
    for frame in frames:
        for attribute in ("src", "data-src"):
            url = normalize(frame.get(attribute))
            if url:
                return url
    return None
