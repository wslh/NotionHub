"""Daily location plugin: record today's configured location via reverse-geocode.

Uses the free, key-less BigDataCloud reverse-geocode API. Set
``DAILY_LOCATION_LOCATION`` to "lat,lon". Docs: https://www.bigdatacloud.com/
"""
from __future__ import annotations

import os

from ..plugin import Category, CredentialSpec, CredentialType, PluginMeta
from .base import BasePlugin, http_get_json


class DailyLocationPlugin(BasePlugin):
    DB_NAME = "每日位置"
    TITLE_PROP = "日期"
    KEY_PROP = "Date"
    SCHEMA = {
        "日期": {"title": {}},
        "地点": {"rich_text": {}},
        "坐标": {"rich_text": {}},
        "Date": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="daily-location",
        name="每日位置",
        category=Category.OTHER,
        description="记录每天的位置（反查地名），用 BigDataCloud 免 Key 反地理编码。设置 DAILY_LOCATION_LOCATION=纬度,经度。",
        docs_url="https://github.com/wslh/NotionHub#daily-location",
        icon="📍",
        credentials=(
            CredentialSpec(
                "DAILY_LOCATION_LOCATION", "经纬度 (lat,lon)", CredentialType.API_KEY,
                "例如 31.2304,121.4737（上海）。", secret=False,
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("DAILY_LOCATION_LOCATION"))

    def _items(self, ctx):
        loc = os.environ["DAILY_LOCATION_LOCATION"]
        lat, _, lon = (x.strip() for x in loc.partition(","))
        from datetime import date as _date
        today = _date.today().isoformat()
        try:
            geo = http_get_json(
                "https://api.bigdatacloud.net/data/reverse-geocode-client",
                params={"latitude": lat, "longitude": lon, "localityLanguage": "zh"},
            )
            place = (geo.get("city") or geo.get("locality") or geo.get("principalSubdivision") or "")
        except Exception:  # noqa: BLE001
            place = ""
        raw = {
            "日期": today,
            "地点": place[:1900],
            "坐标": loc,
            "Date": today,
        }
        yield today, raw
