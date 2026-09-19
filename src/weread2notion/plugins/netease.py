"""NetEase Cloud Music playlist plugin for NotionHub.

Imports tracks from a NetEase playlist JSON export. Set NETEASE_PLAYLIST
to the path of the JSON file. Each track is written to the Notion
"网易云音乐歌单" database.
Supports two common export formats: a flat list, or a dict with a top-level
"tracks" key (from netease-cloud-music-exporter).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin


def _load_tracks(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(data, dict):
        for key in ('tracks', 'songs', 'playlist', 'data'):
            v = data.get(key)
            if isinstance(v, list):
                return v
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and 'name' in v[0]:
                return v
    if isinstance(data, list):
        return data
    return []


def _normalize(track):
    if not isinstance(track, dict):
        return None
    name = str(track.get('name') or track.get('title') or '').strip()
    if not name:
        return None
    artists = track.get('artists') or track.get('artist') or []
    if isinstance(artists, str):
        artist = artists.strip()
    elif isinstance(artists, list):
        names = []
        for a in artists:
            if isinstance(a, dict):
                n = a.get('name')
                if n:
                    names.append(str(n))
            elif isinstance(a, str):
                names.append(a)
        artist = ' / '.join(names)
    else:
        artist = ''
    album = track.get('album')
    if isinstance(album, dict):
        album_name = str(album.get('name') or '').strip()
    else:
        album_name = str(album or '').strip()
    duration = int(track.get('duration') or track.get('dt') or 0) // 1000
    song_id = str(track.get('id') or track.get('song_id') or name)
    return {
        'id': song_id,
        'name': name,
        'artist': artist,
        'album': album_name,
        'duration': duration,
    }


class NeteasePlugin(BasePlugin):
    """NetEase 歌单同步：把 JSON 导出里的每首歌 upsert 到 Notion 歌单库。"""

    DB_NAME = "网易云音乐歌单"
    TITLE_PROP = "歌名"
    KEY_PROP = "SongId"
    SCHEMA = {
        "歌名": {"title": {}},
        "歌手": {"rich_text": {}},
        "专辑": {"rich_text": {}},
        "时长": {"number": {"format": "number"}},
        "SongId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="netease",
        name="NetEase Playlist",
        category=Category.MEDIA,
        description="Import a NetEase Music playlist from a JSON export. Set NETEASE_PLAYLIST to the JSON file path.",
        docs_url="https://github.com/wslh/NotionHub#netease",
        icon="🎵",
    )

    def is_configured(self):
        return bool(os.getenv("NETEASE_PLAYLIST"))

    def _items(self, ctx):
        path = os.environ.get('NETEASE_PLAYLIST', '')
        if not path or not Path(path).exists():
            return
        for track in _load_tracks(path):
            n = _normalize(track)
            if not n:
                continue
            sid = n['id']
            raw = {
                '歌名': n['name'],
                '歌手': n['artist'][:1900],
                '专辑': n['album'][:1900],
                '时长': n['duration'],
                'SongId': sid,
            }
            yield sid, raw

    def _health_extra(self, ctx):
        path = os.environ.get("NETEASE_PLAYLIST", "")
        return {"exists": bool(path) and Path(path).exists()}
