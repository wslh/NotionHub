"""YouTube liked-videos plugin."""
from __future__ import annotationsimport jsonimport loggingimport osfrom pathlib import Pathfrom ..plugin import Category, PluginMetafrom .base import BasePluginlog = logging.getLogger(__name__)
def _load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("videos", "liked", "items", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


def _normalize(v):
    if not isinstance(v, dict):
        return None
    title = str(v.get("title") or "").strip()
    return {
        "id": str(v.get("id") or v.get("video_id") or title),
        "title": title,
        "channel": str(v.get("channel") or v.get("channelTitle") or v.get("uploader") or ""),
        "url": str(v.get("url") or v.get("link") or ("https://youtu.be/" + str(v.get("id", "")))),
        "published": str(v.get("published_at") or v.get("publishedAt") or v.get("upload_date") or ""),
    }


class YouTubePlugin(BasePlugin):
    """YouTube 收藏同步：把导出 JSON 里的每个视频 upsert 到 Notion。"""

    DB_NAME = "YouTube 收藏"
    TITLE_PROP = "标题"
    KEY_PROP = "VideoId"
    SCHEMA = {
        "标题": {"title": {}},
        "频道": {"rich_text": {}},
        "链接": {"url": {}},
        "发布时间": {"date": {}},
        "VideoId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="youtube",
        name="YouTube",
        category=Category.MEDIA,
        description="YouTube 频道、播放列表、赞过的视频自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#youtube",
        icon=chr(0x1F525),
    )

    def is_configured(self):
        return bool(os.getenv("YOUTUBE_EXPORT")) or bool(os.getenv("YOUTUBE_API_KEY"))

    def _items(self, ctx):
        path = os.environ.get("YOUTUBE_EXPORT", "")
        if not path or not Path(path).exists():
            return
        try:
            records = _load(path)
        except Exception as exc:  # noqa: BLE001
            log.warning("error in %s: %s", __name__, exc)
            return
        for v in records:
            n = _normalize(v)
            if not n:
                continue
            vid = n["id"]
            raw = {
                "标题": n["title"] or "(no title)",
                "频道": n["channel"][:1900],
                "链接": n["url"],
                "VideoId": vid,
            }
            if n["published"]:
                raw["发布时间"] = {"date": {"start": n["published"]}}
            yield vid, raw
