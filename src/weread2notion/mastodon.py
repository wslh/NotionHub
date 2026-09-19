"""Minimal Mastodon (长毛象) client — 仅依赖标准库，用于 Worker 状态播报。

Worker 每轮同步结束后，可以把结果以「嘟文」发布到用户指定的长毛象实例，
既作为运行播报，也作为心跳。凭据来自环境变量：

    MASTODON_INSTANCE      长毛象实例地址，例如 https://mastodon.social
    MASTODON_ACCESS_TOKEN  在实例「开发 → 新建应用」后取得的访问令牌
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional


class MastodonError(RuntimeError):
    """长毛象接口调用失败。"""


class MastodonClient:
    def __init__(self, instance: str, access_token: str):
        self.instance = instance.rstrip("/")
        self.token = access_token

    @classmethod
    def from_env(cls) -> "MastodonClient":
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:  # noqa: BLE001
            pass
        instance = (os.getenv("MASTODON_INSTANCE") or "").strip()
        token = (os.getenv("MASTODON_ACCESS_TOKEN") or "").strip()
        if not instance or not token:
            raise MastodonError(
                "未配置 MASTODON_INSTANCE / MASTODON_ACCESS_TOKEN（请在 .env 中填写）"
            )
        return cls(instance, token)

    def post(self, status: str, max_chars: int = 480, visibility: str = "unlisted") -> dict:
        """发布一条嘟文，超长自动截断。返回实例响应的 JSON 字典。"""
        if len(status) > max_chars:
            status = status[: max_chars - 1].rstrip() + "…"
        url = f"{self.instance}/api/v1/statuses"
        payload = json.dumps({"status": status, "visibility": visibility}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "NotionHub-Worker/1.0")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            raise MastodonError(f"Mastodon 返回 {exc.code}: {body}") from exc
        except Exception as exc:  # noqa: BLE001
            raise MastodonError(f"Mastodon 发布失败：{exc}") from exc

    def verify(self) -> Optional[str]:
        """验证凭据是否可用，可用则返回账号 handle，否则抛出异常。"""
        url = f"{self.instance}/api/v1/accounts/verify_credentials"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("User-Agent", "NotionHub-Worker/1.0")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("acct") or data.get("username")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            raise MastodonError(f"凭据校验失败 {exc.code}: {body}") from exc
        except Exception as exc:  # noqa: BLE001
            raise MastodonError(f"凭据校验失败：{exc}") from exc
