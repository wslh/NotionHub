"""Synchronizer 端到端编排与状态逻辑的专项测试。

既有 ``test_sync.py`` 已覆盖各 ``sync_*`` 方法的单点行为，本文件聚焦此前未覆盖的
「编排胶水」与「有状态逻辑」：

* ``run()`` 端到端：变更检测（新书的 book / 旧 sync_version / 无变化跳过）、
  移除书籍入回收站、``reading_days`` 失败降级、选择性同步、全量重建备份。
* ``_select_entries`` 按 ``only_books`` / ``only_tags`` 过滤。
* 检查点 ``_load_checkpoint`` / ``_mark_done`` / ``clear_checkpoint`` 往返与容错。
* ``validate_full_rebuild`` 通过 / 失败两条路径。
* ``dry_run`` 提前返回且零写入。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weread2notion.sync import DATA_DATABASES, Synchronizer


class FakeNotion:
    """最小可运行的 Notion 替身，记录所有写入调用。"""

    def __init__(self):
        # run() 通过这些库名做存在性判断与全量重建校验。
        self.sources = {
            "书架",
            "笔记",
            "划线",
            "日",
            "周",
            "月",
            "年",
            "分类",
            "作者",
            "阅读记录",
            "阅读记录1",
            "阅读记录2",
            "阅读快照",
            "设置",
        }
        self.titles = {
            "书架": "书名",
            "日": "标题",
            "周": "标题",
            "月": "标题",
            "年": "标题",
            "分类": "名称",
            "作者": "姓名",
            "阅读快照": "快照",
            "阅读记录": "标题",
            "阅读记录1": "标题",
            "阅读记录2": "标题",
            "设置": "名称",
        }
        # delete_removed_books 仅当 书籍 属性为 relation 时才归档关联行。
        self.schemas = {
            "笔记": {"书籍": "relation"},
            "划线": {"书籍": "relation"},
        }
        self.rows: list[tuple] = []  # ("upsert"|"create"|"content", ...)
        self.requests: list = []
        self.archived: list = []
        self.backups: list = []
        self.queries: list = []
        self.ai_intros: list = []
        self._book_index: dict = {}
        self._rows_by_db: dict = {}  # database -> list | Exception
        self._indexes: dict = {}

    def book_index(self):
        return dict(self._book_index)

    def query_all(self, database, filter_=None):
        self.queries.append((database, filter_))
        payload = self._rows_by_db.get(database)
        if isinstance(payload, Exception):
            raise payload
        return payload or []

    def backup_and_archive(self, backup_dir, databases):
        self.backups.append((backup_dir, list(databases)))
        return "backup-ok"

    def upsert(
        self,
        database,
        key_name,
        key_value,
        raw,
        icon=None,
        cover=None,
        existing_id=None,
        existing_properties=None,
    ):
        self.rows.append(("upsert", database, raw))
        return existing_id or f"{database}:{key_value}"

    def request(self, path, method="GET", body=None):
        self.requests.append((path, method, body))
        return {}

    def properties(self, database, raw):
        return raw

    def changed_properties(self, database, existing, desired):
        if not existing:
            return dict(desired)
        return {k: v for k, v in desired.items() if existing.get(k) != v}

    def row_index(self, database, key_name):
        return self._indexes.get(database, {})

    def plain_property(self, prop):
        if not prop:
            return None
        kind = prop.get("type")
        val = prop.get(kind)
        if kind in ("title", "rich_text"):
            return "".join(x.get("plain_text", "") for x in (val or []))
        return val

    def archive_rows(self, database, args):
        self.archived.append((database, args))
        return 1

    def create(self, database, raw, icon):
        self.rows.append(("create", database, raw))
        return f"{database}:created"

    def replace_generated_book_content(self, page_id, blocks):
        self.rows.append(("content", page_id, blocks))

    def write_ai_intro(self, page_id, summary):
        self.ai_intros.append((page_id, summary))


class FakeWeread:
    def __init__(
        self,
        shelf=None,
        notebooks=None,
        totals=None,
        days=None,
        stats=None,
        bundles=None,
        reading_days_raises=False,
    ):
        self._shelf = shelf if shelf is not None else {"books": []}
        self._notebooks = notebooks if notebooks is not None else []
        self._totals = totals if totals is not None else {"books": 0, "notes": 0}
        self._days = days if days is not None else []
        self._stats = stats if stats is not None else {}
        self._bundles = bundles or {}
        self.reading_days_raises = reading_days_raises
        self.bundle_calls: list = []

    def shelf(self):
        return self._shelf

    def notebooks(self):
        return self._notebooks, self._totals

    def reading_days(self, year):
        if self.reading_days_raises:
            raise RuntimeError("readdata 499")
        return self._days, self._stats

    def book_bundle(self, bid):
        self.bundle_calls.append(bid)
        return self._bundles.get(bid, {})


def _one_book_weread() -> FakeWeread:
    """构造一个含单本电子书的 weread，bundle 带最小可用进度信息。"""
    return FakeWeread(
        shelf={"books": [{"bookId": "b1", "title": "书1", "author": "作者甲", "category": "分类甲"}]},
        bundles={
            "b1": {
                "info": {"title": "书1", "author": "作者甲"},
                "progress": {"progress": 10, "readingTime": 100},
                "chapters": [],
            }
        },
    )


# --------------------------------------------------------------------------- #
# _select_entries
# --------------------------------------------------------------------------- #
def test_select_entries_filters_by_book():
    sync = Synchronizer(None, FakeNotion(), only_books={"b1"})
    entries = [{"bookId": "b1"}, {"bookId": "b2"}]
    assert sync._select_entries(entries) == [{"bookId": "b1"}]


def test_select_entries_filters_by_tag():
    sync = Synchronizer(None, FakeNotion(), only_tags={"x"})
    entries = [
        {"bookId": "b1", "labels": ["x"]},
        {"bookId": "b2", "tags": ["y"]},
    ]
    assert [e["bookId"] for e in sync._select_entries(entries)] == ["b1"]


def test_select_entries_returns_all_without_filter():
    sync = Synchronizer(None, FakeNotion())
    entries = [{"bookId": "b1"}, {"bookId": "b2"}]
    assert sync._select_entries(entries) == entries


# --------------------------------------------------------------------------- #
# 检查点往返与容错
# --------------------------------------------------------------------------- #
def test_checkpoint_roundtrip(tmp_path: Path):
    cp = tmp_path / "cp.json"
    sync = Synchronizer(None, FakeNotion(), checkpoint_file=cp)
    assert sync._load_checkpoint() == set()
    sync._mark_done("b1")
    assert cp.exists()
    assert sync._load_checkpoint() == {"b1"}
    sync.clear_checkpoint()
    assert not cp.exists()
    assert sync._load_checkpoint() == set()


def test_load_checkpoint_handles_corrupt_file(tmp_path: Path):
    cp = tmp_path / "cp.json"
    cp.write_text("{not valid json")
    sync = Synchronizer(None, FakeNotion(), checkpoint_file=cp)
    # 损坏即忽略，重新全量，不抛异常。
    assert sync._load_checkpoint() == set()


# --------------------------------------------------------------------------- #
# validate_full_rebuild
# --------------------------------------------------------------------------- #
def test_validate_full_rebuild_passes_when_all_queryable():
    sync = Synchronizer(None, FakeNotion())
    sync.validate_full_rebuild()  # 不应抛出


def test_validate_full_rebuild_raises_on_unreadable():
    notion = FakeNotion()
    # query_all("书架") 抛错，应被捕获并汇总进 RuntimeError。
    notion._rows_by_db = {"书架": RuntimeError("403 Forbidden")}
    sync = Synchronizer(None, notion)
    with pytest.raises(RuntimeError, match="全量重建前校验失败"):
        sync.validate_full_rebuild()
    # 报告里应点名出问题的库。
    with pytest.raises(RuntimeError, match="书架"):
        sync.validate_full_rebuild()


# --------------------------------------------------------------------------- #
# dry_run
# --------------------------------------------------------------------------- #
def test_run_dry_run_returns_early_without_writing():
    notion = FakeNotion()
    weread = FakeWeread(shelf={"books": [{"bookId": "b1", "title": "书1"}]})
    sync = Synchronizer(weread, notion, dry_run=True)
    result = sync.run()
    assert result["mode"] == "dry-run"
    assert result["shelf_entries"] == 1
    assert notion.rows == []
    assert notion.requests == []
    assert notion.backups == []


# --------------------------------------------------------------------------- #
# run() 变更检测
# --------------------------------------------------------------------------- #
def test_run_syncs_new_book_and_counts():
    notion = FakeNotion()
    sync = Synchronizer(_one_book_weread(), notion)
    counts = sync.run()
    assert counts["changed_books"] == 1
    assert counts["书架"] == 1
    book = next(r[2] for r in notion.rows if r[0] == "upsert" and r[1] == "书架")
    assert book["BookId"] == "b1"


def test_run_detects_stale_sync_version():
    notion = FakeNotion()
    notion._book_index = {"b1": {"page_id": "p1", "sync_version": 7, "sort": 0}}
    sync = Synchronizer(_one_book_weread(), notion)
    counts = sync.run()
    assert counts["changed_books"] == 1


def test_run_skips_unchanged_book():
    notion = FakeNotion()
    # sync_version 等于当前版本且无 sort 变化 → 视为无变化，跳过写入。
    notion._book_index = {"b1": {"page_id": "p1", "sync_version": 8, "sort": 0}}
    sync = Synchronizer(_one_book_weread(), notion)
    counts = sync.run()
    assert counts["changed_books"] == 0
    assert counts["skipped_books"] == 1
    assert all(not (r[0] == "upsert" and r[1] == "书架") for r in notion.rows)


def test_run_moves_removed_book_to_trash():
    notion = FakeNotion()
    notion._book_index = {"old": {"page_id": "p-old", "sync_version": 8, "sort": 0}}
    weread = FakeWeread(shelf={"books": []})  # 书架已空，old 不在其中
    sync = Synchronizer(weread, notion)
    sync.run()
    assert ("笔记", ("书籍", "p-old")) in notion.archived
    assert ("划线", ("书籍", "p-old")) in notion.archived
    assert notion.requests[-1] == ("pages/p-old", "PATCH", {"in_trash": True})
    assert sync.counts["删除书架"] == 1


def test_run_continues_when_reading_days_fails():
    notion = FakeNotion()
    weread = _one_book_weread()
    weread.reading_days_raises = True
    sync = Synchronizer(weread, notion)
    counts = sync.run()
    # 阅读时长统计失败被吞掉，书籍仍正常同步。
    assert counts["changed_books"] == 1
    assert counts["书架"] == 1
    assert "reading_seconds" in counts


def test_run_respects_only_books_selection():
    notion = FakeNotion()
    weread = FakeWeread(
        shelf={
            "books": [
                {"bookId": "b1", "title": "书1", "author": "a1"},
                {"bookId": "b2", "title": "书2", "author": "a2"},
            ]
        },
        bundles={
            "b1": {"info": {"title": "书1", "author": "a1"}, "progress": {"progress": 10}, "chapters": []},
            "b2": {"info": {"title": "书2", "author": "a2"}, "progress": {"progress": 10}, "chapters": []},
        },
    )
    sync = Synchronizer(weread, notion, only_books={"b1"})
    counts = sync.run()
    assert counts["changed_books"] == 1  # 仅 b1
    book_ids = [r[2]["BookId"] for r in notion.rows if r[0] == "upsert" and r[1] == "书架"]
    assert book_ids == ["b1"]


def test_run_full_rebuild_backs_up_and_resets(tmp_path: Path):
    notion = FakeNotion()
    weread = _one_book_weread()
    cp = tmp_path / "cp.json"
    sync = Synchronizer(weread, notion, checkpoint_file=cp)
    counts = sync.run(full=True)
    # 校验 + 备份都被触发，且覆盖全部数据数据库。
    assert len(notion.backups) == 1
    assert set(DATA_DATABASES).issubset(set(notion.backups[0][1]))
    assert counts["backup"] == "backup-ok"
    assert counts["archived"] == 0  # 无既有数据行
    # 全量重建结束清理检查点。
    assert sync._load_checkpoint() == set()


def test_run_full_rebuild_aborts_when_validation_fails(tmp_path: Path):
    notion = FakeNotion()
    notion._rows_by_db = {"书架": RuntimeError("403")}
    weread = _one_book_weread()
    sync = Synchronizer(weread, notion, checkpoint_file=tmp_path / "cp.json")
    with pytest.raises(RuntimeError, match="全量重建前校验失败"):
        sync.run(full=True)
    # 校验失败不应进入破坏性备份。
    assert notion.backups == []
