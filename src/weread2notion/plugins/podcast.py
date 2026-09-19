"""Podcast base plugin: import OPML subscriptions and sync latest episodes.

Self-hosted podcast sync reads an OPML subscription export, fetches each feed's
RSS, and upserts the latest episodes into Notion. ``applepodcast`` subclasses this
for Apple Podcasts OPML exports; the generic ``podcast`` entry handles any OPML.
"""
from __future__ import annotationsimport logginglog = logging.getLogger(__name__)

import email.utilsimport osimport xml.etree.ElementTree as ETfrom pathlib import Pathfrom ..plugin import Category, CredentialSpec, CredentialType, PluginMetafrom ..utils import strip_htmlfrom .base import BasePlugin, http_get_textdef _rfc822_to_iso(text: str) -> str | None:
    if not text:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(text.strip())
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=__import__("datetime").timezone.utc)
        return dt.isoformat()
    except Exception as exc:  # noqa: BLE001
        log.warning("error in %s: %s", __name__, exc)
        return None


def parse_opml(path: Path) -> list[str]:
    tree = ET.parse(path)
    return [
        o.attrib["xmlUrl"]
        for o in tree.iter("outline")
        if o.attrib.get("xmlUrl")
    ]


def parse_feed(url: str, limit: int = 5) -> list[dict]:
    xml = http_get_text(url)
    root = ET.fromstring(xml)
    channel = root.find("channel")
    if channel is None:
        return []
    feed_title = strip_html(channel.findtext("title") or "")
    items: list[dict] = []
    for it in channel.findall("item")[:limit]:
        title = strip_html(it.findtext("title") or "")
        link = (it.findtext("link") or "").strip()
        desc = strip_html(it.findtext("description") or "")
        pub = _rfc822_to_iso(it.findtext("pubDate") or "")
        enc = it.find("enclosure")
        audio = enc.attrib.get("url") if enc is not None else ""
        guid = (it.findtext("guid") or link or title).strip()
        items.append(
            {
                "title": title,
                "feed": feed_title,
                "link": link,
                "desc": desc[:1900],
                "pub": pub,
                "audio": audio,
                "guid": guid,
                "feed_url": url,
            }
        )
    return items


class OpmlPodcastPlugin(BasePlugin):
    """Subclass and set ``OPML_ENV`` / ``DB_NAME`` / ``meta``."""

    OPML_ENV: str = ""
    DB_NAME = "播客单集"
    TITLE_PROP = "单集"
    KEY_PROP = "EpisodeKey"
    SCHEMA = {
        "单集": {"title": {}},
        "播客": {"rich_text": {}},
        "发布": {"date": {}},
        "简介": {"rich_text": {}},
        "链接": {"url": {}},
        "音频": {"url": {}},
        "EpisodeKey": {"rich_text": {}},
    }

    def is_configured(self) -> bool:
        return bool(os.getenv(self.OPML_ENV))

    def _items(self, ctx):
        path = Path(os.environ[self.OPML_ENV])
        if not path.exists():
            return
        for feed_url in parse_opml(path):
            try:
                for ep in parse_feed(feed_url):
                    key = f"{ep['feed_url']}|{ep['guid']}"
                    raw = {
                        "单集": (ep["title"] or "untitled")[:1900],
                        "播客": ep["feed"][:1900],
                        "简介": ep["desc"],
                        "链接": ep["link"],
                        "音频": ep["audio"],
                        "EpisodeKey": key,
                    }
                    if ep["pub"]:
                        raw["发布"] = {"date": {"start": ep["pub"]}}
                    yield key, raw
            except Exception as exc:  # noqa: BLE001 - one dead feed must not abort
                if ctx.log:
                    ctx.log.warning("podcast feed failed %s: %s", feed_url, exc)


class PodcastPlugin(OpmlPodcastPlugin):
    OPML_ENV = "PODCAST_OPML"
    DB_NAME = "播客单集"
    meta = PluginMeta(
        id="podcast",
        name="播客",
        category=Category.PODCAST,
        description="导入 OPML 订阅，把各播客最新单集同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#podcast",
        icon="🎙️",
        credentials=(
            CredentialSpec(
                "PODCAST_OPML", "OPML 订阅文件路径", CredentialType.FILE,
                "播客 App 导出的 OPML 绝对路径。", secret=False,
            ),
        ),
    )
