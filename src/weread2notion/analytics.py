"""阅读数据分析：在已有 Notion 数据上生成洞察，供 ``insights`` 命令与看板使用。

所有函数只读取、不写入，可安全重复调用。
"""

from __future__ import annotations

from datetime import date
from typing import Any


def reading_insights(notion) -> dict[str, Any]:
    """汇总阅读统计：总时长、连续阅读天数、Top 书目、日均等。"""
    snapshots = (
        notion.query_all("阅读快照") if "阅读快照" in notion.sources else []
    )
    minutes = 0.0
    day_set: set[str] = set()
    by_book: dict[str, float] = {}
    for row in snapshots:
        props = row.get("properties") or {}
        raw = notion.plain_property(props.get("累计阅读时长（分钟）")) or 0
        try:
            m = float(raw)
        except (TypeError, ValueError):
            m = 0.0
        minutes += m
        day = notion.plain_property(props.get("日期"))
        if isinstance(day, dict):
            day = day.get("start")
        if day:
            day_set.add(str(day).split("T")[0])
        book_id = notion.plain_property(props.get("BookId"))
        if book_id:
            by_book[str(book_id)] = by_book.get(str(book_id), 0.0) + m
    day_strings = {d for d in day_set if _is_date(d)}
    current, longest = _streaks(day_strings)
    top = sorted(by_book.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "total_minutes": minutes,
        "total_hours": round(minutes / 60, 1),
        "active_days": len(day_strings),
        "daily_average_minutes": round(minutes / len(day_strings), 1) if day_strings else 0,
        "current_streak_days": current,
        "longest_streak_days": longest,
        "top_books_minutes": top,
    }


def snapshot_diff(notion, book_id: str, day_a: str, day_b: str) -> dict[str, Any]:
    """计算某本书在两日之间的累计阅读时长增量。"""
    result: dict[str, Any] = {"book_id": book_id, "day_a": day_a, "day_b": day_b}
    for key, day in (("a", day_a), ("b", day_b)):
        row = notion.find("阅读快照", "SnapshotKey", _snapshot_key(book_id, day))
        minutes = 0.0
        if row:
            raw = notion.plain_property(
                (row.get("properties") or {}).get("累计阅读时长（分钟）")
            ) or 0
            try:
                minutes = float(raw)
            except (TypeError, ValueError):
                minutes = 0.0
        result[f"minutes_{key}"] = minutes
    result["delta_minutes"] = round(
        result["minutes_b"] - result["minutes_a"], 1
    )
    return result


def _snapshot_key(book_id: str, day: str) -> str:
    return f"{book_id}-{day}"


def _streaks(day_set: set[str]) -> tuple[int, int]:
    days = sorted(date.fromisoformat(d) for d in day_set)
    if not days:
        return 0, 0
    longest = 1
    run = 1
    for prev, cur in zip(days, days[1:]):
        if (cur - prev).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    current = 0
    cursor = date.today()
    while cursor.isoformat() in day_set:
        current += 1
        cursor = date.fromordinal(cursor.toordinal() - 1)
    return current, longest


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False
