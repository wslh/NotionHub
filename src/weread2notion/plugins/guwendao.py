"""Guwendao (古文岛) plugin: import a local reading export into Notion.

古文岛没有公开 API，自托管采用本地导出 JSON 入库。导出结构通常为文章列表，
含 id / 标题 / 作者 / 朝代 / 正文 / 时间。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..plugin import Category, CredentialSpec, CredentialType, PluginMeta
from .base import BasePlugin


class GuwendaoPlugin(BasePlugin):
    DB_NAME = "古文岛"
    TITLE_PROP = "篇名"
    KEY_PROP = "Id"
    SCHEMA = {
        "篇名": {"title": {}},
        "作者": {"rich_text": {}},
        "朝代": {"rich_text": {}},
        "正文": {"rich_text": {}},
        "时间": {"date": {}},
        "链接": {"url": {}},
        "Id": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="guwendao",
        name="古文岛",
        category=Category.READING,
        description="把古文岛阅读导出的本地 JSON 同步到 Notion（无公开 API，推荐导出后入库）。",
        docs_url="https://github.com/wslh/NotionHub#guwendao",
        icon="📜",
        credentials=(
            CredentialSpec(
                "GUWENDAO_EXPORT", "古文岛导出文件路径", CredentialType.FILE,
                "导出 JSON 的绝对路径。", secret=False,
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("GUWENDAO_EXPORT"))

    def _load(self) -> list[dict]:
        path = Path(os.environ["GUWENDAO_EXPORT"])
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("articles") or data.get("data") or data.get("list") or []
        return data if isinstance(data, list) else []

    def _items(self, ctx):
        for art in self._load():
            aid = str(art.get("id") or art.get("url") or "")
            if not aid:
                continue
            raw = {
                "篇名": (art.get("title") or "untitled")[:1900],
                "作者": (art.get("author") or "")[:1900],
                "朝代": (art.get("dynasty") or "")[:1900],
                "正文": (art.get("content") or art.get("body") or "")[:1900],
                "链接": art.get("url") or "",
                "Id": aid,
            }
            ts = art.get("time") or art.get("created_at") or art.get("date")
            if ts:
                raw["时间"] = {"date": {"start": str(ts)}}
            yield aid, raw
