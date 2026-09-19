"""Plugin runner: builds context, schedules a plugin, aggregates results."""
from __future__ import annotations
import logging
from .plugin import Plugin, PluginContext, SyncResult

log = logging.getLogger(__name__)


def run_plugin(plugin: Plugin, notion, settings) -> SyncResult:
    """Run one plugin. Returns a :class:`SyncResult`; safe-skip if unconfigured."""
    ctx = PluginContext(notion=notion, settings=settings, log=log)
    if not plugin.is_configured():
        log.info(
            "plugin %s not configured, skipped (%s)",
            plugin.meta.name,
            plugin.meta.docs_url or "no docs",
        )
        return SyncResult(plugin_id=plugin.meta.id, skipped=1, extra={"reason": "not_configured"})
    try:
        plugin.setup(ctx)
    except Exception as exc:  # noqa: BLE001 - setup failure should not block sync
        log.warning("plugin %s setup failed: %s", plugin.meta.name, exc)
    return plugin.sync(ctx)
