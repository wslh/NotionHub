"""Tests for the 4 new plugin sync engines: rss, douban, telegram, netease."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from weread2notion.runner import run_plugin


class FakeNotion:
    def __init__(self):
        self.sources = {}
        self.schemas = {}
        self.titles = {}
        self.created = []
        self.patched = []
        self.existing = {}

    def ensure_database(self, name, title_prop, properties, icon=None):
        if name not in self.sources:
            self.sources[name] = f"src-{name}"
            self.schemas[name] = {k: (v or {}).get("type", "rich_text") for k, v in properties.items()}
            self.titles[name] = title_prop
        return self.sources[name]

    def find(self, database, key, value):
        return self.existing.get((database, key, value))

    def properties(self, database, raw):
        return {k: v for k, v in raw.items() if k in self.schemas.get(database, {})}

    def create(self, database, raw):
        page_id = f"page-{len(self.created) + 1}"
        self.created.append((database, raw))
        return page_id

    def request(self, path, method="GET", body=None):
        self.patched.append((path, method, body))
        return {}

    def upsert(self, database, key_name, key_value, raw, icon=None, cover=None,
               existing_id=None, existing_properties=None):
        existing = self.existing.get((database, key_name, key_value))
        if existing:
            self.patched.append(
                (f"pages/{existing['id']}", "PATCH", {"properties": self.properties(database, raw)})
            )
            return existing["id"]
        page_id = f"page-{len(self.created) + 1}"
        self.created.append((database, raw))
        return page_id


# ---------------------- RSS ----------------------

RSS2_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>My Blog</title>
<item><title>Post A</title><link>https://a</link><description>desc A</description><pubDate>Wed, 09 Sep 2026 12:00:00 +0000</pubDate><guid>aaa</guid></item>
<item><title>Post B</title><link>https://b</link><description>desc B</description><pubDate>Tue, 08 Sep 2026 10:00:00 +0000</pubDate><guid>bbb</guid></item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Feed</title>
<entry><id>tag:a,1</id><title>Atom A</title><link href="https://a"/><summary>atom desc</summary><updated>2026-09-09T12:00:00Z</updated></entry>
</feed>"""


def test_rss_parses_rss2(monkeypatch):
    from weread2notion.plugins.rss import RssPlugin, _fetch_feed
    with patch("weread2notion.plugins.rss.requests.get") as g:
        g.return_value.content = RSS2_XML.encode()
        g.return_value.raise_for_status = lambda: None
        feed = _fetch_feed("https://x.example/feed")
    assert feed["source"] == "My Blog"
    assert len(feed["items"]) == 2
    assert feed["items"][0]["title"] == "Post A"
    assert feed["items"][0]["guid"] == "aaa"
    assert "2026" in feed["items"][0]["date"]


def test_rss_parses_atom(monkeypatch):
    from weread2notion.plugins.rss import RssPlugin, _fetch_feed
    with patch("weread2notion.plugins.rss.requests.get") as g:
        g.return_value.content = ATOM_XML.encode()
        g.return_value.raise_for_status = lambda: None
        feed = _fetch_feed("https://x.example/atom")
    assert feed["source"] == "Atom Feed"
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Atom A"
    assert feed["items"][0]["link"] == "https://a"


def test_rss_sync_creates_entries(monkeypatch):
    from weread2notion.plugins.rss import RssPlugin
    monkeypatch.setenv("RSS_FEEDS", "https://x.example/feed")
    with patch("weread2notion.plugins.rss._fetch_feed") as g:
        g.return_value = {"source": "My Blog", "items": [
            {"title": "P1", "link": "https://1", "summary": "s", "date": "2026-09-09T12:00:00Z", "guid": "g1"}
        ]}
        notion = FakeNotion()
        result = run_plugin(RssPlugin(), notion, settings=object())
    assert result.synced == 1
    assert notion.created[0][0] == "RSS \u8ba2\u9605"
    raw = notion.created[0][1]
    assert raw["\u6807\u9898"] == "P1"
    assert raw["GUID"] == "g1"


def test_rss_updates_existing(monkeypatch):
    from weread2notion.plugins.rss import RssPlugin
    monkeypatch.setenv("RSS_FEEDS", "https://x.example/feed")
    with patch("weread2notion.plugins.rss._fetch_feed") as g:
        g.return_value = {"source": "S", "items": [
            {"title": "P1", "link": "https://1", "summary": "s", "date": "", "guid": "g1"}
        ]}
        notion = FakeNotion()
        notion.existing[("RSS \u8ba2\u9605", "GUID", "g1")] = {"id": "p1"}
        run_plugin(RssPlugin(), notion, settings=object())
    assert any(p[0] == "pages/p1" and p[1] == "PATCH" for p in notion.patched)


def test_rss_health_reports_feed_count(monkeypatch):
    from weread2notion.plugins.rss import RssPlugin
    monkeypatch.setenv("RSS_FEEDS", "https://a,https://b, https://c ,")
    p = RssPlugin()
    h = p.health(None)
    assert h["configured"] is True
    assert h["feeds"] == 3


