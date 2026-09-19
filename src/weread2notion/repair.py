"""数据修复：检测并修复微信读书 → Notion 同步过程中的数据不一致。

典型不一致包括：
- 设置库缺失/配置行丢失（模板被误删或损坏）
- 阅读快照库缺失
- 书籍页面的同步版本低于当前版本（正文未随模板升级而重新生成）
- 笔记/划线关联到的书籍页面已被移入回收站（孤立记录）
- 当前书架书目缺失当日的阅读快照

`check` 仅检测并打印问题（默认行为）；`fix` 在 ``apply=True`` 时执行修复。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .normalize import SHANGHAI
from .sync import SYNC_VERSION, Synchronizer


class Repair:
    """检测并修复 Notion 工作区内的同步数据不一致。"""

    def __init__(
        self,
        weread,
        notion,
        start_year: int = 2023,
        apply: bool = False,
    ):
        self.weread = weread
        self.notion = notion
        self.start_year = start_year
        self.apply = apply
        self.issues: dict[str, Any] = {}
        self._orphan_ids: dict[str, list[str]] = {}

    def check(self) -> dict[str, Any]:
        """只读检测数据不一致，返回问题描述。"""
        issues: dict[str, Any] = {}

        if "设置" not in self.notion.sources:
            issues["settings_missing"] = "设置数据库不存在"
        elif not self.notion.query_all("设置"):
            issues["settings_row_missing"] = "设置数据库缺少配置行"

        if "阅读快照" not in self.notion.sources:
            issues["snapshots_db_missing"] = "阅读快照数据库不存在"

        books = self.notion.book_index()
        stale = [
            book_id
            for book_id, book in books.items()
            if int(book.get("sync_version") or 0) < SYNC_VERSION
        ]
        if stale:
            issues["stale_books"] = stale
            issues["stale_book_count"] = len(stale)

        orphaned = self._orphan_rows(books)
        if orphaned:
            issues["orphaned_rows"] = {db: len(ids) for db, ids in orphaned.items()}
            self._orphan_ids = orphaned

        missing = self._missing_today_snapshots(books)
        if missing:
            issues["missing_today_snapshots"] = missing

        self.issues = issues
        return issues

    def _orphan_rows(self, books: dict[str, Any]) -> dict[str, list[str]]:
        """返回笔记/划线中关联到已删除书籍的孤立页面 id 列表。"""
        page_ids = {book["page_id"] for book in books.values()}
        result: dict[str, list[str]] = {}
        for database in ("笔记", "划线"):
            if database not in self.notion.sources:
                continue
            if self.notion.schemas.get(database, {}).get("书籍") != "relation":
                continue
            ids: list[str] = []
            for row in self.notion.query_all(database):
                relations = (
                    (row.get("properties") or {}).get("书籍", {}).get("relation") or []
                )
                linked = {item["id"] for item in relations}
                if linked and not (linked & page_ids):
                    ids.append(row["id"])
            if ids:
                result[database] = ids
        return result

    def _missing_today_snapshots(self, books: dict[str, Any]) -> int:
        """返回当前书架中缺少今日阅读快照的书目数量。"""
        if "阅读快照" not in self.notion.sources:
            return 0
        day_text = datetime.now(SHANGHAI).date().isoformat()
        present: set[str] = set()
        for row in self.notion.query_all(
            "阅读快照", {"property": "日期", "date": {"equals": day_text}}
        ):
            book_id = self.notion.plain_property(
                (row.get("properties") or {}).get("BookId")
            )
            if book_id:
                present.add(str(book_id))
        return len(set(books) - present)

    def fix(self) -> dict[str, Any]:
        """执行修复并返回修复报告。仅在 ``apply=True`` 时有效。"""
        issues = self.issues or self.check()
        if not self.apply:
            raise RuntimeError("repair.fix 需要在 apply=True 时调用")

        report: dict[str, Any] = {}

        if "settings_missing" in issues or "settings_row_missing" in issues:
            self.notion.ensure_sync_settings(self.start_year)
            report["settings"] = "已重建设置库与配置行"

        if "snapshots_db_missing" in issues:
            self.notion.ensure_reading_snapshots()
            report["snapshots_db"] = "已创建阅读快照库"

        stale = issues.get("stale_books", [])
        if stale:
            books_index = self.notion.book_index()
            fixed = 0
            for book_id in stale:
                page_id = (books_index.get(book_id) or {}).get("page_id")
                if not page_id:
                    continue
                bundle = self.weread.book_bundle(book_id)
                if not bundle:
                    continue
                self.notion.replace_generated_book_content(
                    page_id, Synchronizer.book_content_blocks(bundle)
                )
                self.notion.request(
                    f"pages/{page_id}",
                    "PATCH",
                    {"properties": self.notion.properties("书架", {"同步版本": SYNC_VERSION})},
                )
                fixed += 1
            report["stale_books"] = fixed

        for database, ids in self._orphan_ids.items():
            for page_id in ids:
                self.notion.request(f"pages/{page_id}", "PATCH", {"in_trash": True})
            report[f"orphaned_{database}"] = len(ids)

        if issues.get("missing_today_snapshots"):
            sync = Synchronizer(self.weread, self.notion, self.start_year)
            plan = sync.plan()
            entries = {entry["bookId"]: entry for entry in plan["entries"]}
            bundles = {bid: self.weread.book_bundle(bid) for bid in entries}
            sync.sync_daily_snapshots(entries, bundles, self.notion.book_index())
            report["missing_today_snapshots"] = "已补齐今日本书快照"

        return report
