"""统一的日志配置，避免散落的 print，并支持本地日志文件与脱敏。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_DIR = Path("logs")
_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def redact(message: str) -> str:
    """对可能包含密钥的字符串做脱敏，避免写入日志/终端。"""
    if not message:
        return message
    import re

    # 脱敏 notion secret / 长 token / api key 值
    message = re.sub(
        r"(ntn_[A-Za-z0-9]{4})[A-Za-z0-9]{10,}", r"\1****", message
    )
    message = re.sub(
        r"(secret_[A-Za-z0-9]{4})[A-Za-z0-9]{10,}", r"\1****", message
    )
    message = re.sub(r"(token[\"=:\s]+)[A-Za-z0-9_\-]{12,}", r"\1****", message, flags=re.I)
    return message


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(str(a)) if isinstance(a, str) else a for a in record.args
            )
        return True


def setup_logging(verbose: bool = False, quiet: bool = False) -> logging.Logger:
    """配置根日志：控制台按级别，文件始终记录 DEBUG（含脱敏）。"""
    level = logging.WARNING if quiet else (logging.DEBUG if verbose else logging.INFO)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(console)

    LOG_DIR.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(LOG_DIR / "weread2notion.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    file_handler.addFilter(_RedactingFilter())
    root.addHandler(file_handler)

    return logging.getLogger("weread2notion")
