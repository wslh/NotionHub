from __future__ import annotations

from pathlib import Path

from weread2notion.notion import NotionWorkspace
from weread2notion.repair import Repair
from weread2notion.sync import SYNC_VERSION


class FakeWeRead:
    def shelf(self):
        return {
            "books": [
                {"bookId": "book1", "sort": "100", "kind": "book"},
                {"bookId": "book2", "sort": "200", "kind": "book"},
            ]
        }

    def notebooks(self):
        return [], {}

    def book_bundle(self, book_id):
        return {"info": {"title": book_id}, "chapters": []}


class FakeNotion:
    def __init__(self):
        self.sources = {"书架", "笔记", "划线", "阅读快照", "设置"}
        self.schemas = {"笔记": {"书籍": "relation"}, "划线": {"书籍": "relation"}}
        self.titles = {"阅读快照": "名称"}
        self.rows = {
            "设置": [{"id": "s1", "properties": {}}],
            "书架": [
                {
                    "id": "page1",
                    "properties": {"BookId": {"title": [{"plain_text": "book1"}]}},
                    "page_id": "page1",
                    "sync_version": SYNC_VERSION,
                },
                {
                    "id": "page2",
                    "properties": {"BookId": {"title": [{"plain_text": "book2"}]}},
                    "page_id": "page2",
                    "sync_version": SYNC_VERSION - 1,  # stale
                },
            ],
            "笔记": [
                {"id": "n1", "properties": {"书籍": {"relation": [{"id": "page1"}]}}},
                {"id": "n2", "properties": {"书籍": {"relation": [{"id": "ghost"}]}}},
            ],
            "划线": [
                {"id": "h1", "properties": {"书籍": {"relation": [{"id": "page2"}]}}},
            ],
            "阅读快照": [
                {
                    "id": "snap1",
                    "properties": {
                        "日期": {"date": {"start": "2026-09-09"}},
                        "BookId": {"title": [{"plain_text": "book1"}]},
                    },
                },
            ],
        }
        self.requests: list[tuple] = []
        self.ensured_settings = False
        self.ensured_snapshots = False
        self.replaced: list[str] = []

    def query_all(self, database, filter=None):
        return self.rows.get(database, [])

    def book_index(self):
        result = {}
        for row in self.rows.get("书架", []):
            book_id = self.plain_property(row.get("properties", {}).get("BookId")) or row["page_id"]
            result[book_id] = {
                "page_id": row["page_id"],
                "sync_version": row.get("sync_version", 0),
            }
        return result

    def plain_property(self, prop):
        if not prop:
            return None
        for key in ("title", "rich_text"):
            if key in prop and isinstance(prop[key], list) and prop[key]:
                return prop[key][0].get("plain_text")
        return prop.get("number")

    def ensure_sync_settings(self, start_year):
        self.ensured_settings = True
        return {}

    def ensure_reading_snapshots(self):
        self.ensured_snapshots = True

    def replace_generated_book_content(self, page_id, blocks):
        self.replaced.append(page_id)

    def request(self, url, method, body):
        self.requests.append((url, method, body))

    def properties(self, database, data):
        return {"_raw": data}

    # 本 Fake 的 properties() 把整个 payload 包成 {"_raw": ...}，无法逐字段比对，
    # 因此保守返回全部字段（等价于改造前的整页覆盖）。
    def changed_properties(self, database, existing, desired):
        return desired

    def upsert(
        self,
        database,
        title_key,
        key,
        raw,
        icon,
        existing_id=None,
        existing_properties=None,
    ):
        return existing_id or f"new-{key}"


def test_repair_check_detects_issues():
    notion = FakeNotion()
    issues = Repair(FakeWeRead(), notion).check()

    assert issues["stale_books"] == ["book2"]
    assert issues["orphaned_rows"] == {"笔记": 1}
    assert issues["missing_today_snapshots"] == 1
    # 设置库存在且配置行存在，不应报缺失
    assert "settings_missing" not in issues
    assert "settings_row_missing" not in issues


def test_repair_fix_resolves_issues():
    notion = FakeNotion()
    report = Repair(FakeWeRead(), notion, apply=True).fix()

    # 过期正文被重新生成
    assert report["stale_books"] == 1
    assert "page2" in notion.replaced
    # 孤立笔记被归档
    assert report["orphaned_笔记"] == 1
    assert ("pages/n2", "PATCH", {"in_trash": True}) in notion.requests
    # 正文同步版本被刷新
    version_patch = [
        (u, b) for (u, m, b) in notion.requests if u == "pages/page2"
    ]
    assert any(b.get("properties", {}).get("_raw", {}).get("同步版本") == SYNC_VERSION for _, b in version_patch)
    # 当日快照已补齐
    assert report["missing_today_snapshots"] == "已补齐今日本书快照"


def test_repair_fix_requires_apply():
    notion = FakeNotion()
    repair = Repair(FakeWeRead(), notion, apply=False)
    repair.check()
    try:
        repair.fix()
    except RuntimeError:
        return
    raise AssertionError("fix 应在 apply=False 时抛出 RuntimeError")


def test_restore_from_backup_unarchives_pages(tmp_path):
    backup = tmp_path / "b.json"
    backup.write_text(
        '{"databases": {"书架": [{"id": "p1"}], "笔记": [{"id": "n1"}, {"id": "n2"}]}}',
        encoding="utf-8",
    )
    notion = NotionWorkspace.__new__(NotionWorkspace)
    notion.request = lambda url, method, body: requests_log.append((url, method, body))
    requests_log: list[tuple] = []
    restored = notion.restore_from_backup(Path(backup))
    assert restored == 3
    assert all(method == "PATCH" and body == {"in_trash": False} for _, method, body in requests_log)
