"""Shared helpers for data-source plugins.

提供：
- ``http_get_json``：带 UA、超时的 JSON GET。
- ``BasePlugin``：统一 ``setup``（建库）与 ``sync``（upsert 循环），
  子类只需实现 ``is_configured`` 与 ``_items(ctx) -> Iterable[(key, raw)]``。

所有插件未配置时由 runner 安全跳过（见 runner.run_plugin）。
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import requests

from ..plugin import PluginContext, SyncResult

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 25
UA = {"User-Agent": "Mozilla/5.0 (NotionHub self-hosted sync)"}


def http_get_json(url: str, *, headers=None, params=None, timeout=DEFAULT_TIMEOUT) -> Any:
    h = dict(UA)
    if headers:
        h.update(headers)
    resp = requests.get(url, headers=h, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def http_get_text(url: str, *, headers=None, params=None, timeout=DEFAULT_TIMEOUT) -> str:
    h = dict(UA)
    if headers:
        h.update(headers)
    resp = requests.get(url, headers=h, params=params, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    return resp.text


class BasePlugin:
    """Convention over configuration base for source plugins.

    Subclasses set class attributes and implement two methods::

        DB_NAME:   Notion database title (empty => skip ensure_database)
        TITLE_PROP: title column name
        SCHEMA:    Notion property definitions (name -> type dict)
        KEY_PROP:  unique key column used for upsert (must be title/rich_text/number/url)

        def is_configured(self) -> bool: ...
        def _items(self, ctx) -> Iterable[tuple[Any, dict]]: ...
    """

    DB_NAME: str = ""
    TITLE_PROP: str = "名称"
    SCHEMA: dict[str, dict] = {}
    KEY_PROP: str = "ID"

    def is_configured(self) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    def setup(self, ctx: PluginContext) -> None:
        if self.DB_NAME:
            ctx.notion.ensure_database(self.DB_NAME, self.TITLE_PROP, self.SCHEMA)

    def _items(self, ctx: PluginContext) -> Iterable[tuple[Any, dict]]:  # pragma: no cover
        raise NotImplementedError

    def discover(self, ctx: PluginContext) -> list[dict]:
        """返回「将被同步」的原始条目，不写入 Notion（预演 / 调试用）。

        由 ``_items`` 推导；不适用（例如纯维护类插件）时重写或返回空列表。
        注意：该方法必须存在——插件框架的 ``Plugin`` 协议把它列为必需成员，
        缺少会导致 ``isinstance(p, Plugin)`` 为假，注册表直接拒绝该插件。
        """
        try:
            return [raw for _key, raw in self._items(ctx)]
        except NotImplementedError:
            return []

    def sync(self, ctx: PluginContext) -> SyncResult:
        result = SyncResult(plugin_id=self.meta.id)
        for key, raw in self._items(ctx):
            try:
                ctx.notion.upsert(self.DB_NAME, self.KEY_PROP, key, raw)
                result.synced += 1
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort the run
                result.errors += 1
                if ctx.log:
                    ctx.log.warning("%s upsert failed (key=%s): %s", self.meta.id, key, exc)
        return result

    def health(self, ctx: PluginContext) -> dict:
        return {"configured": self.is_configured(), **self._health_extra(ctx)}

    def _health_extra(self, ctx: PluginContext) -> dict:
        """子类重写以返回额外健康信息（文件是否存在、条目数等）。

        基类已将其合并进 ``health`` 的返回值，因此绝大多数插件无需重写 ``health``。
        """
        return {}
