"""文本与分块工具：把任意值转成 Notion rich_text 片段，以及按上限切片迭代。

这些函数与具体 NotionWorkspace 实例无关，因此单独抽出，便于复用与单测。
"""

from __future__ import annotations

from typing import Any, Iterable


def text_value(value: Any) -> list[dict[str, Any]]:
    """把任意值转成 Notion rich_text 写模型；超长文本按 2000 字符切片。"""
    value = "" if value is None else str(value)
    return [
        {"type": "text", "text": {"content": value[index : index + 2000]}}
        for index in range(0, len(value), 2000)
    ] or [{"type": "text", "text": {"content": ""}}]


def chunks(values: list[Any], size: int = 100) -> Iterable[list[Any]]:
    """把列表按 size 切片迭代，用于满足 Notion 批量写入的 100 条上限。"""
    for index in range(0, len(values), size):
        yield values[index : index + size]
