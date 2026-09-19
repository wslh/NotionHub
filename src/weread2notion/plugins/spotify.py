"""Spotify plugin: syncs recently played tracks and saved tracks to Notion.

Auth: a Spotify OAuth access token (``SPOTIFY_TOKEN``), or client-credentials
(``SPOTIFY_CLIENT_ID`` + ``SPOTIFY_CLIENT_SECRET``) which mints a token on the fly.
Docs: https://developer.spotify.com/documentation/web-api
"""
from __future__ import annotations

import os
import time

from ..plugin import Category, CredentialSpec, CredentialType, PluginMeta
from .base import BasePlugin, http_get_json


def _get_token() -> str | None:
    token = (os.getenv("SPOTIFY_TOKEN") or "").strip()
    if token:
        return token
    cid = (os.getenv("SPOTIFY_CLIENT_ID") or "").strip()
    secret = (os.getenv("SPOTIFY_CLIENT_SECRET") or "").strip()
    if cid and secret:
        import base64
        import requests

        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": "Basic "
                + base64.b64encode(f"{cid}:{secret}".encode()).decode()
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    return None


class SpotifyPlugin(BasePlugin):
    DB_NAME = "Spotify 听歌记录"
    TITLE_PROP = "歌曲"
    KEY_PROP = "TrackId"
    SCHEMA = {
        "歌曲": {"title": {}},
        "艺人": {"rich_text": {}},
        "专辑": {"rich_text": {}},
        "时间": {"date": {}},
        "时长(秒)": {"number": {"format": "number"}},
        "链接": {"url": {}},
        "TrackId": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="spotify",
        name="Spotify",
        category=Category.MEDIA,
        description="把 Spotify 最近播放 / 收藏的歌曲同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#spotify",
        icon="🎵",
        credentials=(
            CredentialSpec(
                "SPOTIFY_TOKEN", "Spotify Access Token", CredentialType.OAUTH,
                "OAuth 授权后的 access token；或用下面的 Client ID/Secret 自动获取。",
                required=False,
            ),
            CredentialSpec(
                "SPOTIFY_CLIENT_ID", "Spotify Client ID", CredentialType.API_KEY,
                "Spotify 开发者后台应用凭证。", required=False,
            ),
            CredentialSpec(
                "SPOTIFY_CLIENT_SECRET", "Spotify Client Secret", CredentialType.API_KEY,
                "与 Client ID 配对。", required=False, secret=True,
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(
            os.getenv("SPOTIFY_TOKEN")
            or (os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET"))
        )

    def _items(self, ctx):
        token = _get_token()
        if not token:
            return
        headers = {"Authorization": f"Bearer {token}"}
        seen = set()
        # 1) 最近播放
        url = "https://api.spotify.com/v1/me/player/recently-played?limit=50"
        for _ in range(4):
            if not url:
                break
            data = http_get_json(url, headers=headers)
            for item in data.get("items", []):
                track = item.get("track", {})
                tid = track.get("id")
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                yield self._rec(track, item.get("played_at"))
            url = data.get("next")
        # 2) 收藏歌曲
        url = "https://api.spotify.com/v1/me/tracks?limit=50&offset=0"
        page = 0
        while url and page < 4:
            data = http_get_json(url, headers=headers)
            for item in data.get("items", []):
                track = item.get("track", {})
                tid = track.get("id")
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                yield self._rec(track, item.get("added_at"))
            url = data.get("next")
            page += 1

    @staticmethod
    def _rec(track: dict, when: str | None) -> tuple[str, dict]:
        artists = " / ".join(a.get("name", "") for a in track.get("artists", []))
        album = (track.get("album") or {}).get("name", "")
        dur = int((track.get("duration_ms") or 0) / 1000)
        ext = track.get("external_urls", {}).get("spotify", "")
        raw = {
            "歌曲": (track.get("name") or "unknown")[:1900],
            "艺人": artists[:1900],
            "专辑": album[:1900],
            "时长(秒)": dur,
            "链接": ext,
            "TrackId": track.get("id"),
        }
        if when:
            raw["时间"] = {"date": {"start": when.replace("Z", "+00:00")}}
        return track.get("id"), raw
