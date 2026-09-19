"""TickTick (滴答清单) task plugin."""
from __future__ import annotationsimport jsonimport osfrom pathlib import Pathfrom ..plugin import Category, PluginMetafrom .base import BasePlugindef _load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("tasks", "todos", "items", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


def _normalize(t):
    if not isinstance(t, dict):
        return None
    title = str(t.get("title") or t.get("content") or "").strip()
    if not title:
        return None
    return {
        "id": str(t.get("id") or t.get("taskId") or title),
        "title": title,
        "status": str(t.get("status") or "pending"),
        "due": str(t.get("dueDate") or t.get("due") or t.get("deadline") or ""),
        "priority": str(t.get("priority") or ""),
    }


class TickTickPlugin(BasePlugin):
    """滴答清单同步：把任务、习惯 upsert 到 Notion。"""

    DB_NAME = "滴答清单任务"
    TITLE_PROP = "标题"
    KEY_PROP = "TaskId"
    SCHEMA = {
        "标题": {"title": {}},
        "状态": {"select": {"options": []}},
        "优先级": {"rich_text": {}},
        "截止日期": {"date": {}},
        "TaskId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="ticktick",
        name="滴答清单",
        category=Category.TODO,
        description="滴答清单任务、习惯自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#ticktick",
        icon=chr(0x2705),
    )

    def is_configured(self):
        return bool(os.getenv("TICKTICK_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("TICKTICK_EXPORT", "")
        if not path or not Path(path).exists():
            return
        for t in _load(path):
            n = _normalize(t)
            if not n:
                continue
            tid = n["id"]
            raw = {
                "标题": n["title"][:1900],
                "状态": {"select": {"name": n["status"][:80] or "pending"}},
                "优先级": n["priority"][:1900],
                "TaskId": tid,
            }
            if n["due"]:
                raw["截止日期"] = {"date": {"start": n["due"]}}
            yield tid, raw

    def _health_extra(self, ctx):
        path = os.getenv("TICKTICK_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
