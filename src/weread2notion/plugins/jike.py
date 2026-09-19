"""Jike (即刻) plugin: imports a local export into Notion.

即刻官方 API 已不再稳定开放，自托管最稳妥的方式是先把动态导出为 JSON，
再交给本插件入库。仍保留 Cookie 字段作为「在线抓取」的可选说明。
"""
from __future__ import annotationsimport jsonimport osfrom pathlib import Pathfrom ..plugin import Category, CredentialSpec, CredentialType, PluginMetafrom .base import BasePluginclass JikePlugin(BasePlugin):
    DB_NAME = "即刻"
    TITLE_PROP = "摘要"
    KEY_PROP = "PostId"
    SCHEMA = {
        "摘要": {"title": {}},
        "正文": {"rich_text": {}},
        "时间": {"date": {}},
        "点赞": {"number": {"format": "number"}},
        "评论": {"number": {"format": "number"}},
        "链接": {"url": {}},
        "PostId": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="jike",
        name="即刻",
        category=Category.OTHER,
        description="把即刻动态的本地产出 JSON 同步到 Notion（官方 API 已不稳定，推荐导出后入库）。",
        docs_url="https://github.com/wslh/NotionHub#jike",
        icon="🟢",
        credentials=(
            CredentialSpec(
                "JIKE_EXPORT", "即刻导出文件路径", CredentialType.FILE,
                "导出 JSON 的绝对路径。", secret=False,
            ),
            CredentialSpec(
                "JIKE_COOKIE", "即刻 Cookie（在线抓取，可选）", CredentialType.COOKIE,
                "在线抓取已不稳定，仅作说明保留；推荐改用本地导出。", required=False,
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("JIKE_EXPORT"))

    def _load(self) -> list[dict]:
        path = Path(os.environ["JIKE_EXPORT"])
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("posts") or data.get("data") or data.get("list") or []
        return data if isinstance(data, list) else []

    def _items(self, ctx):
        for post in self._load():
            pid = str(post.get("id") or post.get("postId") or post.get("url") or "")
            if not pid:
                continue
            content = post.get("content") or post.get("text") or ""
            raw = {
                "摘要": (content[:50] or pid)[:50],
                "正文": content[:1900],
                "点赞": int(post.get("likeCount") or post.get("likes") or 0),
                "评论": int(post.get("commentCount") or post.get("comments") or 0),
                "链接": post.get("url") or "",
                "PostId": pid,
            }
            ts = post.get("time") or post.get("createdAt") or post.get("created_at")
            if ts:
                raw["时间"] = {"date": {"start": str(ts)}}
            yield pid, raw
