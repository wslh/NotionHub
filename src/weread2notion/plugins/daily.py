"""Daily notes plugin: import local journal files into Notion daily pages.

Reads a directory of dated notes (``DAILY_NOTES_DIR``); ``.md`` / ``.json`` files
whose name starts with a date (YYYY-MM-DD) become a Notion daily page. Fully
self-hosted, no third-party service required.
"""
from __future__ import annotationsimport logginglog = logging.getLogger(__name__)

import jsonimport osfrom pathlib import Pathfrom ..plugin import Category, CredentialSpec, CredentialType, PluginMetafrom .base import BasePluginclass DailyPlugin(BasePlugin):
    DB_NAME = "每日记录"
    TITLE_PROP = "日期"
    KEY_PROP = "Date"
    SCHEMA = {
        "日期": {"title": {}},
        "内容": {"rich_text": {}},
        "来源": {"rich_text": {}},
        "Date": {"rich_text": {}},
    }
    meta = PluginMeta(
        id="daily",
        name="每日记录",
        category=Category.NOTES,
        description="把本地日记目录（按日期命名的 .md/.json）导入 Notion 每日页。",
        docs_url="https://github.com/wslh/NotionHub#daily",
        icon="📅",
        credentials=(
            CredentialSpec(
                "DAILY_NOTES_DIR", "日记目录路径", CredentialType.FILE,
                "存放按 YYYY-MM-DD 命名的 .md/.json 文件的目录。", secret=False,
            ),
        ),
    )

    def is_configured(self) -> bool:
        d = os.getenv("DAILY_NOTES_DIR")
        return bool(d) and Path(d).is_dir()

    def _items(self, ctx):
        base = Path(os.environ["DAILY_NOTES_DIR"])
        for path in sorted(base.iterdir()):
            if not path.is_file():
                continue
            name = path.stem
            if not re_match_date(name):
                continue
            content = self._read(path)
            if content is None:
                continue
            raw = {
                "日期": name,
                "内容": content[:1900],
                "来源": path.name,
                "Date": name,
            }
            yield name, raw

    @staticmethod
    def _read(path: Path) -> str | None:
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("error in %s: %s", __name__, exc)
                return None
            if isinstance(data, dict):
                return (data.get("content") or data.get("text") or json.dumps(data, ensure_ascii=False))[:1900]
            if isinstance(data, str):
                return data[:1900]
            return json.dumps(data, ensure_ascii=False)[:1900]
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text[:1900]


def re_match_date(name: str):
    import re
    return re.match(r"^\d{4}-\d{2}-\d{2}", name)
