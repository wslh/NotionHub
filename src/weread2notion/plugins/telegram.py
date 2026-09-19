"""Telegram Saved Messages plugin for NotionHub.

Imports messages from a Telegram Desktop JSON export. Set TELEGRAM_EXPORT
to the path of a result.json file. Each message is written to the Notion
"收藏的消息" database.
Text entities (bold/italic/links) are flattened to plain text.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin


def _flatten_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ''.join(_flatten_text(c) for c in value)
    if isinstance(value, dict):
        return _flatten_text(value.get('text') or '')
    return ''


def _load_messages(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(data, dict):
        msgs = data.get('messages')
        if isinstance(msgs, list):
            return msgs
    if isinstance(data, list):
        return data
    return []


def _normalize(msg):
    text = _flatten_text(msg.get('text') or '')
    return {
        'id': str(msg.get('id') or ''),
        'date': str(msg.get('date') or ''),
        'text': text[:1900],
        'forwarded_from': (msg.get('forwarded_from') or '')
        if isinstance(msg.get('forwarded_from'), str) else '',
        'type': str(msg.get('type') or 'message'),
    }


class TelegramPlugin(BasePlugin):
    """Telegram 收藏同步：把桌面端 JSON 导出里的每条消息 upsert 到 Notion。"""

    DB_NAME = "收藏的消息"
    TITLE_PROP = "标题"
    KEY_PROP = "MessageId"
    SCHEMA = {
        "标题": {"title": {}},
        "内容": {"rich_text": {}},
        "时间": {"date": {}},
        "转发自": {"rich_text": {}},
        "MessageId": {"rich_text": {}},
        "Type": {"select": {"options": []}},
    }

    meta = PluginMeta(
        id="telegram",
        name="Telegram Saved",
        category=Category.NOTES,
        description="Import Telegram Saved Messages from a Telegram Desktop JSON export. Set TELEGRAM_EXPORT to the result.json path.",
        docs_url="https://github.com/wslh/NotionHub#telegram",
        icon="💬",
    )

    def is_configured(self):
        return bool(os.getenv("TELEGRAM_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get('TELEGRAM_EXPORT', '')
        if not path or not Path(path).exists():
            return
        for msg in _load_messages(path):
            m = _normalize(msg)
            mid = m["id"]
            title = (m['text'][:60] or '(empty)').strip()
            raw = {
                "标题": title,
                "内容": m["text"],
                "MessageId": mid,
                "Type": {"select": {"name": m["type"][:80]}},
            }
            if m.get('date'):
                raw["时间"] = {"date": {"start": m["date"]}}
            if m.get('forwarded_from'):
                raw["转发自"] = m["forwarded_from"][:1900]
            yield mid, raw

    def _health_extra(self, ctx):
        path = os.environ.get("TELEGRAM_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
