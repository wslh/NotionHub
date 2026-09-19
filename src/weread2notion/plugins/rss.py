"""RSS/Atom feed plugin for NotionHub.

Reads standard RSS 2.0 or Atom feeds from URLs in the RSS_FEEDS env var
(comma-separated) and writes each entry to the Notion "RSS 订阅" database.
No authentication required.
"""
from __future__ import annotationsimport osimport xml.etree.ElementTree as ETfrom urllib.parse import urlparseimport requestsfrom ..plugin import Category, PluginMetafrom ..utils import parse_date_to_isofrom .base import BasePluginATOM = "{http://www.w3.org/2005/Atom}"


import logginglog = logging.getLogger(__name__)
def _fetch_feed(url, timeout=20):
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "NotionHub/1.0"})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    source = urlparse(url).netloc or url
    channel_title = source
    items = []
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is not None:
            t = channel.findtext("title")
            if t and t.strip():
                channel_title = t.strip()
            for item in channel.findall("item"):
                items.append({
                    "title": (item.findtext("title") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "summary": (item.findtext("description") or "").strip()[:1900],
                    "date": parse_date_to_iso(item.findtext("pubDate") or ""),
                    "guid": (item.findtext("guid") or "").strip(),
                })
    elif root.tag == f"{ATOM}feed":
        t = root.findtext(f"{ATOM}title")
        if t and t.strip():
            channel_title = t.strip()
        for entry in root.findall(f"{ATOM}entry"):
            link = ""
            for l in entry.findall(f"{ATOM}link"):
                href = l.attrib.get("href")
                if href:
                    link = href
                    break
            items.append({
                "title": (entry.findtext(f"{ATOM}title") or "").strip(),
                "link": link,
                "summary": (entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content") or "").strip()[:1900],
                "date": parse_date_to_iso(entry.findtext(f"{ATOM}updated") or entry.findtext(f"{ATOM}published") or ""),
                "guid": (entry.findtext(f"{ATOM}id") or link).strip(),
            })
    return {"source": channel_title or source, "items": items}


class RssPlugin(BasePlugin):
    """RSS/Atom 订阅同步：把每个条目 upsert 到 Notion 订阅库。"""

    DB_NAME = "RSS 订阅"
    TITLE_PROP = "标题"
    KEY_PROP = "GUID"
    SCHEMA = {
        "标题": {"title": {}},
        "链接": {"url": {}},
        "摘要": {"rich_text": {}},
        "发布时间": {"date": {}},
        "来源 Feed": {"select": {"options": []}},
        "GUID": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="rss",
        name="RSS Feeds",
        category=Category.OTHER,
        description="Sync any standard RSS/Atom feed into Notion. Set RSS_FEEDS to a comma-separated URL list.",
        docs_url="https://github.com/wslh/NotionHub#rss",
        icon="\U0001f4e1",
    )

    def is_configured(self):
        return bool(os.getenv("RSS_FEEDS"))

    def _urls(self):
        return [u.strip() for u in os.environ.get("RSS_FEEDS", "").split(",") if u.strip()]

    def _collect_feeds(self):
        feeds = []
        for url in self._urls():
            try:
                feeds.append(_fetch_feed(url))
            except Exception as exc:  # noqa: BLE001
                log.warning("error in %s: %s", __name__, exc)
                continue
        return feeds

    def _items(self, ctx):
        for feed in self._collect_feeds():
            source = feed["source"] or "Unknown"
            for item in feed["items"]:
                guid = item.get("guid") or item.get("link") or item.get("title") or ""
                raw = {
                    "标题": item.get("title") or "(untitled)",
                    "链接": item.get("link") or "",
                    "摘要": item.get("summary") or "",
                    "来源 Feed": {"select": {"name": source[:80]}},
                    "GUID": guid,
                }
                date = item.get("date")
                if date:
                    raw["发布时间"] = {"date": {"start": date}}
                yield guid, raw

    def _health_extra(self, ctx):
        return {"feeds": len(self._urls())}
