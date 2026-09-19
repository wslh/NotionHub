"""Fix plugin: repair / normalise Notion database schemas.

Not a data source — a maintenance tool. Re-runs ``ensure_database`` for every
registered plugin so that databases created by older versions (or by the
now-removed NotionHub cloud workflows) get their columns normalised. Requires
only ``NOTION_TOKEN`` + ``NOTION_PAGE`` (the global Notion connection).
"""
from __future__ import annotations

import os

from ..plugin import Category, PluginMeta, SyncResult
from .base import BasePlugin


class FixPlugin(BasePlugin):
    DB_NAME = ""
    meta = PluginMeta(
        id="fix",
        name="修复数据库",
        category=Category.OTHER,
        description="重跑所有插件的 ensure_database，修复/规范化 Notion 数据库结构（不导入数据）。",
        docs_url="https://github.com/wslh/NotionHub#fix",
        icon="🛠️",
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("NOTION_TOKEN"))

    def setup(self, ctx: object) -> None:
        return  # no database of its own

    def sync(self, ctx) -> SyncResult:
        result = SyncResult(plugin_id=self.meta.id)
        from ..registry import build_default_registry

        for plugin in build_default_registry():
            try:
                plugin.setup(ctx)
                result.synced += 1
            except Exception as exc:  # noqa: BLE001
                result.errors += 1
                if ctx.log:
                    ctx.log.warning("fix: ensure_database failed for %s: %s",
                                    plugin.meta.id, exc)
        return result
