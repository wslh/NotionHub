"""运维状态：汇总工作区健康度、待修复项与版本信息，供 `status` 命令使用。"""

from __future__ import annotations

from typing import Any

from .repair import Repair
from .sync import SYNC_VERSION


def workspace_status(weread, notion, start_year: int = 2023) -> dict[str, Any]:
    """返回工作区健康状态：数据库清单、待修复项、当前同步版本。"""
    repair = Repair(weread, notion, start_year)
    issues = repair.check()
    book_index = notion.book_index()
    stale = issues.get("stale_book_count", 0)
    count_by_db: dict[str, int] = {}
    for name in notion.sources:
        try:
            count_by_db[name] = len(notion.query_all(name))
        except Exception:  # noqa: BLE001 - 统计失败不应阻断状态查询
            count_by_db[name] = -1
    return {
        "sync_version": SYNC_VERSION,
        "databases": sorted(notion.sources),
        "counts": count_by_db,
        "books": len(book_index),
        "issues": {k: v for k, v in issues.items() if k != "stale_books"},
        "stale_books": stale,
        "healthy": stale == 0
        and not any(
            k in issues
            for k in ("settings_missing", "settings_row_missing", "snapshots_db_missing")
        ),
    }