def test_rss_handles_feed_failure_gracefully(monkeypatch):
    from weread2notion.plugins.rss import RssPlugin
    monkeypatch.setenv("RSS_FEEDS", "https://bad1,https://bad2")
    with patch("weread2notion.plugins.rss._fetch_feed", side_effect=Exception("boom")):
        notion = FakeNotion()
        result = run_plugin(RssPlugin(), notion, settings=object())
    assert result.synced == 0
    assert result.errors == 0
    assert notion.created == []


# ---------------------- Douban ----------------------

DOUBAN_HTML = """<html><head><title>\u4e09\u4f53 (\u8c46\u74e3)</title></head><body>
<div id="info">
<span class="pl">\u4f5c\u8005:</span> \u5218\u6148\u6e90<br>
<span class="pl">\u51fa\u7248\u793e:</span> \u8d5b\u9b3c\u6587\u5316<br>
<span class="pl">\u51fa\u7248\u5e74:</span> 2018-6<br>
<span class="pl">\u9875\u6570:</span> 380<br>
<span class="pl">\u5b9a\u4ef7:</span> 68.00\u5143<br>
<span class="pl">ISBN:</span> 9787559623266<br>
</div>
<strong class="ll rating_num">9.5</strong>
<a href="/tag/\u79d1\u5e7b">\u79d1\u5e7b</a>
<a href="/tag/\u5c0f\u8bf4">\u5c0f\u8bf4</a>
<div class="intro"><p>\u4e09\u4f53\u662f\u5218\u6148\u6e90\u7684\u4f5c\u54c1.</p></div>
</body></html>"""


def test_douban_parse_extracts_all_fields():
    from weread2notion.plugins.douban import _parse_book
    book = _parse_book(DOUBAN_HTML, "https://book.douban.com/subject/30384825/")
    assert book["title"] == "\u4e09\u4f53"
    assert book["author"] == "\u5218\u6148\u6e90"
    assert book["rating"] == 9.5
    assert book["press"] == "\u8d5b\u9b3c\u6587\u5316"
    assert book["pub_date"] == "2018-6"
    assert book["isbn"] == "9787559623266"
    assert book["pages"] == "380"
    assert book["price"] == "68.00\u5143"
    assert book["subject_id"] == "30384825"
    assert "\u4e09\u4f53" in book["summary"]
    assert "\u79d1\u5e7b" in book["tags"]
    assert "\u5c0f\u8bf4" in book["tags"]


def test_douban_sync_creates_book(monkeypatch):
    from weread2notion.plugins.douban import DoubanPlugin
    monkeypatch.setenv("DOUBAN_BOOK_URLS", "https://book.douban.com/subject/30384825/")
    with patch("weread2notion.plugins.douban._fetch_book") as g:
        g.return_value = {
            "subject_id": "30384825", "title": "Three Body", "author": "Liu",
            "rating": 9.5, "pub_date": "2018", "press": "Chongqing",
            "isbn": "123", "pages": "380", "price": "68",
            "summary": "x", "tags": ["sci-fi", "novel"], "url": "https://x",
        }
        notion = FakeNotion()
        result = run_plugin(DoubanPlugin(), notion, settings=object())
    assert result.synced == 1
    assert notion.created[0][0] == "\u8c46\u74e3\u4e66\u5355"
    raw = notion.created[0][1]
    assert raw["\u4e66\u540d"] == "Three Body"
    assert raw["SubjectId"] == "30384825"
    assert {t["name"] for t in raw["\u6807\u7b7e"]["multi_select"]} == {"sci-fi", "novel"}


def test_douban_updates_existing(monkeypatch):
    from weread2notion.plugins.douban import DoubanPlugin
    monkeypatch.setenv("DOUBAN_BOOK_URLS", "https://x/subject/1/")
    with patch("weread2notion.plugins.douban._fetch_book") as g:
        g.return_value = {"subject_id": "1", "title": "T", "author": "A", "rating": 8.0,
                          "pub_date": "", "press": "", "isbn": "", "pages": "", "price": "",
                          "summary": "", "tags": [], "url": "https://x"}
        notion = FakeNotion()
        notion.existing[("\u8c46\u74e3\u4e66\u5355", "SubjectId", "1")] = {"id": "p1"}
        run_plugin(DoubanPlugin(), notion, settings=object())
    assert any(p[0] == "pages/p1" and p[1] == "PATCH" for p in notion.patched)


def test_douban_health(monkeypatch):
    from weread2notion.plugins.douban import DoubanPlugin
    monkeypatch.setenv("DOUBAN_BOOK_URLS", "https://a, https://b")
    h = DoubanPlugin().health(None)
    assert h["configured"] is True
    assert h["books"] == 2


# ---------------------- Telegram ----------------------

