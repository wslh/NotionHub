"""Daily weather plugin: record today's weather via Open-Meteo (no API key).

Open-Meteo is free and key-less. Set ``DAILY_WEATHER_LOCATION`` to "lat,lon".
Docs: https://open-meteo.com/
"""
from __future__ import annotations

import os

from ..plugin import Category, CredentialSpec, CredentialType, PluginMeta
from .base import BasePlugin, http_get_json

_WMO = {
    0: "晴", 1: "大致晴朗", 2: "局部多云", 3: "阴",
    45: "雾", 48: "雾凇", 51: "小毛雨", 53: "毛雨", 55: "大毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪",
    80: "阵雨", 81: "强阵雨", 82: "暴雨", 95: "雷暴", 96: "雷暴伴冰雹",
}


class DailyWeatherPlugin(BasePlugin):
    DB_NAME = "每日天气"
    TITLE_PROP = "日期"
    KEY_PROP = "Date"
    SCHEMA = {
        "日期": {"title": {}},
        "最高温(℃)": {"number": {"format": "number"}},
        "最低温(℃)": {"number": {"format": "number"}},
        "降水(mm)": {"number": {"format": "number"}},
        "天气": {"rich_text": {}},
        "地点": {"rich_text": {}},
        "Date": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="daily-weather",
        name="每日天气",
        category=Category.OTHER,
        description="用 Open-Meteo（免 Key）记录每天天气到 Notion。设置 DAILY_WEATHER_LOCATION=纬度,经度。",
        docs_url="https://github.com/wslh/NotionHub#daily-weather",
        icon="🌤️",
        credentials=(
            CredentialSpec(
                "DAILY_WEATHER_LOCATION", "经纬度 (lat,lon)", CredentialType.API_KEY,
                "例如 39.9042,116.4074（北京）。", secret=False,
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("DAILY_WEATHER_LOCATION"))

    def _items(self, ctx):
        loc = os.environ["DAILY_WEATHER_LOCATION"]
        lat, _, lon = (x.strip() for x in loc.partition(","))
        data = http_get_json(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                "timezone": "auto", "forecast_days": 1,
            },
        )
        daily = data.get("daily") or {}
        if not daily.get("time"):
            return
        i = 0
        date = daily["time"][i]
        tmax = daily["temperature_2m_max"][i]
        tmin = daily["temperature_2m_min"][i]
        prec = daily.get("precipitation_sum", [0])[i]
        code = int(daily.get("weather_code", [0])[i])
        raw = {
            "日期": date,
            "最高温(℃)": tmax,
            "最低温(℃)": tmin,
            "降水(mm)": prec,
            "天气": _WMO.get(code, f"代码{code}"),
            "地点": loc,
            "Date": date,
        }
        yield date, raw
