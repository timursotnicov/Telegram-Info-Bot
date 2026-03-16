"""Tests for savebot.services.link_preview."""
import pytest
from savebot.services.link_preview import extract_url, MetaParser


# ── extract_url ───────────────────────────────────────────


def test_extract_url_from_text():
    text = "Check this out https://example.com/page for more info"
    assert extract_url(text) == "https://example.com/page"


def test_extract_url_no_url():
    text = "Just plain text with no links"
    assert extract_url(text) is None


def test_extract_url_multiple_urls():
    text = "First https://first.com then https://second.com"
    assert extract_url(text) == "https://first.com"


def test_extract_url_http():
    text = "Old style http://insecure.com/path"
    assert extract_url(text) == "http://insecure.com/path"


# ── MetaParser ────────────────────────────────────────────


def test_meta_parser_title_tag():
    html = "<html><head><title>My Page Title</title></head><body></body></html>"
    parser = MetaParser()
    parser.feed(html)
    assert parser.title == "My Page Title"


def test_meta_parser_og_title_overrides():
    html = """<html><head>
        <title>Fallback Title</title>
        <meta property="og:title" content="OG Title" />
    </head><body></body></html>"""
    parser = MetaParser()
    parser.feed(html)
    # og:title takes priority since it's set after <title> data
    assert parser.title == "OG Title"


def test_meta_parser_description():
    html = """<html><head>
        <meta name="description" content="A nice description" />
    </head><body></body></html>"""
    parser = MetaParser()
    parser.feed(html)
    assert parser.description == "A nice description"


def test_meta_parser_og_description():
    html = """<html><head>
        <meta property="og:description" content="OG description here" />
    </head><body></body></html>"""
    parser = MetaParser()
    parser.feed(html)
    assert parser.description == "OG description here"


def test_meta_parser_empty_html():
    parser = MetaParser()
    parser.feed("<html><head></head><body></body></html>")
    assert parser.title == ""
    assert parser.description == ""


def test_meta_parser_description_first_wins():
    html = """<html><head>
        <meta name="description" content="First description" />
        <meta property="og:description" content="Second description" />
    </head><body></body></html>"""
    parser = MetaParser()
    parser.feed(html)
    # First description set wins (the code checks `if not self.description`)
    assert parser.description == "First description"
