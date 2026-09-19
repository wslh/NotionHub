"""Beidanci (Bu Bei Dan Ci) English-learning plugin."""
from __future__ import annotationsimport jsonimport osfrom pathlib import Pathfrom ..plugin import Category, PluginMetafrom .base import BasePlugindef _load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("words", "reviews", "items", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


def _normalize(w):
    if not isinstance(w, dict):
        return None
    word = str(w.get("word") or w.get("text") or "").strip()
    if not word:
        return None
    return {
        "id": word.lower(),
        "word": word,
        "meaning": str(w.get("meaning") or w.get("definition") or w.get("translation") or ""),
        "status": str(w.get("status") or w.get("state") or "learning"),
        "date": str(w.get("date") or w.get("last_review") or ""),
    }


class BeidanciPlugin(BasePlugin):
    """不背单词同步：把每日学习、授课、新学和复习记录 upsert 到 Notion。"""

    DB_NAME = "不背单词"
    TITLE_PROP = "单词"
    KEY_PROP = "WordKey"
    SCHEMA = {
        "单词": {"title": {}},
        "释义": {"rich_text": {}},
        "状态": {"select": {"options": []}},
        "日期": {"date": {}},
        "WordKey": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="beidanci",
        name="不背单词",
        category=Category.LEARNING,
        description="不背单词每日学习、授课、新学和复习记录自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#beidanci",
        icon=chr(0x1F4DA),
    )

    def is_configured(self):
        return bool(os.getenv("BEIDANCI_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("BEIDANCI_EXPORT", "")
        if not path or not Path(path).exists():
            return
        for w in _load(path):
            n = _normalize(w)
            if not n:
                continue
            key = n["id"]
            raw = {
                "单词": n["word"],
                "释义": n["meaning"][:1900],
                "状态": {"select": {"name": n["status"][:80] or "learning"}},
                "WordKey": key,
            }
            if n["date"]:
                raw["日期"] = {"date": {"start": n["date"]}}
            yield key, raw

    def _health_extra(self, ctx):
        path = os.getenv("BEIDANCI_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
