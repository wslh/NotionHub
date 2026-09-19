"""Bilibili (B站) video collection plugin."""
from __future__ import annotations
import json
import os
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin


def _load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("videos", "favorites", "items", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


def _normalize(v):
    if not isinstance(v, dict):
        return None
    title = str(v.get("title") or "").strip()
    return {
        "id": str(v.get("id") or v.get("aid") or v.get("bvid") or title),
        "title": title,
        "author": str(v.get("author") or v.get("up_name") or v.get("uploader") or ""),
        "url": str(v.get("url") or v.get("link") or ("https://www.bilibili.com/video/" + str(v.get("bvid", "")))),
        "duration": int(v.get("duration") or 0),
    }


class BilibiliPlugin(BasePlugin):
    """B站收藏同步：把导出 JSON 里的每个视频 upsert 到 Notion。"""

    DB_NAME = "B站收藏"
    TITLE_PROP = "标题"
    KEY_PROP = "VideoId"
    SCHEMA = {
        "标题": {"title": {}},
        "UP主": {"rich_text": {}},
        "链接": {"url": {}},
        "时长(秒)": {"number": {"format": "number"}},
        "VideoId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="bilibili",
        name="B站",
        category=Category.MEDIA,
        description="哔哩哔哩体验账号、后台追番记录、历史记录自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#bilibili",
        icon=chr(0x1F4FA),
    )

    def is_configured(self):
        return bool(os.getenv("BILIBILI_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("BILIBILI_EXPORT", "")
        if not path or not Path(path).exists():
            return
        for v in _load(path):
            n = _normalize(v)
            if not n:
                continue
            vid = n["id"]
            raw = {
                "标题": n["title"][:1900] or "(no title)",
                "UP主": n["author"][:1900],
                "链接": n["url"],
                "时长(秒)": n["duration"],
                "VideoId": vid,
            }
            yield vid, raw

    def _health_extra(self, ctx):
        path = os.getenv("BILIBILI_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
