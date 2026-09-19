"""Weibo plugin: syncs a user's Weibo posts to Notion via the mobile API.

Uses the public m.weibo.cn container endpoint (no official API key required).
Set ``WEIBO_UID`` to the numeric user id; optionally ``WEIBO_COOKIE`` to raise
rate-limit headroom. Docs: https://m.weibo.cn/
"""
from __future__ import annotations

import os
import re

from ..plugin import Category, CredentialSpec, CredentialType, PluginMeta
from .base import BasePlugin, http_get_json
from ..utils import strip_html


def _parse_date(text: str) -> str | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", text or "")
    if m:
        return m.group(1).replace(" ", "T") + "+08:00"
    return None


class WeiboPlugin(BasePlugin):
    DB_NAME = "微博"
    TITLE_PROP = "摘要"
    KEY_PROP = "WeiboId"
    SCHEMA = {
        "摘要": {"title": {}},
        "正文": {"rich_text": {}},
        "时间": {"date": {}},
        "转发": {"number": {"format": "number"}},
        "评论": {"number": {"format": "number"}},
        "赞": {"number": {"format": "number"}},
        "链接": {"url": {}},
        "WeiboId": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="weibo",
        name="微博",
        category=Category.OTHER,
        description="把指定微博 UID 的公开微博同步到 Notion（无需官方 API Key）。",
        docs_url="https://github.com/wslh/NotionHub#weibo",
        icon="🐦",
        credentials=(
            CredentialSpec(
                "WEIBO_UID", "微博 UID", CredentialType.API_KEY,
                "微博用户数字 ID（从 m.weibo.cn/u/<UID> 获取）。",
            ),
            CredentialSpec(
                "WEIBO_COOKIE", "微博 Cookie（可选）", CredentialType.COOKIE,
                "登录后复制 Cookie，可提升抓取稳定性。", required=False,
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("WEIBO_UID"))

    def _items(self, ctx):
        uid = os.environ["WEIBO_UID"]
        cookie = (os.getenv("WEIBO_COOKIE") or "").strip()
        headers = {"Cookie": cookie} if cookie else {}
        for page in range(1, 6):
            data = http_get_json(
                "https://m.weibo.cn/api/container/getIndex",
                headers=headers,
                params={"type": "uid", "value": uid, "page": page},
            )
            cards = (data.get("data") or {}).get("cards") or []
            for card in cards:
                for c in card.get("card_group", [card]):
                    mblog = c.get("mblog")
                    if not mblog:
                        continue
                    bid = mblog.get("bid") or str(mblog.get("id"))
                    wid = str(mblog.get("id"))
                    text = strip_html(mblog.get("text", ""))
                    raw = {
                        "摘要": (text[:50] or wid)[:50],
                        "正文": text[:1900],
                        "转发": int(mblog.get("reposts_count") or 0),
                        "评论": int(mblog.get("comments_count") or 0),
                        "赞": int(mblog.get("attitudes_count") or 0),
                        "链接": f"https://m.weibo.cn/detail/{bid}",
                        "WeiboId": wid,
                    }
                    d = _parse_date(mblog.get("created_at", ""))
                    if d:
                        raw["时间"] = {"date": {"start": d}}
                    yield wid, raw
