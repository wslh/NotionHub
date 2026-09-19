"""Keep (运动) fitness plugin."""
from __future__ import annotations
import json
import os
from pathlib import Path

from ..plugin import Category, PluginMeta
from .base import BasePlugin


def _load_workouts(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("workouts", "records", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


def _normalize(workout):
    if not isinstance(workout, dict):
        return None
    title = str(workout.get("name") or workout.get("title") or "运动记录").strip()
    return {
        "id": str(workout.get("id") or workout.get("time") or title),
        "title": title,
        "kind": str(workout.get("kind") or workout.get("type") or ""),
        "duration": int(workout.get("duration") or 0),
        "calories": int(workout.get("calorie") or workout.get("calories") or 0),
        "date": str(workout.get("date") or workout.get("start_time") or ""),
    }


class KeepPlugin(BasePlugin):
    """Keep 运动记录同步：把导出 JSON 里的每条运动 upsert 到 Notion。"""

    DB_NAME = "运动记录"
    TITLE_PROP = "标题"
    KEY_PROP = "RecordId"
    SCHEMA = {
        "标题": {"title": {}},
        "类型": {"select": {"options": []}},
        "时长(分钟)": {"number": {"format": "number"}},
        "热量": {"number": {"format": "number"}},
        "日期": {"date": {}},
        "RecordId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="keep",
        name="Keep",
        category=Category.EXERCISE,
        description="Keep 运动记录自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#keep",
        icon=chr(0x1F3C3),
    )

    def is_configured(self):
        return bool(os.getenv("KEEP_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("KEEP_EXPORT", "")
        if not path or not Path(path).exists():
            return
        for w in _load_workouts(path):
            n = _normalize(w)
            if not n:
                continue
            rid = n["id"]
            raw = {
                "标题": n["title"],
                "类型": {"select": {"name": n["kind"][:80] or "Workout"}},
                "时长(分钟)": n["duration"],
                "热量": n["calories"],
                "RecordId": rid,
            }
            if n["date"]:
                raw["日期"] = {"date": {"start": n["date"]}}
            yield rid, raw

    def _health_extra(self, ctx):
        path = os.getenv("KEEP_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
