"""Toggl time-tracking plugin."""
from __future__ import annotationsimport base64import osfrom datetime import datetime, timedeltaimport requestsfrom ..plugin import Category, PluginMetafrom .base import BasePlugin_BASE = "https://api.track.toggl.com/api/v9"


import logginglog = logging.getLogger(__name__)
def _fetch_reports(token, since_iso, until_iso, workspace_id=None):
    headers = {"Authorization": "Basic " + base64.b64encode(
        (token + ":api_token").encode("utf-8")).decode("ascii")}
    params = {"start_date": since_iso, "end_date": until_iso}
    if workspace_id:
        params["workspace_id"] = workspace_id
    resp = requests.get(_BASE + "/me/time_entries", headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _normalize(entry):
    if not isinstance(entry, dict):
        return None
    description = str(entry.get("description") or "").strip() or "(no description)"
    start = str(entry.get("start") or "")
    duration = int(entry.get("duration") or 0)
    project_id = entry.get("project_id")
    return {
        "id": str(entry.get("id") or start + description),
        "description": description,
        "start": start,
        "duration_s": duration,
        "project_id": str(project_id) if project_id else "",
    }


class TogglPlugin(BasePlugin):
    """Toggl 时间追踪同步：把时间记录 upsert 到 Notion。"""

    DB_NAME = "时间追踪"
    TITLE_PROP = "任务"
    KEY_PROP = "EntryId"
    SCHEMA = {
        "任务": {"title": {}},
        "开始时间": {"date": {}},
        "时长(秒)": {"number": {"format": "number"}},
        "项目": {"rich_text": {}},
        "EntryId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="toggl",
        name="Toggl",
        category=Category.PRODUCTIVITY,
        description="Toggl 时间追踪记录自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#toggl",
        icon=chr(0x1F3AF),
    )

    def is_configured(self):
        return bool(os.getenv("TOGGL_API_TOKEN"))

    def _items(self, ctx):
        token = os.getenv("TOGGL_API_TOKEN", "")
        if not token:
            return
        since = (datetime.utcnow() - timedelta(days=14)).date().isoformat()
        until = datetime.utcnow().date().isoformat()
        try:
            data = _fetch_reports(token, since, until)
        except Exception as exc:  # noqa: BLE001
            log.warning("error in %s: %s", __name__, exc)
            return
        for entry in data:
            n = _normalize(entry)
            if not n:
                continue
            eid = n["id"]
            raw = {
                "任务": n["description"][:1900],
                "时长(秒)": n["duration_s"],
                "项目": n["project_id"][:1900],
                "EntryId": eid,
            }
            if n["start"]:
                raw["开始时间"] = {"date": {"start": n["start"]}}
            yield eid, raw
