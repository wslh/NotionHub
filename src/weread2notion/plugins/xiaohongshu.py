"""Xiaohongshu (RED) plugin: imports a local export into Notion.

小红书没有公开 API，自托管最稳妥的方式是先用官方/第三方方式把笔记导出为
JSON，再交给本插件入库。仍保留 ``XIAOHONGSHU_COOKIE`` 作为「在线抓取」的可选
说明（在线抓取反爬严格，需自行承担稳定性风险）。
"""
from __future__ import annotationsimport jsonimport osfrom pathlib import Pathfrom ..plugin import Category, CredentialSpec, CredentialType, PluginMetafrom .base import BasePluginclass XiaohongshuPlugin(BasePlugin):
    DB_NAME = "小红书笔记"
    TITLE_PROP = "标题"
    KEY_PROP = "NoteId"
    SCHEMA = {
        "标题": {"title": {}},
        "正文": {"rich_text": {}},
        "时间": {"date": {}},
        "点赞": {"number": {"format": "number"}},
        "链接": {"url": {}},
        "NoteId": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="xiaohongshu",
        name="小红书",
        category=Category.OTHER,
        description="把小红书笔记的本地导出 JSON 同步到 Notion（无公开 API，推荐导出后入库）。",
        docs_url="https://github.com/wslh/NotionHub#xiaohongshu",
        icon="📕",
        credentials=(
            CredentialSpec(
                "XIAOHONGSHU_EXPORT", "小红书导出文件路径", CredentialType.FILE,
                "导出 JSON 的绝对路径（数组或含 notes 字段）。", secret=False,
            ),
            CredentialSpec(
                "XIAOHONGSHU_COOKIE", "小红书 Cookie（在线抓取，可选）", CredentialType.COOKIE,
                "在线抓取反爬严格，仅作说明保留；推荐改用本地导出。", required=False,
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("XIAOHONGSHU_EXPORT"))

    def _load(self) -> list[dict]:
        path = Path(os.environ["XIAOHONGSHU_EXPORT"])
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("notes") or data.get("data") or []
        return data if isinstance(data, list) else []

    def _items(self, ctx):
        for note in self._load():
            nid = str(note.get("id") or note.get("note_id") or note.get("url") or "")
            if not nid:
                continue
            raw = {
                "标题": (note.get("title") or "untitled")[:1900],
                "正文": (note.get("content") or note.get("desc") or "")[:1900],
                "点赞": int(note.get("likes") or note.get("liked_count") or 0),
                "链接": note.get("url") or "",
                "NoteId": nid,
            }
            ts = note.get("time") or note.get("create_time") or note.get("created_at")
            if ts:
                raw["时间"] = {"date": {"start": str(ts)}}
            yield nid, raw
