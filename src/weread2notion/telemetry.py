"""可选的匿名遥测（运营支持）。

默认关闭。仅当用户显式设置 WEREAD2NOTION_TELEMETRY=1 时发送，且不含任何
书目、笔记、密钥或个人身份信息，仅上报聚合计数用于规划限流与兼容性。
数据发送到环境变量 WEREAD2NOTION_TELEMETRY_URL（默认项目统计端点），可自定义。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

log = logging.getLogger(__name__)

DEFAULT_URL = "https://example.invalid/telemetry"  # 占位端点，部署方可替换


def send(event: str, payload: dict) -> bool:
    if os.getenv("WEREAD2NOTION_TELEMETRY") != "1":
        return False
    body = json.dumps({"event": event, **payload}).encode("utf-8")
    url = os.getenv("WEREAD2NOTION_TELEMETRY_URL", DEFAULT_URL)
    try:
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=5).close()  # noqa: S310 - 用户显式开启
        return True
    except Exception as exc:  # noqa: BLE001 - 遥测失败绝不影响主流程
        log.debug("遥测发送失败（已忽略）：%s", exc)
        return False
