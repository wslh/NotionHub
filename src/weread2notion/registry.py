"""NotionHub plugin registry: centralised catalogue of every available plugin.

Supports:

- Auto-discovery of built-in plugins (see :data:`weread2notion.plugins.BUILTIN_PLUGINS`).
- Registration of third-party plugins via Python entry points (``notionhub.plugins``).
- Lookup by id or category, with enable/disable filtering at the runner layer.
"""
from __future__ import annotations

from typing import Iterable, Iterator

from .plugin import Category, Plugin


class PluginRegistry:
    """Lightweight plugin registry."""

    def __init__(self, plugins: Iterable[Plugin] = ()) -> None:
        self._plugins: dict[str, Plugin] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: Plugin) -> None:
        if not isinstance(plugin, Plugin):
            raise TypeError(f"{plugin!r} does not implement the Plugin protocol")
        plugin_id = getattr(plugin, "meta", None) and plugin.meta.id
        if not plugin_id:
            raise ValueError(f"{plugin!r} is missing PluginMeta.id")
        if plugin_id in self._plugins:
            raise ValueError(f"duplicate plugin id: {plugin_id}")
        self._plugins[plugin_id] = plugin

    def get(self, plugin_id: str) -> Plugin:
        if plugin_id not in self._plugins:
            raise KeyError(f"unknown plugin: {plugin_id}")
        return self._plugins[plugin_id]

    def all(self) -> list[Plugin]:
        return list(self._plugins.values())

    def by_category(self, category: Category) -> list[Plugin]:
        return [p for p in self._plugins.values() if p.meta.category == category]

    def __iter__(self) -> Iterator[Plugin]:
        return iter(self._plugins.values())

    def __contains__(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    def __len__(self) -> int:
        return len(self._plugins)

    def summary(self) -> list[dict]:
        # 插件在 PluginMeta.credentials 里自己声明的优先，否则回退集中凭证目录。
        from .credentials import credentials_for

        out = []
        for p in self._plugins.values():
            meta_creds = getattr(p.meta, "credentials", ()) or ()
            specs = meta_creds if meta_creds else credentials_for(p.meta.id)
            out.append(
                {
                    "id": p.meta.id,
                    "name": p.meta.name,
                    "category": p.meta.category.value,
                    "description": p.meta.description,
                    "docs_url": p.meta.docs_url,
                    "icon": p.meta.icon,
                    "configured": bool(p.is_configured()),
                    "credentials": [s.to_dict() for s in specs],
                }
            )
        return out


def build_default_registry() -> "PluginRegistry":
    """Build a registry containing every built-in plugin."""
    from .plugins import BUILTIN_PLUGINS
    return PluginRegistry(BUILTIN_PLUGINS)
