import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from weread2notion.plugin import (
    Category,
    Plugin,
    PluginContext,
    PluginMeta,
    SyncResult,
)
from weread2notion.registry import PluginRegistry, build_default_registry
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


class _Stub:
    meta = PluginMeta(id="stub", name="Stub", category=Category.OTHER, description="d")
    def is_configured(self): return True
    def setup(self, ctx): pass
    def discover(self, ctx): return []
    def sync(self, ctx): return SyncResult(plugin_id="stub", synced=1)
    def health(self, ctx): return {"configured": True}


def test_category_values_are_chinese():
    assert Category.READING.value == "\u9605\u8bfb"
    assert Category.NOTES.value == "\u7b14\u8bb0"
    assert Category.PRODUCTIVITY.value == "\u6548\u7387"


def test_plugin_protocol_recognises_conforming():
    assert isinstance(_Stub(), Plugin)


def test_registry_register_get_contains_len():
    r = PluginRegistry()
    r.register(_Stub())
    assert "stub" in r
    assert len(r) == 1
    assert r.get("stub").meta.id == "stub"
    assert list(r) == [r.get("stub")]


def test_registry_rejects_duplicate_and_invalid():
    r = PluginRegistry([_Stub()])
    with pytest.raises(ValueError):
        r.register(_Stub())
    with pytest.raises(TypeError):
        r.register(object())  # type: ignore[arg-type]


def test_registry_by_category_and_summary():
    r = PluginRegistry([_Stub()])
    assert r.by_category(Category.OTHER) == [r.get("stub")]
    s = r.summary()
    assert s[0]["id"] == "stub"
    assert s[0]["category"] == "\u5176\u4ed6"


def test_build_default_registry_has_three_plugins():
    r = build_default_registry()
    ids = [p.meta.id for p in r]
    assert ids[:3] == ["weread", "flomo", "github"]
    assert "rss" in ids and "douban" in ids


def test_run_plugin_skips_when_unconfigured(monkeypatch):
    monkeypatch.delenv("FLOMO_EXPORT", raising=False)
    from weread2notion.plugins.flomo import FlomoPlugin
    result = run_plugin(FlomoPlugin(), notion=None, settings=object())
    assert result.skipped == 1
    assert result.extra["reason"] == "not_configured"


def test_flomo_parses_json_and_upserts(monkeypatch, tmp_path):
    f = tmp_path / "flomo.json"
    f.write_text(json.dumps({
        "memos": [
            {"content": "hello <b>world</b>", "tags": [{"name": "t1"}, "t2"], "created_at": "2025-01-01T10:00:00Z", "slug": "s1"},
        ]
    }), encoding="utf-8")
    monkeypatch.setenv("FLOMO_EXPORT", str(f))
    from weread2notion.plugins.flomo import FlomoPlugin
    notion = FakeNotion()
    result = run_plugin(FlomoPlugin(), notion, settings=object())
    assert result.synced == 1
    assert notion.created and notion.created[0][0] == "Flomo \u7b14\u8bb0"
    raw = notion.created[0][1]
    assert "hello world" in raw["\u5185\u5bb9"]
    assert {t["name"] for t in raw["\u6807\u7b7e"]["multi_select"]} == {"t1", "t2"}


def test_flomo_updates_existing(monkeypatch, tmp_path):
    f = tmp_path / "flomo.json"
    f.write_text(json.dumps([{"content": "x", "slug": "abc", "created_at": "2025-01-01"}]), encoding="utf-8")
    monkeypatch.setenv("FLOMO_EXPORT", str(f))
    from weread2notion.plugins.flomo import FlomoPlugin
    notion = FakeNotion()
    notion.existing[("Flomo \u7b14\u8bb0", "Slug", "abc")] = {"id": "p1"}
    result = run_plugin(FlomoPlugin(), notion, settings=object())
    assert result.synced == 1
    assert any(p[0] == "pages/p1" and p[1] == "PATCH" for p in notion.patched)


def test_github_upsert_creates_and_updates(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "t")
    from weread2notion.plugins.github import GithubPlugin, _fetch_stars
    repo = {"full_name": "u/r", "description": "d", "html_url": "https://x", "language": "Python", "stargazers_count": 10, "topics": ["ai"], "pushed_at": "2025-01-01T00:00:00Z"}
    with patch("weread2notion.plugins.github._fetch_stars", return_value=[repo]):
        notion = FakeNotion()
        result = run_plugin(GithubPlugin(), notion, settings=object())
        assert result.synced == 1
        assert notion.created[0][0] == "GitHub Stars"
        # update path
        notion.existing[("GitHub Stars", "\u4ed3\u5e93", "u/r")] = {"id": "pg"}
        result = run_plugin(GithubPlugin(), notion, settings=object())
        assert result.synced == 1
        assert any(p[0] == "pages/pg" and p[1] == "PATCH" for p in notion.patched)


def test_ensure_database_creates_and_reuses(monkeypatch):
    from weread2notion.notion import NotionWorkspace
    n = NotionWorkspace.__new__(NotionWorkspace)
    n.sources, n.schemas, n.titles = {}, {}, {}
    n.page_id = "page"
    calls = []
    def fake_request(path, method="GET", body=None):
        calls.append((path, method, body))
        return {"id": "db1", "data_sources": [{"id": "src1"}]}
    n.request = fake_request
    sid1 = n.ensure_database("X", "T", {"T": {"title": {}}, "N": {"number": {}}})
    assert sid1 == "src1" and "X" in n.sources
    sid2 = n.ensure_database("X", "T", {"T": {"title": {}}})
    assert sid2 == sid1 and len(calls) == 1





def test_new_plugins_registered():
    r = build_default_registry()
    ids = [p.meta.id for p in r]
    for pid in ('telegram', 'netease', 'rss', 'douban'):
        assert pid in ids, f'{pid} not in {ids}'


def test_telegram_unconfigured_when_no_env(monkeypatch):
    monkeypatch.delenv('TELEGRAM_EXPORT', raising=False)
    from weread2notion.plugins.telegram import TelegramPlugin
    p = TelegramPlugin()
    assert p.is_configured() is False
    h = p.health(None)
    assert h['configured'] is False
    assert h['exists'] is False


def test_netease_unconfigured_when_no_env(monkeypatch):
    monkeypatch.delenv('NETEASE_PLAYLIST', raising=False)
    from weread2notion.plugins.netease import NeteasePlugin
    p = NeteasePlugin()
    assert p.is_configured() is False
    h = p.health(None)
    assert h['configured'] is False
    assert h['exists'] is False


def test_rss_unconfigured_when_no_env(monkeypatch):
    monkeypatch.delenv('RSS_FEEDS', raising=False)
    from weread2notion.plugins.rss import RssPlugin
    assert RssPlugin().is_configured() is False


def test_douban_unconfigured_when_no_env(monkeypatch):
    monkeypatch.delenv('DOUBAN_BOOK_URLS', raising=False)
    from weread2notion.plugins.douban import DoubanPlugin
    assert DoubanPlugin().is_configured() is False


def test_registry_raises_keyerror_for_unknown_id():
    r = build_default_registry()
    import pytest
    with pytest.raises(KeyError):
        r.get('nonexistent')
