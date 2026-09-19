"""Trakt watch-history plugin."""
from __future__ import annotationsimport osimport requestsfrom ..plugin import Category, PluginMetafrom .base import BasePlugin_BASE = "https://api.trakt.tv"


import logginglog = logging.getLogger(__name__)
def _fetch_history(token, client_id, limit=100):
    headers = {
        "Authorization": "Bearer " + token,
        "trakt-api-version": "2",
        "trakt-api-key": client_id,
    }
    resp = requests.get(_BASE + "/users/me/history?limit=" + str(limit), headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _normalize(entry):
    if not isinstance(entry, dict):
        return None
    typ = entry.get("type")
    payload = entry.get(typ) if typ in entry else entry
    if not isinstance(payload, dict):
        return None
    title = payload.get("title") or ""
    year = payload.get("year") or ""
    watched_at = entry.get("watched_at") or ""
    return {
        "id": str(entry.get("id") or (title + "|" + watched_at)),
        "title": str(title),
        "year": int(year) if str(year).isdigit() else 0,
        "type": str(typ or ""),
        "watched_at": str(watched_at),
    }


class TraktPlugin(BasePlugin):
    """Trakt 观看历史同步：把电影、剧集、单集观看记录 upsert 到 Notion。"""

    DB_NAME = "观看历史"
    TITLE_PROP = "标题"
    KEY_PROP = "HistoryId"
    SCHEMA = {
        "标题": {"title": {}},
        "类型": {"select": {"options": []}},
        "年份": {"number": {"format": "number"}},
        "观看时间": {"date": {}},
        "HistoryId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="trakt",
        name="Trakt",
        category=Category.MEDIA,
        description="自动将 Trakt 的电影、剧集、单集观看历史同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#trakt",
        icon=chr(0x2728),
    )

    def is_configured(self):
        return bool(os.getenv("TRAKT_TOKEN")) and bool(os.getenv("TRAKT_CLIENT_ID"))

    def _items(self, ctx):
        token = os.getenv("TRAKT_TOKEN", "")
        cid = os.getenv("TRAKT_CLIENT_ID", "")
        if not (token and cid):
            return
        try:
            data = _fetch_history(token, cid)
        except Exception as exc:  # noqa: BLE001
            log.warning("error in %s: %s", __name__, exc)
            return
        for entry in data:
            n = _normalize(entry)
            if not n:
                continue
            hid = n["id"]
            raw = {
                "标题": (n["title"] or "(untitled)")[:1900],
                "类型": {"select": {"name": n["type"][:80] or "unknown"}},
                "年份": n["year"],
                "HistoryId": hid,
            }
            if n["watched_at"]:
                raw["观看时间"] = {"date": {"start": n["watched_at"]}}
            yield hid, raw
