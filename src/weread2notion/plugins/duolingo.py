"""Duolingo learning-records plugin."""
from __future__ import annotations
import json
import os
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin


def _load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("sessions", "events", "items", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


def _normalize(it):
    if not isinstance(it, dict):
        return None
    return {
        "id": str(it.get("id") or it.get("date") or it.get("timestamp") or ""),
        "date": str(it.get("date") or it.get("timestamp") or ""),
        "skill": str(it.get("skill") or it.get("type") or "practice"),
        "xp": int(it.get("xp") or it.get("experience") or 0),
        "language": str(it.get("language") or it.get("learning_language") or ""),
    }


class DuolingoPlugin(BasePlugin):
    """多邻国学习记录同步：把每条学习记录 upsert 到 Notion。"""

    DB_NAME = "多邻国记录"
    TITLE_PROP = "标题"
    KEY_PROP = "RecordId"
    SCHEMA = {
        "标题": {"title": {}},
        "语言": {"rich_text": {}},
        "练习类型": {"rich_text": {}},
        "经验值": {"number": {"format": "number"}},
        "日期": {"date": {}},
        "RecordId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="duolingo",
        name="多邻国",
        category=Category.LEARNING,
        description="多邻国学习记录自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#duolingo",
        icon=chr(0x1F426),
    )

    def is_configured(self):
        return bool(os.getenv("DUOLINGO_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("DUOLINGO_EXPORT", "")
        if not path or not Path(path).exists():
            return
        for it in _load(path):
            n = _normalize(it)
            if not n:
                continue
            rid = n["id"]
            raw = {
                "标题": "Duolingo " + (n["date"] or rid),
                "语言": n["language"][:1900],
                "练习类型": n["skill"][:1900],
                "经验值": n["xp"],
                "RecordId": rid,
            }
            if n["date"]:
                raw["日期"] = {"date": {"start": n["date"]}}
            yield rid, raw

    def _health_extra(self, ctx):
        path = os.getenv("DUOLINGO_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
