"""Unit tests for the shared helpers in ``weread2notion.utils``.

Covers the four public helpers:

* ``strip_html``            — tag/entity/whitespace cleaning
* ``parse_date_to_iso``     — date string -> ISO 8601 (passthrough on failure)
* ``parse_date_to_timestamp`` — date string -> Unix timestamp (None on failure)
* ``parse_kindle_clipping_date`` — Kindle metadata line -> Unix timestamp

Timestamp assertions are written to be timezone-independent: we compare the two
date helpers against each other and check wall-clock components via
``datetime.fromtimestamp`` (which reconstructs the original local wall time),
rather than asserting absolute epoch integers.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from weread2notion.utils import (
    parse_date_to_iso,
    parse_date_to_timestamp,
    parse_kindle_clipping_date,
    strip_html,
)


# --------------------------------------------------------------------------- #
# strip_html
# --------------------------------------------------------------------------- #
def test_strip_html_removes_tags() -> None:
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_unescapes_entities() -> None:
    assert strip_html("Tom &amp; Jerry") == "Tom & Jerry"
    # 反转义后仍是一段文本；HTML 标签会被一并清洗掉。
    assert strip_html("&lt;div&gt;") == "<div>"


def test_strip_html_collapses_whitespace() -> None:
    assert strip_html("  a   b  \n c ") == "a b c"


def test_strip_html_multiline() -> None:
    assert strip_html("<p>l1</p>\n<p>l2</p>") == "l1 l2"


def test_strip_html_empty_and_none() -> None:
    assert strip_html("") == ""
    assert strip_html(None) == ""


# --------------------------------------------------------------------------- #
# parse_date_to_iso
# --------------------------------------------------------------------------- #
# (raw input, expected normalized ISO)
ISO_CASES = [
    ("2024-01-01T10:00:00+08:00", "2024-01-01T10:00:00+08:00"),
    ("2024-01-01T10:00:00Z", "2024-01-01T10:00:00+00:00"),
    ("2024-01-01T10:00:00.123456+08:00", "2024-01-01T10:00:00.123456+08:00"),
    ("2024-01-01T10:00:00.123456Z", "2024-01-01T10:00:00.123456+00:00"),
    ("Mon, 01 Jan 2024 10:00:00 +0000", "2024-01-01T10:00:00+00:00"),
    ("Mon, 01 Jan 2024 10:00:00 UTC", "2024-01-01T10:00:00"),
    ("2024-01-01 10:00:00", "2024-01-01T10:00:00"),
    ("2024-01-01 10:30", "2024-01-01T10:30:00"),
    ("2024/01/01 10:30", "2024-01-01T10:30:00"),
    ("2024-01-01", "2024-01-01T00:00:00"),
    ("2024/01/01", "2024-01-01T00:00:00"),
    ("2024-01-01T10:00:00", "2024-01-01T10:00:00"),
]


@pytest.mark.parametrize("raw,expected", ISO_CASES)
def test_parse_date_to_iso_formats(raw: str, expected: str) -> None:
    assert parse_date_to_iso(raw) == expected


def test_parse_date_to_iso_passthrough_on_garbage() -> None:
    assert parse_date_to_iso("not-a-date") == "not-a-date"


def test_parse_date_to_iso_empty_and_none() -> None:
    assert parse_date_to_iso("") == ""
    assert parse_date_to_iso(None) == ""


# --------------------------------------------------------------------------- #
# parse_date_to_timestamp
# --------------------------------------------------------------------------- #
def test_parse_date_to_timestamp_type_and_none() -> None:
    assert isinstance(parse_date_to_timestamp("2024-01-01"), int)
    assert parse_date_to_timestamp("garbage") is None
    assert parse_date_to_timestamp("") is None
    assert parse_date_to_timestamp(None) is None


@pytest.mark.parametrize("raw", [case[0] for case in ISO_CASES] + ["not-a-date", ""])
def test_parse_date_to_timestamp_consistent_with_iso(raw) -> None:
    ts = parse_date_to_timestamp(raw)
    if ts is None:
        # 解析失败时 parse_date_to_iso 原样返回；这里确认两者都"无法解析"。
        assert parse_date_to_iso(raw) == raw or raw in ("", None)
        return
    # 同一输入下，timestamp 必须等于把 ISO 结果再转回的时间戳（时区无关）。
    assert ts == int(datetime.fromisoformat(parse_date_to_iso(raw)).timestamp())


def test_parse_date_to_timestamp_z_treated_as_utc() -> None:
    # "Z" 后缀必须与显式 +00:00 等价（修复前 Z 被当成本地时区，差 8 小时）。
    assert (
        parse_date_to_timestamp("2024-01-01T10:00:00Z")
        == parse_date_to_timestamp("2024-01-01T10:00:00+00:00")
    )


# --------------------------------------------------------------------------- #
# parse_kindle_clipping_date
# --------------------------------------------------------------------------- #
def test_parse_kindle_clipping_date_english() -> None:
    ts = parse_kindle_clipping_date("Added on 1/1/24, 10:00:00 AM")
    assert isinstance(ts, int)
    assert datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") == "2024-01-01 10:00:00"


def test_parse_kindle_clipping_date_chinese() -> None:
    ts = parse_kindle_clipping_date("添加于 2024年3月5日 星期一 上午8:00:00")
    assert datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") == "2024-03-05 08:00:00"


def test_parse_kindle_clipping_date_invalid() -> None:
    assert parse_kindle_clipping_date("") is None
    assert parse_kindle_clipping_date(None) is None
    assert parse_kindle_clipping_date("no date here") is None
