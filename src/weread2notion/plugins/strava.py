"""Strava plugin: syncs athlete activities to Notion.

Auth: a Strava access token (``STRAVA_TOKEN``). Paginates the activities feed.
Docs: https://developers.strava.com/docs/reference/#api-Activities
"""
from __future__ import annotations

import os

from ..plugin import Category, CredentialSpec, CredentialType, PluginMeta
from .base import BasePlugin, http_get_json


class StravaPlugin(BasePlugin):
    DB_NAME = "Strava 运动记录"
    TITLE_PROP = "活动"
    KEY_PROP = "ActivityId"
    SCHEMA = {
        "活动": {"title": {}},
        "类型": {"select": {"options": []}},
        "距离(km)": {"number": {"format": "number"}},
        "时长(分钟)": {"number": {"format": "number"}},
        "爬升(m)": {"number": {"format": "number"}},
        "日期": {"date": {}},
        "链接": {"url": {}},
        "ActivityId": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="strava",
        name="Strava",
        category=Category.EXERCISE,
        description="把 Strava 运动记录（跑步/骑行等）同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#strava",
        icon="🏃",
        credentials=(
            CredentialSpec(
                "STRAVA_TOKEN", "Strava Access Token", CredentialType.OAUTH,
                "Strava API 应用的 access token（需 activity:read 权限）。",
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("STRAVA_TOKEN"))

    def _items(self, ctx):
        token = os.environ["STRAVA_TOKEN"]
        headers = {"Authorization": f"Bearer {token}"}
        page = 1
        while page <= 5:
            data = http_get_json(
                "https://www.strava.com/api/v3/athlete/activities",
                headers=headers,
                params={"per_page": 50, "page": page},
            )
            if not data:
                break
            for act in data:
                yield self._rec(act)
            page += 1

    @staticmethod
    def _rec(act: dict) -> tuple[str, dict]:
        aid = str(act.get("id"))
        name = act.get("name") or "activity"
        raw = {
            "活动": name[:1900],
            "类型": act.get("type", "") or None,
            "距离(km)": round((act.get("distance") or 0) / 1000, 2),
            "时长(分钟)": round((act.get("moving_time") or 0) / 60, 1),
            "爬升(m)": round(act.get("total_elevation_gain") or 0, 1),
            "链接": f"https://www.strava.com/activities/{aid}",
            "ActivityId": aid,
        }
        start = act.get("start_date")
        if start:
            raw["日期"] = {"date": {"start": start.replace("Z", "+00:00")}}
        return aid, raw
