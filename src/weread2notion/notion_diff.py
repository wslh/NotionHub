"""属性归一化与字段级 diff：把 Notion 的读写两种属性模型互相映射、比较。

Notion 一行属性在「读」与「写」时结构不同：

- 读模型（来自 API 返回）：富文本带 ``plain_text``，数字/勾选直接是值，
  选择/状态是 ``{"name": ...}``。
- 写模型（由 ``NotionWorkspace.property`` 生成）：富文本带 ``text.content``，
  数字/勾选/选择等同读模型。

因此比较「现有值」与「目标值」必须按属性类型分别归一化后再比。本模块
把这部分纯逻辑独立出来，与 NotionWorkspace 实例解耦，便于复用与单测。
"""

from __future__ import annotations

from typing import Any


# 这些属性由 Notion 计算或生成，永远不写入，也不参与 diff。
READ_ONLY_KINDS = frozenset(
    {
        "formula",
        "rollup",
        "created_time",
        "created_by",
        "last_edited_time",
        "last_edited_by",
        "unique_id",
        "verification",
        "button",
    }
)


def plain_property_value(prop: dict | None) -> Any:
    """从 Notion 读模型里取出属性的「业务值」（剥离类型外壳）。"""
    if not prop:
        return None
    kind = prop.get("type")
    value = prop.get(kind)
    if kind in {"title", "rich_text"}:
        return "".join(item.get("plain_text", "") for item in (value or []))
    if kind in {"number", "url", "checkbox"}:
        return value
    if kind in {"select", "status"}:
        return (value or {}).get("name")
    return value


def same_value(kind: str, current: dict, desired: dict) -> bool:
    """比较 Notion 返回的 ``current`` 与将要写入的 ``desired`` 是否等价。

    ``current`` 是读模型（富文本带 ``plain_text``），``desired`` 是写模型
    （富文本带 ``text.content``），因此必须按 ``kind`` 分别归一化后再比。

    保守原则：比较抛错或遇到未知类型一律返回 ``False``（判定为「有变化」），
    让字段照旧写入。最坏情况退化成改造前的全量覆盖，不会漏更新。
    """
    try:
        if kind in {"title", "rich_text"}:
            a = plain_property_value(current) or ""
            b = "".join(
                item.get("text", {}).get("content", "")
                for item in (desired.get(kind) or [])
            )
            return a == b
        if kind == "number":
            a = plain_property_value(current)
            b = desired.get("number")
            if a is None and b is None:
                return True
            if a is None or b is None:
                return False
            return abs(float(a) - float(b)) < 1e-9
        if kind == "checkbox":
            return bool(plain_property_value(current)) == bool(
                desired.get("checkbox")
            )
        if kind in {"select", "status"}:
            a = plain_property_value(current)
            b = (desired.get(kind) or {}).get("name")
            return (a or None) == (b or None)
        if kind == "multi_select":
            a = {i.get("name") for i in (plain_property_value(current) or [])}
            b = {i.get("name") for i in (desired.get(kind) or [])}
            return a == b
        if kind == "date":
            a = plain_property_value(current) or {}
            b = desired.get("date") or {}
            return (a.get("start") or None) == (b.get("start") or None) and (
                a.get("end") or None
            ) == (b.get("end") or None)
        if kind == "relation":
            a = {i.get("id") for i in (plain_property_value(current) or [])}
            b = {i.get("id") for i in (desired.get("relation") or [])}
            return a == b
        if kind == "url":
            return (plain_property_value(current) or None) == (
                desired.get("url") or None
            )
    except Exception:  # noqa: BLE001 - 比较失败必须退回「有变化」
        return False
    return False


def compute_changed_properties(
    schemas: dict[str, str],
    existing: dict | None,
    desired: dict,
) -> dict:
    """返回 ``desired`` 中与 Notion 现有值不同的字段子集。

    ``existing`` 为空（新记录）时返回全部字段；遇到只读类型或无法逐字段比较
    的字段时，按正常逻辑跳过只读类型、其余正常比较。
    """
    if not existing:
        return desired
    changed = {}
    for name, desired_prop in desired.items():
        kind = schemas.get(name)
        if kind in READ_ONLY_KINDS:
            continue
        current = existing.get(name)
        # 现有记录里没有这个属性（模板刚加了字段），必须写入。
        if current is None:
            changed[name] = desired_prop
            continue
        if not same_value(kind, current, desired_prop):
            changed[name] = desired_prop
    return changed
