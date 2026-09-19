from __future__ import annotations

from pathlib import Path

from weread2notion.config import ConfigError, Settings, redact_secret
from weread2notion.export import export_books
from weread2notion.status import workspace_status
from weread2notion.sync import Synchronizer


class FakeNotion:
    def __init__(self):
        self.sources = {"书架", "阅读快照", "设置"}
        self.schemas = {}
        self.titles = {"书架": "书名"}
        self.rows = {
            "书架": [
                {
                    "id": "p1",
                    "properties": {
                        "BookId": {"title": [{"plain_text": "b1"}]},
                        "书名": {"title": [{"plain_text": "测试书"}]},
                    },
                }
            ],
            "阅读快照": [
                {
                    "id": "s1",
                    "properties": {
                        "日期": {"date": {"start": "2026-09-09"}},
                        "书名": {"title": [{"plain_text": "测试书"}]},
                        "累计阅读时长（分钟）": {"number": 30},
                        "当日新增阅读时长（分钟）": {"number": 10},
                        "阅读进度": {"number": 0.5},
                    },
                }
            ],
        }

    def query_all(self, database, filter=None):
        return self.rows.get(database, [])

    def book_index(self):
        return {
            "b1": {"page_id": "p1", "sync_version": 8},
            "b2": {"page_id": "p2", "sync_version": 7},  # stale
        }

    def plain_property(self, prop):
        if not prop:
            return None
        for key in ("title", "rich_text"):
            if key in prop and isinstance(prop[key], list) and prop[key]:
                return prop[key][0].get("plain_text")
        return prop.get("number")


class FakeWeRead:
    def shelf(self):
        return {"books": [{"bookId": "b1", "sort": "1", "kind": "book"}]}

    def notebooks(self):
        return [], {}

    def book_bundle(self, book_id):
        return {"info": {"title": book_id}, "chapters": []}

    def reading_days(self, start_year):
        return [], {}


def test_redact_secret_masks_middle():
    masked = redact_secret("ntn_abcdefghijklmnopqrstuvwxyz123456")
    assert "****" in masked
    assert masked.startswith("ntn_")
    assert "abcdefghijklmnopqrstuvwxyz123456" not in masked


def test_settings_rejects_bad_token(monkeypatch):
    monkeypatch.setenv("WEREAD_API_KEY", "k")
    monkeypatch.setenv("NOTION_TOKEN", "invalid-token")
    monkeypatch.setenv("NOTION_PAGE", "https://notion.so/abc")
    try:
        Settings.from_env()
    except ConfigError as exc:
        assert "NOTION_TOKEN" in str(exc)
        return
    raise AssertionError("应拒绝非法 NOTION_TOKEN")


def test_export_books_writes_csv(tmp_path):
    notion = FakeNotion()
    out = export_books(notion, "csv", tmp_path / "books.csv")
    text = out.read_text(encoding="utf-8-sig")
    assert "测试书" in text
    assert "书名" in text


def test_status_reports_stale_books():
    status = workspace_status(FakeWeRead(), FakeNotion())
    assert status["stale_books"] >= 1
    assert status["books"] == 2
    assert "healthy" in status


def test_selective_sync_limits_changed_ids(tmp_path):
    notion = FakeNotion()
    # 让 existing 为空，避免删除逻辑；使用 fake weread 仅含 b1
    sync = Synchronizer(
        FakeWeRead(),
        notion,
        start_year=2023,
        checkpoint_file=tmp_path / "cp.json",
        only_books={"b1"},
    )
    plan = sync.plan()
    selected = sync._select_entries(plan["entries"])
    assert {e["bookId"] for e in selected} == {"b1"}


def test_checkpoint_marks_and_loads(tmp_path):
    cp = tmp_path / "cp.json"
    sync = Synchronizer(FakeWeRead(), FakeNotion(), checkpoint_file=cp)
    sync._mark_done("b1")
    assert "b1" in sync._load_checkpoint()
