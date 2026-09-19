"""Day-One synthesized daily journal plugin."""
from __future__ import annotationsimport loggingimport osimport refrom pathlib import Pathfrom ..plugin import Category, PluginMetafrom .base import BasePluginlog = logging.getLogger(__name__)
class DayOnePlugin(BasePlugin):
    """生成日记同步：汇总当天的阅读、笔记、任务、运动、影音和时间记录，生成 Notion 日记。"""

    DB_NAME = "生成日记"
    TITLE_PROP = "标题"
    KEY_PROP = "DateKey"
    SCHEMA = {
        "标题": {"title": {}},
        "日期": {"date": {}},
        "摘要": {"rich_text": {}},
        "DateKey": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="dayone",
        name="生成日记",
        category=Category.PRODUCTIVITY,
        description="汇总当天的阅读、笔记、任务、运动、影音和时间记录，自动生成 Notion 日记。",
        docs_url="https://github.com/wslh/NotionHub#dayone",
        icon=chr(0x1F4D4),
    )

    def is_configured(self):
        return bool(os.getenv("DAYONE_EXPORT"))

    def _items(self, ctx):
        path = os.environ.get("DAYONE_EXPORT", "")
        if not path or not Path(path).exists():
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("error in %s: %s", __name__, exc)
            return
        for block in text.split("\n---\n"):
            block = block.strip()
            date_match = re.search(r"^(\d{4}-\d{2}-\d{2})", block)
            if not date_match:
                continue
            date = date_match.group(1)
            summary = "\n".join(line for line in block.splitlines() if line.strip())[:1900]
            raw = {
                "标题": "日记 " + date,
                "摘要": summary,
                "日期": {"date": {"start": date}},
                "DateKey": date,
            }
            yield date, raw

    def _health_extra(self, ctx):
        path = os.getenv("DAYONE_EXPORT", "")
        return {"exists": bool(path) and Path(path).exists()}
