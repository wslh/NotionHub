"""Douyin (TikTok China) collection plugin."""
from __future__ import annotations
import json
import os
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin


def _load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("videos", "awemes", "favorites", "items", "data"):
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
    title = str(v.get("title") or v.get("desc") or v.get("share_title") or "").strip()
    return {
        "id": str(v.get("aweme_id") or v.get("id") or v.get("video_id") or title),
        "title": title,
        "author": str(v.get("author") or v.get("nickname") or ""),
        "url": str(v.get("share_url") or v.get("url") or v.get("video_url") or ""),
    }


class DouyinPlugin(BasePlugin):
    """抖音收藏同步：把发布、收藏、点赞的视频和图集 upsert 到 Notion。"""

    DB_NAME = "抖音收藏"
    TITLE_PROP = "标题"
    KEY_PROP = "VideoId"
    SCHEMA = {
        "标题": {"title": {}},
        "作者": {"rich_text": {}},
        "链接": {"url": {}},
        "VideoId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="douyin",
        name="抖音",
        category=Category.MEDIA,
        description="抖音发布、收藏、点赞视频和图集自动同步到 Notion，可按需开启大文件上传。",
        docs_url="https://github.com/wslh/NotionHub#douyin",
        icon=chr(0x1F4AC),
    )

    def is_configured(self):
        return bool(os.getenv("DOUYIN_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("DOUYIN_EXPORT", "")
        if not path or not Path(path).exists():
            return
        for v in _load(path):
            n = _normalize(v)
            if not n:
                continue
            vid = n["id"]
            raw = {
                "标题": n["title"][:1900] or "(no title)",
                "作者": n["author"][:1900],
                "链接": n["url"],
                "VideoId": vid,
            }
            yield vid, raw

    def _health_extra(self, ctx):
        path = os.getenv("DOUYIN_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
