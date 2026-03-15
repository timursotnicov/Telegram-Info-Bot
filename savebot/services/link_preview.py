"""Link preview / metadata extraction service."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser

import aiohttp

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s<>\"']+")


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            content = attrs_dict.get("content", "")
            if name == "description" or prop == "og:description":
                if not self.description:
                    self.description = content
            if prop == "og:title":
                self.title = content

    def handle_data(self, data):
        if self._in_title:
            self.title = data.strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


def extract_url(text: str) -> str | None:
    match = URL_REGEX.search(text)
    return match.group(0) if match else None


async def fetch_link_metadata(url: str) -> dict:
    """Fetch title and description from a URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=5),
                headers={"User-Agent": "Mozilla/5.0 (compatible; SaveBot/1.0)"},
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return {"title": "", "description": ""}
                # Only parse HTML
                ct = resp.headers.get("Content-Type", "")
                if "text/html" not in ct:
                    return {"title": url, "description": f"File: {ct}"}
                html = await resp.text(errors="replace")
                # Only parse first 50KB
                html = html[:50000]

        parser = MetaParser()
        parser.feed(html)
        return {
            "title": parser.title or "",
            "description": parser.description or "",
        }
    except Exception as e:
        logger.warning("Failed to fetch link metadata for %s: %s", url, e)
        return {"title": "", "description": ""}
