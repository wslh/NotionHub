"""Notion HTTP 传输层：带重试的请求与块遍历。

与具体 NotionWorkspace 实例解耦，只依赖 ``notion_client.Client`` 兼容对象，
便于复用与单测（测试可用假 client 注入）。
"""

from __future__ import annotations

import random
import time
from typing import Any


def request_with_retry(
    client,
    path: str,
    method: str = "GET",
    body: dict | None = None,
    interval: float = 0.34,
) -> dict:
    """调用 Notion client.request，对瞬时错误做指数退避重试。

    退避策略：首次使用基础间隔 ``interval``，之后指数退避并加入抖动，避免
    请求同时打满。尊重 Notion 的 ``Retry-After`` 头覆盖退避时间。

    Notion 在大规模同步时会偶发瞬时 429/5xx，这些会重试；但校验/权限错误
    立即抛出，不重试。
    """
    last_error = None
    for attempt in range(5):
        # 首次使用基础间隔，之后指数退避并加入抖动，避免请求同时打满。
        if attempt == 0:
            time.sleep(interval)
        else:
            backoff = min(2**attempt, 30) + random.uniform(0, 1)
            time.sleep(backoff)
        try:
            return client.request(path=path, method=method, body=body)
        except Exception as exc:  # noqa: BLE001 - 需要捕获任意瞬时错误
            last_error = exc
            response = getattr(exc, "response", None)
            status = getattr(exc, "status", None) or getattr(
                response, "status_code", None
            )
            # 尊重 Notion 的 Retry-After 头，覆盖退避时间。
            if status == 429:
                retry_after = getattr(response, "headers", {}).get("Retry-After")
                if retry_after and str(retry_after).isdigit():
                    time.sleep(min(int(retry_after), 60))
            # Notion occasionally returns transient 429/5xx responses
            # during large syncs. Retry those, but surface validation and
            # permission errors immediately.
            if status != 429 and (status is None or status < 500):
                raise
    raise last_error


def list_children_blocks(client, block_id: str) -> list[dict[str, Any]]:
    """遍历某个块下的全部子块（自动翻页）。"""
    rows, cursor = [], None
    while True:
        response = client.blocks.children.list(
            block_id=block_id, page_size=100, start_cursor=cursor
        )
        rows.extend(response.get("results") or [])
        if not response.get("has_more"):
            return rows
        cursor = response.get("next_cursor")