def test_telegram_flatten_text():
    from weread2notion.plugins.telegram import _flatten_text
    assert _flatten_text("hello") == "hello"
    assert _flatten_text([{"text": "a"}, "b"]) == "ab"
    assert _flatten_text({"text": "x"}) == "x"
    assert _flatten_text([{"text": [{"type": "bold", "text": "B"}]}, " end"]) == "B end"
    assert _flatten_text(None) == ""


def test_telegram_load_handles_two_formats(tmp_path):
    from weread2notion.plugins.telegram import _load_messages
    p1 = tmp_path / "a.json"
    p1.write_text(json.dumps({"messages": [{"id": 1}, {"id": 2}]}), encoding="utf-8")
    assert [m["id"] for m in _load_messages(p1)] == [1, 2]
    p2 = tmp_path / "b.json"
    p2.write_text(json.dumps([{"id": 9}]), encoding="utf-8")
    assert [m["id"] for m in _load_messages(p2)] == [9]


def test_telegram_sync_creates(monkeypatch, tmp_path):
    from weread2notion.plugins.telegram import TelegramPlugin
    p = tmp_path / "tg.json"
    p.write_text(json.dumps({"messages": [
        {"id": 1, "date": "2026-01-01T10:00:00", "text": "hello world", "type": "message"},
        {"id": 2, "date": "2026-01-02T11:00:00",
         "text": [{"type": "bold", "text": "bold "}, "rest"], "type": "message"},
    ]}), encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_EXPORT", str(p))
    notion = FakeNotion()
    result = run_plugin(TelegramPlugin(), notion, settings=object())
    assert result.synced == 2
    assert notion.created[0][0] == "\u6536\u85cf\u7684\u6d88\u606f"
    titles = [r[1]["\u6807\u9898"] for r in notion.created]
    assert "hello world" in titles
    assert "bold rest" in titles


def test_telegram_returns_empty_when_file_missing(monkeypatch, tmp_path):
    from weread2notion.plugins.telegram import TelegramPlugin
    monkeypatch.setenv("TELEGRAM_EXPORT", str(tmp_path / "missing.json"))
    notion = FakeNotion()
    result = run_plugin(TelegramPlugin(), notion, settings=object())
    assert result.synced == 0
    assert notion.created == []


# ---------------------- NetEase ----------------------

def test_netease_load_handles_dict_and_list(tmp_path):
    from weread2notion.plugins.netease import _load_tracks
    p1 = tmp_path / "list.json"
    p1.write_text(json.dumps([{"name": "S1"}, {"name": "S2"}]), encoding="utf-8")
    assert len(_load_tracks(p1)) == 2
    p2 = tmp_path / "dict.json"
    p2.write_text(json.dumps({"tracks": [{"name": "A"}]}), encoding="utf-8")
    assert _load_tracks(p2)[0]["name"] == "A"


def test_netease_normalize_artists():
    from weread2notion.plugins.netease import _normalize
    out = _normalize({"id": 1, "name": "song", "artists": [{"name": "A"}, {"name": "B"}], "album": {"name": "X"}, "duration": 200000})
    assert out["artist"] == "A / B"
    assert out["album"] == "X"
    assert out["duration"] == 200


def test_netease_normalize_skips_no_name():
    from weread2notion.plugins.netease import _normalize
    assert _normalize({"id": 1}) is None
    assert _normalize({}) is None
    assert _normalize("not a dict") is None


def test_netease_sync_creates(monkeypatch, tmp_path):
    from weread2notion.plugins.netease import NeteasePlugin
    p = tmp_path / "ne.json"
    p.write_text(json.dumps({"tracks": [
        {"id": 1, "name": "Song1", "artists": "Solo", "album": "Alb1", "duration": 180000},
        {"id": 2, "name": "Song2", "artists": [{"name": "A1"}, {"name": "A2"}], "album": "Alb2", "duration": 240000},
    ]}), encoding="utf-8")
    monkeypatch.setenv("NETEASE_PLAYLIST", str(p))
    notion = FakeNotion()
    result = run_plugin(NeteasePlugin(), notion, settings=object())
    assert result.synced == 2
    assert notion.created[0][0] == "\u7f51\u6613\u4e91\u97f3\u4e50\u6b4c\u5355"
    raws = [r[1] for r in notion.created]
    assert raws[0]["\u6b4c\u624b"] == "Solo"
    assert raws[1]["\u6b4c\u624b"] == "A1 / A2"


def test_netease_updates_existing(monkeypatch, tmp_path):
    from weread2notion.plugins.netease import NeteasePlugin
    p = tmp_path / "ne.json"
    p.write_text(json.dumps([{"id": 9, "name": "Song", "artists": "A", "album": "X", "duration": 100}]), encoding="utf-8")
    monkeypatch.setenv("NETEASE_PLAYLIST", str(p))
    notion = FakeNotion()
    notion.existing[("\u7f51\u6613\u4e91\u97f3\u4e50\u6b4c\u5355", "SongId", "9")] = {"id": "p9"}
    run_plugin(NeteasePlugin(), notion, settings=object())
    assert any(p[0] == "pages/p9" and p[1] == "PATCH" for p in notion.patched)