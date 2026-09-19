"""Builtin plugin auto-registration.

Add a new builtin by appending the plugin class to :data:`BUILTIN_PLUGINS`
(and the ``_instances`` builder below).
"""
from __future__ import annotations
from ..plugin import Plugin
from .weread import WereadPlugin
from .flomo import FlomoPlugin
from .github import GithubPlugin
from .rss import RssPlugin
from .douban import DoubanPlugin
from .telegram import TelegramPlugin
from .netease import NeteasePlugin
from .xiaoyuzhou import XiaoyuzhouPlugin
from .keep import KeepPlugin
from .toggl import TogglPlugin
from .forest import ForestPlugin
from .applemusic import AppleMusicPlugin
from .douyin import DouyinPlugin
from .youtube import YouTubePlugin
from .gutu import GutuPlugin
from .trakt import TraktPlugin
from .dayone import DayOnePlugin
from .ticktick import TickTickPlugin
from .duolingo import DuolingoPlugin
from .bilibili import BilibiliPlugin
from .beidanci import BeidanciPlugin
# --- 新增：原 NotionHub 云端集成补齐的自托管插件 ---
from .spotify import SpotifyPlugin
from .strava import StravaPlugin
from .weibo import WeiboPlugin
from .xiaohongshu import XiaohongshuPlugin
from .jike import JikePlugin
from .podcast import PodcastPlugin
from .applepodcast import ApplePodcastPlugin
from .daily import DailyPlugin
from .daily_weather import DailyWeatherPlugin
from .daily_location import DailyLocationPlugin
from .guwendao import GuwendaoPlugin
from .fix import FixPlugin


def _instances() -> list[Plugin]:
    plugins: list[Plugin] = []
    for cls in (
        WereadPlugin,
        FlomoPlugin,
        GithubPlugin,
        RssPlugin,
        DoubanPlugin,
        TelegramPlugin,
        NeteasePlugin,
        XiaoyuzhouPlugin,
        KeepPlugin,
        TogglPlugin,
        ForestPlugin,
        AppleMusicPlugin,
        DouyinPlugin,
        YouTubePlugin,
        GutuPlugin,
        TraktPlugin,
        DayOnePlugin,
        TickTickPlugin,
        DuolingoPlugin,
        BilibiliPlugin,
        BeidanciPlugin,
        # --- 新增 ---
        SpotifyPlugin,
        StravaPlugin,
        WeiboPlugin,
        XiaohongshuPlugin,
        JikePlugin,
        PodcastPlugin,
        ApplePodcastPlugin,
        DailyPlugin,
        DailyWeatherPlugin,
        DailyLocationPlugin,
        GuwendaoPlugin,
        FixPlugin,
    ):
        try:
            plugins.append(cls())
        except Exception:
            continue
    return plugins


BUILTIN_PLUGINS: list[Plugin] = _instances()