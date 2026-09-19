"""Flomo plugin: parses Flomo note export (JSON) and writes to a Notion database."""
from __future__ import annotations
import json
import os
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin
from ..utils import strip_html


def _load_memos(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "memos" in data:
        return data["memos"]
    if isinstance(data, list):
        return data
    return []


def _normalize_tags(raw) -> list[str]:
    tags: list[str] = []
    for t in raw or []:
        if isinstance(t, str):
            tags.append(t)
        elif isinstance(t, dict) and t.get("name"):
            tags.append(str(t["name"]))
    return [t for t in tags if t]


class FlomoPlugin(BasePlugin):
    """Flomo 笔记同步：把 JSON 导出里的每条 memo upsert 到 Notion。

    继承 :class:`BasePlugin` 后只需声明库结构 + 实现 ``is_configured`` 与
    ``_items``（把每条 memo 转成 ``(Slug, raw)``），建库/同步/探测全部复用基类。
    """

    DB_NAME = "Flomo 笔记"
    TITLE_PROP = "标题"
    KEY_PROP = "Slug"
    SCHEMA = {
        "标题": {"title": {}},
        "内容": {"rich_text": {}},
        "标签": {"multi_select": {"options": []}},
        "时间": {"date": {}},
        "URL": {"url": {}},
        "Slug": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="flomo",
        name="Flomo",
        category=Category.NOTES,
        description="Flomo 笔记自动同步到 Notion（支持 JSON 导出）。",
        docs_url="https://github.com/wslh/NotionHub#flomo",
        icon="💡",
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("FLOMO_EXPORT"))

    def _items(self, ctx):
        path = Path(os.environ.get("FLOMO_EXPORT", ""))
        if not path.exists():
            return
        for memo in _load_memos(path):
            content = strip_html(memo.get("content") or "")[:1900]
            title = (memo.get("title") or content[:60] or "untitled").strip()
            slug = str(memo.get("slug") or memo.get("id") or content[:40])
            tags = _normalize_tags(memo.get("tags"))
            created = memo.get("created_at") or memo.get("created")
            raw = {
                "标题": title,
                "内容": content,
                "标签": {"multi_select": [{"name": t} for t in tags]},
                "Slug": slug,
            }
            if created:
                raw["时间"] = {"date": {"start": str(created)}}
            if memo.get("source") or memo.get("url"):
                raw["URL"] = memo.get("source") or memo.get("url")
            yield slug, raw
