"""数据导出：将 Notion 中的书架/阅读记录导出为 CSV 或 Markdown，便于数据可携。

对外只暴露两个高层函数：:func:`export_books` 与 :func:`export_snapshots`。
底层的「记录构建」「CSV 写出」「Markdown 写出」被抽成可复用的辅助函数，
避免两套导出逻辑各自重复一遍文件读写样板。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable, Iterable

# 列顺序即属性名：Notion 属性名与导出列名一致，便于泛型映射。
BOOK_COLUMNS = ["BookId", "书名", "作者", "分类", "阅读状态", "阅读进度", "最后阅读时间"]
SNAPSHOT_COLUMNS = ["日期", "书名", "累计阅读时长（分钟）", "当日新增阅读时长（分钟）", "阅读进度"]


# --------------------------------------------------------------------------- #
# 底层辅助：构建与写出
# --------------------------------------------------------------------------- #
def _plain(notion, properties: dict[str, Any], name: str) -> Any:
    """从 Notion 属性块里取裸值（兼容缺省/空属性）。"""
    return notion.plain_property((properties or {}).get(name))


def _build_records(notion, rows: Iterable[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    """把 Notion 行列表按列名映射成纯值记录字典。

    列名与 Notion 属性名保持一致，因此无需为每个来源单独手写映射。
    """
    return [
        {name: _plain(notion, row.get("properties") or {}, name) for name in columns}
        for row in rows
    ]


def _default_out(name: str, fmt: str) -> Path:
    """解析默认输出路径并确保父目录存在。"""
    out = Path("exports") / f"{name}.{fmt}"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _write_csv(out: Path, columns: list[str], records: list[dict[str, Any]]) -> None:
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


def _write_markdown(out: Path, header: str, lines: list[str]) -> None:
    with out.open("w", encoding="utf-8") as fh:
        fh.write(header)
        if lines:
            fh.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# 高层导出函数
# --------------------------------------------------------------------------- #
def export_books(notion, fmt: str = "csv", out: Path | None = None) -> Path:
    """导出书架为 CSV 或 Markdown 文件，返回文件路径。"""
    records = _build_records(notion, notion.query_all("书架"), BOOK_COLUMNS)
    out = out or _default_out("books", fmt)
    if fmt == "csv":
        _write_csv(out, BOOK_COLUMNS, records)
    else:
        _write_markdown(
            out,
            "# 书架导出\n\n",
            [
                f"- **{r['书名']}** — {r['作者']} / {r['分类']} "
                f"[{r['阅读状态']} {r['阅读进度']}]"
                for r in records
            ],
        )
    return out


def export_snapshots(notion, fmt: str = "csv", out: Path | None = None) -> Path:
    """导出每日阅读快照为 CSV 或 Markdown 文件，返回文件路径。"""
    if "阅读快照" not in notion.sources:
        raise RuntimeError("阅读快照数据库不存在，无法导出")
    rows = notion.query_all("阅读快照")
    records = _build_records(notion, rows, SNAPSHOT_COLUMNS)
    out = out or _default_out("snapshots", fmt)
    if fmt == "csv":
        _write_csv(out, SNAPSHOT_COLUMNS, records)
    else:
        _write_markdown(
            out,
            "# 阅读快照导出\n\n",
            [
                f"- {r['日期']} {r['书名']}: "
                f"{r['当日新增阅读时长（分钟）']} 分钟（累计 {r['累计阅读时长（分钟）']}）"
                for r in records
            ],
        )
    return out
