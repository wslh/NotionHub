"""Builtin plugin auto-registration.

Add a new builtin by appending the plugin class to :data:`BUILTIN_PLUGINS`
(and the ``_instances`` builder below).
"""
from __future__ import annotationsimport logginglog = logging.getLogger(__name__)
from ..plugin import Pluginfrom .applemusic import AppleMusicPluginfrom .applepodcast import ApplePodcastPluginfrom .beidanci import BeidanciPluginfrom .bilibili import BilibiliPluginfrom .daily import DailyPluginfrom .daily_location import DailyLocationPluginfrom .daily_weather import DailyWeatherPluginfrom .dayone import DayOnePluginfrom .douban import DoubanPluginfrom .douyin import DouyinPluginfrom .duolingo import DuolingoPluginfrom .fix import FixPluginfrom .flomo import FlomoPluginfrom .forest import ForestPluginfrom .github import GithubPluginfrom .gutu import GutuPluginfrom .guwendao import GuwendaoPluginfrom .jike import JikePluginfrom .keep import KeepPluginfrom .netease import NeteasePluginfrom .podcast import PodcastPluginfrom .rss import RssPlugin# --- 新增：原 NotionHub 云端集成补齐的自托管插件 ---from .spotify import SpotifyPluginfrom .strava import StravaPluginfrom .telegram import TelegramPluginfrom .ticktick import TickTickPluginfrom .toggl import TogglPluginfrom .trakt import TraktPluginfrom .weibo import WeiboPluginfrom .weread import WereadPluginfrom .xiaohongshu import XiaohongshuPluginfrom .xiaoyuzhou import XiaoyuzhouPluginfrom .youtube import YouTubePlugindef _instances() -> list[Plugin]:
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
        except Exception as exc:  # noqa: BLE001
            log.warning("插件 %s 实例化失败，已跳过：%s", cls.__name__, exc)
            continue
    return plugins


BUILTIN_PLUGINS: list[Plugin] = _instances()