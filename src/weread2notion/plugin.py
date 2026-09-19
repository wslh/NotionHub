"""NotionHub plugin framework: contract every data-source plugin must follow.

A plugin is a data-source adapter (WeRead, Flomo, GitHub, ...). It reads from an
external source and writes into Notion, orchestrated by the registry.

Design principles: thin interface, categorised, skippable when unconfigured,
and independently runnable (single id or --all).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Protocol, runtime_checkable


class Category(str, Enum):
    """Categories shown in the NotionHub control panel filter bar."""
    READING = "\u9605\u8bfb"
    PODCAST = "\u64ad\u5ba2"
    MEDIA = "\u5f71\u97f3"
    NOTES = "\u7b14\u8bb0"
    TODO = "\u5f85\u529e"
    LEARNING = "\u5b66\u4e60"
    EXERCISE = "\u8fd0\u52a8"
    PRODUCTIVITY = "\u6548\u7387"
    DIET = "\u996e\u98df"
    OTHER = "\u5176\u4ed6"

    @classmethod
    def labels(cls) -> list[str]:
        return [c.value for c in cls]


class CredentialType(str, Enum):
    """How a credential is obtained, driving the panel UI and guidance."""
    API_KEY = "api_key"        # 粘贴 API Key / Token
    COOKIE = "cookie"          # 从浏览器复制 Cookie
    OAUTH = "oauth"            # 走 OAuth 授权流程
    QRCODE = "qrcode"          # 扫码登录（通常由配套脚本产出凭证）
    FILE = "file"              # 本地导出文件路径
    URLS = "urls"              # URL 列表（逗号分隔）


@dataclass(frozen=True)
class CredentialSpec:
    """Declares one credential a plugin needs.

    Declaring these on :class:`PluginMeta` lets the browser panel render the
    right input, write the value into .env under ``env_key``, and offer a
    documentation hint without hardcoding per-plugin UI.
    """
    env_key: str
    label: str
    cred_type: CredentialType = CredentialType.API_KEY
    hint: str = ""
    required: bool = True
    secret: bool = True        # 是否在 UI 掩码显示

    def to_dict(self) -> dict[str, Any]:
        return {
            "env_key": self.env_key,
            "label": self.label,
            "cred_type": self.cred_type.value,
            "hint": self.hint,
            "required": self.required,
            "secret": self.secret,
        }


@dataclass(frozen=True)
class PluginMeta:
    """Plugin metadata: control panel display and docs link."""
    id: str
    name: str
    category: Category
    description: str
    docs_url: str = ""
    icon: str = ""
    builtin: bool = True
    # 统一声明该插件所需凭证，供面板自动生成授权表单并写入 .env
    credentials: tuple[CredentialSpec, ...] = ()

    def credentials_dict(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.credentials]


@dataclass
class PluginContext:
    """Context the runner injects: Notion client, shared settings, log hook."""
    notion: Any
    settings: Any
    log: Any = None

    def logger(self):
        return self.log


@dataclass
class SyncResult:
    """Unified return from Plugin.sync; the runner aggregates these into logs."""
    plugin_id: str
    synced: int = 0
    skipped: int = 0
    errors: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "synced": self.synced,
            "skipped": self.skipped,
            "errors": self.errors,
            **self.extra,
        }


@runtime_checkable
class Plugin(Protocol):
    """Protocol every data-source plugin must implement."""
    meta: PluginMeta

    def is_configured(self) -> bool:
        ...

    def setup(self, ctx: PluginContext) -> None:
        ...

    def discover(self, ctx: PluginContext) -> Iterable[dict[str, Any]]:
        ...

    def sync(self, ctx: PluginContext) -> SyncResult:
        ...

    def health(self, ctx: PluginContext) -> dict[str, Any]:
        ...
