"""Xiaoyuzhou (小宇宙) podcast plugin."""
from __future__ import annotationsimport loggingimport osimport xml.etree.ElementTree as ETimport requestsfrom ..plugin import Category, PluginMetafrom ..utils import parse_date_to_isofrom .base import BasePluginlog = logging.getLogger(__name__)
def _fetch_feed(url, timeout=20):
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "NotionHub/1.0"})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for it in root.iter("item"):
        link_el = it.find("link")
        enclosure = it.find("enclosure")
        audio = ""
        if enclosure is not None:
            audio = enclosure.attrib.get("url", "")
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "audio": audio,
            "link": link_el.text.strip() if link_el is not None and link_el.text else "",
            "pub": parse_date_to_iso(it.findtext("pubDate") or ""),
            "duration": (it.findtext("itunes:duration") or "").strip(),
            "guid": (it.findtext("guid") or "").strip(),
        })
    return items


class XiaoyuzhouPlugin(BasePlugin):
    """小宇宙播客同步：把订阅源里的每集 upsert 到 Notion。"""

    DB_NAME = "小宇宙播客"
    TITLE_PROP = "标题"
    KEY_PROP = "GUID"
    SCHEMA = {
        "标题": {"title": {}},
        "音频": {"url": {}},
        "链接": {"url": {}},
        "发布时间": {"date": {}},
        "时长": {"rich_text": {}},
        "GUID": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="xiaoyuzhou",
        name="小宇宙",
        category=Category.PODCAST,
        description="小宇宙播客收记、收听时长自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#xiaoyuzhou",
        icon=chr(0x1F680),
    )

    def is_configured(self):
        return bool(os.getenv("XIAOYUZHOU_FEEDS"))

    def _urls(self):
        return [u.strip() for u in os.environ.get("XIAOYUZHOU_FEEDS", "").split(",") if u.strip()]

    def _items(self, ctx):
        for url in self._urls():
            try:
                feed = _fetch_feed(url)
            except Exception as exc:  # noqa: BLE001
                log.warning("error in %s: %s", __name__, exc)
                continue
            for it in feed:
                guid = it["guid"] or it["link"] or it["title"]
                raw = {
                    "标题": it["title"] or "(untitled)",
                    "音频": it["audio"],
                    "链接": it["link"],
                    "时长": it["duration"][:1900],
                    "GUID": guid,
                }
                if it["pub"]:
                    raw["发布时间"] = {"date": {"start": it["pub"]}}
                yield guid, raw

    def _health_extra(self, ctx):
        return {"feeds": len(self._urls())}
