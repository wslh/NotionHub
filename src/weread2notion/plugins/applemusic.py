"""Apple Music listening history plugin."""
from __future__ import annotations
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin


def _parse_library(path):
    root = ET.parse(path).getroot()
    out = []
    for track in root.iter("dict"):
        name = ""
        artist = ""
        album = ""
        for child in track:
            tag = child.tag
            if tag == "key":
                key = (child.text or "").strip()
            elif tag == "string":
                if key == "Name":
                    name = (child.text or "").strip()
                elif key == "Artist":
                    artist = (child.text or "").strip()
                elif key == "Album":
                    album = (child.text or "").strip()
            elif tag == "true":
                continue
        if name:
            out.append({"name": name, "artist": artist, "album": album})
    return out


class AppleMusicPlugin(BasePlugin):
    """Apple Music 听歌记录同步：把导出库里的每首歌 upsert 到 Notion。"""

    DB_NAME = "听歌记录"
    TITLE_PROP = "歌名"
    KEY_PROP = "TrackKey"
    SCHEMA = {
        "歌名": {"title": {}},
        "歌手": {"rich_text": {}},
        "专辑": {"rich_text": {}},
        "TrackKey": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="applemusic",
        name="Apple Music",
        category=Category.MEDIA,
        description="Apple Music 听歌记录自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#applemusic",
        icon=chr(0x1F3B5),
    )

    def is_configured(self):
        return bool(os.getenv("APPLEMUSIC_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("APPLEMUSIC_EXPORT", "")
        if not path or not Path(path).exists():
            return
        try:
            tracks = _parse_library(path)
        except Exception:
            return
        for t in tracks:
            key = (t["name"] + "|" + t["artist"]).strip("|")
            raw = {
                "歌名": t["name"],
                "歌手": t["artist"][:1900],
                "专辑": t["album"][:1900],
                "TrackKey": key,
            }
            yield key, raw

    def _health_extra(self, ctx):
        path = os.getenv("APPLEMUSIC_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
