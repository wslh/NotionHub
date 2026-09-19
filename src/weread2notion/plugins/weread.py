"""WeRead plugin: wraps the existing Synchronizer engine, conforms to the Plugin protocol."""
from __future__ import annotationsimport osfrom ..plugin import (    Category,    CredentialSpec,    CredentialType,    PluginContext,    PluginMeta,    SyncResult,)class WereadPlugin:
    meta = PluginMeta(
        id="weread",
        name="微信读书",
        category=Category.READING,
        description="微信读书笔记划线、阅读时长自动同步到 Notion。",
        docs_url="https://github.com/wslh/NotionHub#wechat-reading",
        icon="📚",
        credentials=(
            CredentialSpec(
                env_key="WEREAD_API_KEY",
                label="微信读书 Gateway API Key",
                cred_type=CredentialType.API_KEY,
                hint="以 wrk_ 开头，从微信读书 Gateway 获取。",
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("WEREAD_API_KEY"))

    def setup(self, ctx: PluginContext) -> None:
        ctx.notion.discover()
        ctx.notion.ensure_sync_settings(ctx.settings.start_year)
        ctx.notion.ensure_reading_snapshots()

    def discover(self, ctx: PluginContext):
        from ..sources import build_source        from ..weread import WeReadClient
        client = WeReadClient(ctx.settings.weread_api_key, ctx.settings.skill_version)
        return build_source("weread", client).shelf().get("books", [])

    def sync(self, ctx: PluginContext) -> SyncResult:
        from ..sources import build_source        from ..sync import Synchronizer        from ..weread import WeReadClient
        client = WeReadClient(ctx.settings.weread_api_key, ctx.settings.skill_version)
        source = build_source("weread", client)
        preferences = ctx.notion.ensure_sync_settings(ctx.settings.start_year)
        result = Synchronizer(
            source, ctx.notion, ctx.settings.start_year, preferences=preferences
        ).run()
        return SyncResult(
            plugin_id=self.meta.id,
            synced=result.get("changed_books", 0),
            extra=result,
        )

    def health(self, ctx: PluginContext) -> dict:
        from ..sources import build_source        from ..status import workspace_status        from ..weread import WeReadClient
        try:
            client = WeReadClient(ctx.settings.weread_api_key, ctx.settings.skill_version)
            report = workspace_status(
                build_source("weread", client), ctx.notion, ctx.settings.start_year
            )
            return {"configured": True, "healthy": report.get("healthy", True), "details": report}
        except Exception as exc:  # noqa: BLE001
            return {"configured": True, "healthy": False, "error": str(exc)}
