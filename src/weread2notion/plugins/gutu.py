"""Gutu (古文岛) classical Chinese plugin."""
from __future__ import annotationsimport jsonimport loggingimport osfrom pathlib import Pathfrom ..plugin import Category, PluginMetafrom .base import BasePluginlog = logging.getLogger(__name__)
def _load(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for k in ("poems", "articles", "items", "data"):
                v = data.get(k)
                if isinstance(v, list):
                    return v
        if isinstance(data, list):
            return data
    except Exception as exc:  # noqa: BLE001
        log.warning("error in %s: %s", __name__, exc)
        pass
    # Treat as plain text: one item per non-empty line.
    return [{"title": line.strip(), "content": line.strip()} for line in text.splitlines() if line.strip()]


def _normalize(it):
    if not isinstance(it, dict):
        return None
    title = str(it.get("title") or it.get("name") or "").strip()
    author = str(it.get("author") or it.get("dynasty") or "").strip()
    content = str(it.get("content") or it.get("body") or it.get("text") or "").strip()
    if not title and not content:
        return None
    return {
        "id": (title + "|" + author).strip("|"),
        "title": title or content[:50],
        "author": author,
        "content": content[:1900],
    }


class GutuPlugin(BasePlugin):
    """古文岛同步：把诗文、作者、收藏、诗单、标注和背诵记录 upsert 到 Notion。"""

    DB_NAME = "古文岛记录"
    TITLE_PROP = "标题"
    KEY_PROP = "ItemKey"
    SCHEMA = {
        "标题": {"title": {}},
        "作者": {"rich_text": {}},
        "内容": {"rich_text": {}},
        "ItemKey": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="gutu",
        name="古文岛",
        category=Category.LEARNING,
        description="古文岛诗文、作者、收藏、诗单、标注和背诵记录自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#gutu",
        icon=chr(0x1F4DD),
    )

    def is_configured(self):
        return bool(os.getenv("GUTU_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("GUTU_EXPORT", "")
        if not path or not Path(path).exists():
            return
        for it in _load(path):
            n = _normalize(it)
            if not n:
                continue
            key = n["id"]
            raw = {
                "标题": n["title"][:1900],
                "作者": n["author"][:1900],
                "内容": n["content"],
                "ItemKey": key,
            }
            yield key, raw

    def _health_extra(self, ctx):
        path = os.getenv("GUTU_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
