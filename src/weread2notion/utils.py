"""Shared text/date helpers reused by source plugins and core modules.

- ``strip_html``：去除 HTML 标签、反转义实体、折叠空白。
- ``parse_date_to_iso``：把常见日期字符串解析为 ISO 8601；无法解析时原样返回。
- ``parse_date_to_timestamp``：把常见日期字符串解析为 Unix 时间戳（秒）；无法解析时返回 ``None``。
- ``parse_kindle_clipping_date``：从 Kindle 标注元数据行解析时间，兼容英文/中文界面。
"""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(value: str) -> str:
    """Strip HTML tags, unescape entities, and collapse whitespace.

    Tags are removed *before* entities are unescaped, so escaped markup such as
    ``&lt;div&gt;`` is preserved as literal text instead of being stripped as a tag.
    """
    if not value:
        return ""
    cleaned = unescape(_HTML_RE.sub(" ", value))
    return _WS_RE.sub(" ", cleaned).strip()


# 常见日期格式：RFC822（带时区）、本地无时区、以及带 Z / 偏移 / 微秒的 ISO 变体。
# 取各插件原有格式的并集，保证迁移行为一致。``parse_date_to_timestamp`` 也复用此表。
_DATE_FMTS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
)


def parse_date_to_iso(value: str) -> str:
    """Parse a common date string to ISO 8601; return the original text if unparseable."""
    if not value:
        return ""
    text = value.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return text


def parse_date_to_timestamp(value: str) -> int | None:
    """Parse a common date string to a Unix timestamp (seconds); return ``None`` if unparseable.

    Iterates the same ``_DATE_FMTS`` table as :func:`parse_date_to_iso`, differing only
    in the return type (Unix timestamp instead of an ISO 8601 string). A trailing ``Z``
    is therefore treated as UTC here too, keeping the two helpers consistent.
    """
    if not value:
        return None
    text = value.strip()
    for fmt in _DATE_FMTS:
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    # fromisoformat() does not accept a trailing "Z"; strip it only for the ISO fallback.
    try:
        return int(datetime.fromisoformat(text.replace("Z", "")).timestamp())
    except ValueError:
        return None


def parse_kindle_clipping_date(meta: str) -> int | None:
    """Parse a Kindle clipping's metadata line into a Unix timestamp.

    Handles both English ("Added on 1/1/24, 10:00:00 AM") and Chinese
    ("添加于 2024年3月5日 星期二 上午8:00:00") locale formats; returns ``None`` when
    the timestamp cannot be extracted.
    """
    if not meta:
        return None
    # 英文：Added on 1/1/24, 10:00:00 AM
    m = re.search(
        r"added on\s+(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}:\d{2}\s*[AP]M)",
        meta,
        re.IGNORECASE,
    )
    if m:
        try:
            return int(
                datetime.strptime(
                    f"{m.group(1)} {m.group(2)}", "%m/%d/%y %I:%M:%S %p"
                ).timestamp()
            )
        except ValueError:
            pass
    # 中文：添加于 2024年3月5日 星期二 上午8:00:00
    m = re.search(
        r"添加于\s*(\d{4})年(\d{1,2})月(\d{1,2})日[^\d]*(\d{1,2}):(\d{2}):(\d{2})",
        meta,
    )
    if m:
        try:
            return int(
                datetime(
                    int(m.group(1)), int(m.group(2)), int(m.group(3)),
                    int(m.group(4)), int(m.group(5)), int(m.group(6)),
                ).timestamp()
            )
        except ValueError:
            pass
    return None
