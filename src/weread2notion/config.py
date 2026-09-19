from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ID_RE = re.compile(
    r"([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
    re.IGNORECASE,
)


class ConfigError(RuntimeError):
    pass


def notion_id(value: str) -> str:
    match = ID_RE.search(value or "")
    if not match:
        raise ConfigError("NOTION_PAGE 必须是 Notion 页面链接或页面 ID")
    return match.group(1)


def redact_secret(value: str) -> str:
    """仅保留前后缀用于排查，中间用 **** 代替。"""
    value = value or ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


@dataclass(frozen=True)
class StorageSettings:
    """资源存储配置（S3 兼容对象存储）。

    由面板「资源存储」页写入 .env 的 STORAGE_* 变量提供；未配置时各字段为空，
    调用方据此判断是否需要上传媒体文件。
    """

    provider: str = ""
    endpoint: str = ""
    region: str = ""
    bucket: str = ""
    access_key: str = ""
    secret_key: str = ""
    prefix: str = "notionhub-media/"
    cdn_domain: str = ""
    youtube: bool = False
    xiaohongshu: bool = False
    douyin: bool = False

    @property
    def configured(self) -> bool:
        """当且仅当 Endpoint / Bucket / AccessKey / SecretKey 都齐全才算已配置。"""
        return bool(self.endpoint and self.bucket and self.access_key and self.secret_key)

    def plugins(self) -> list[str]:
        """返回已开启媒体上传的插件 ID 列表。"""
        out = []
        if self.youtube:
            out.append("youtube")
        if self.xiaohongshu:
            out.append("xiaohongshu")
        if self.douyin:
            out.append("douyin")
        return out


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_storage_settings() -> StorageSettings:
    """从环境变量（含 .env）读取资源存储配置。"""
    load_dotenv()
    endpoint = (os.getenv("STORAGE_ENDPOINT") or "").strip()
    prefix = (os.getenv("STORAGE_PREFIX") or "notionhub-media/").strip()
    return StorageSettings(
        provider=(os.getenv("STORAGE_PROVIDER") or "").strip(),
        endpoint=endpoint,
        region=(os.getenv("STORAGE_REGION") or "").strip(),
        bucket=(os.getenv("STORAGE_BUCKET") or "").strip(),
        access_key=(os.getenv("STORAGE_ACCESS_KEY") or "").strip(),
        secret_key=(os.getenv("STORAGE_SECRET_KEY") or "").strip(),
        prefix=prefix,
        cdn_domain=(os.getenv("STORAGE_CDN_DOMAIN") or "").strip(),
        youtube=_truthy(os.getenv("STORAGE_YOUTUBE")),
        xiaohongshu=_truthy(os.getenv("STORAGE_XIAOHONGSHU")),
        douyin=_truthy(os.getenv("STORAGE_DOUYIN")),
    )


@dataclass(frozen=True)
class Settings:
    weread_api_key: str
    notion_token: str
    notion_page_id: str
    notion_version: str = "2026-03-11"
    skill_version: str = "1.0.4"
    start_year: int = 2023
    backup_dir: Path = Path("backups")
    request_interval: float = 0.34
    concurrency: int = 4
    checkpoint_file: Path = Path("backups/.checkpoint.json")
    max_retries: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        api_key = (os.getenv("WEREAD_API_KEY") or "").strip()
        token = (os.getenv("NOTION_TOKEN") or "").strip()
        page = (os.getenv("NOTION_PAGE") or "").strip()
        # WEREAD_API_KEY 仅微信读书同步必需；多数据源自托管（plugins sync）下其它插件
        # 不依赖它，故这里不再强制，避免「只想同步 GitHub/Douban 却必须填微信读书 Key」的怪象。
        # 微信读书专属 sync 命令的强制校验在 cli.main() 中完成。
        if not token:
            raise ConfigError("缺少 NOTION_TOKEN")
        if not page:
            raise ConfigError("缺少 NOTION_PAGE")
        # 早期失败：Notion token 应以 ntn_ 或 secret_ 开头
        if not (token.startswith("ntn_") or token.startswith("secret_")):
            raise ConfigError(
                "NOTION_TOKEN 格式不正确，应以 ntn_ 或 secret_ 开头"
            )
        concurrency = int(os.getenv("CONCURRENCY", "4"))
        if concurrency < 1:
            concurrency = 1
        return cls(
            weread_api_key=api_key,
            notion_token=token,
            notion_page_id=notion_id(page),
            notion_version=os.getenv("NOTION_VERSION", "2026-03-11"),
            skill_version=os.getenv("WEREAD_SKILL_VERSION", "1.0.4"),
            start_year=int(os.getenv("START_YEAR", "2023")),
            backup_dir=Path(os.getenv("BACKUP_DIR", "backups")),
            request_interval=float(os.getenv("NOTION_REQUEST_INTERVAL", "0.34")),
            concurrency=concurrency,
            checkpoint_file=Path(os.getenv("CHECKPOINT_FILE", "backups/.checkpoint.json")),
            max_retries=int(os.getenv("MAX_RETRIES", "5")),
        )
