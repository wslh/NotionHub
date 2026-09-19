"""Apple Podcasts plugin: import Apple Podcasts OPML and sync latest episodes.

Apple Podcasts has no user-data API; the self-hosted path is to export your
subscriptions as OPML (e.g. via a Shortcut / library export) and let this plugin
fetch each feed's RSS. Reuses :class:`OpmlPodcastPlugin`.
"""
from __future__ import annotations

from ..plugin import Category, CredentialSpec, CredentialType, PluginMeta
from .podcast import OpmlPodcastPlugin


class ApplePodcastPlugin(OpmlPodcastPlugin):
    OPML_ENV = "APPLEPODCAST_OPML"
    DB_NAME = "Apple 播客"
    meta = PluginMeta(
        id="applepodcast",
        name="Apple 播客",
        category=Category.PODCAST,
        description="导入 Apple 播客的 OPML 订阅，把最新单集同步到 Notion（无用户数据 API）。",
        docs_url="https://github.com/wslh/NotionHub#applepodcast",
        icon="🍎",
        credentials=(
            CredentialSpec(
                "APPLEPODCAST_OPML", "Apple 播客 OPML 路径", CredentialType.FILE,
                "从 Apple 播客导出的 OPML 绝对路径。", secret=False,
            ),
        ),
    )
