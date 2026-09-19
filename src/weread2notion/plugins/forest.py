"""Forest focus-time plugin."""
from __future__ import annotations
import json
import os
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin


def _load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("sessions", "records", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


def _normalize(s):
    if not isinstance(s, dict):
        return None
    return {
        "id": str(s.get("id") or s.get("date") or s.get("start_time") or ""),
        "date": str(s.get("date") or s.get("start_time") or ""),
        "minutes": int(s.get("duration") or s.get("minutes") or 0),
        "tag": str(s.get("tag") or s.get("tree_type") or ""),
    }


class ForestPlugin(BasePlugin):
    """Forest 专注同步：把专注时间记录、种植记录 upsert 到 Notion。"""

    DB_NAME = "专注记录"
    TITLE_PROP = "标题"
    KEY_PROP = "SessionId"
    SCHEMA = {
        "标题": {"title": {}},
        "日期": {"date": {}},
        "分钟": {"number": {"format": "number"}},
        "标签": {"rich_text": {}},
        "SessionId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="forest",
        name="Forest",
        category=Category.PRODUCTIVITY,
        description="Forest 专注时间记录、种植记录自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#forest",
        icon=chr(0x1F333),
    )

    def is_configured(self):
        return bool(os.getenv("FOREST_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("FOREST_EXPORT", "")
        if not path or not Path(path).exists():
            return
        for s in _load(path):
            n = _normalize(s)
            if not n:
                continue
            sid = n["id"]
            raw = {
                "标题": "Focus " + (n["date"] or sid),
                "分钟": n["minutes"],
                "标签": n["tag"][:1900],
                "SessionId": sid,
            }
            if n["date"]:
                raw["日期"] = {"date": {"start": n["date"]}}
            yield sid, raw

    def _health_extra(self, ctx):
        path = os.getenv("FOREST_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
