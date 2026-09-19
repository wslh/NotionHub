"""自托管补齐插件的契约测试。

这 12 个插件原先是 NotionHub 云端集成（拉外部仓库运行），现改为本仓库
自托管插件。这里锁定三件容易回归的事：

1. 它们确实注册进了默认注册表；
2. 它们满足 ``Plugin`` 协议 —— 缺任何一个必需方法（例如 ``discover``）
   都会让 ``PluginRegistry.register`` 抛 TypeError，进而拖垮整个注册表；
3. 未配置凭证时安全跳过，不抛异常。
"""
from __future__ import annotations

import pytest

from weread2notion.plugin import Plugin
from weread2notion.plugins import BUILTIN_PLUGINS
from weread2notion.registry import build_default_registry

# 插件 id -> 触发其“已配置”所需的凭证环境变量（空元组 = 只依赖 NOTION_TOKEN）
SELF_HOSTED_PLUGINS = {
    "spotify": ("SPOTIFY_TOKEN",),
    "strava": ("STRAVA_TOKEN",),
    "weibo": ("WEIBO_UID",),
    "xiaohongshu": ("XIAOHONGSHU_EXPORT",),
    "jike": ("JIKE_EXPORT",),
    "podcast": ("PODCAST_OPML",),
    "applepodcast": ("APPLEPODCAST_OPML",),
    "daily": ("DAILY_NOTES_DIR",),
    "daily-weather": ("DAILY_WEATHER_LOCATION",),
    "daily-location": ("DAILY_LOCATION_LOCATION",),
    "guwendao": ("GUWENDAO_EXPORT",),
    "fix": (),
}


def test_registry_builds_with_self_hosted_plugins():
    registry = build_default_registry()
    ids = [p.meta.id for p in registry]
    missing = [pid for pid in SELF_HOSTED_PLUGINS if pid not in ids]
    assert missing == [], f"未注册：{missing}；实际：{ids}"


@pytest.mark.parametrize("plugin", BUILTIN_PLUGINS, ids=[p.meta.id for p in BUILTIN_PLUGINS])
def test_every_plugin_satisfies_protocol(plugin):
    """注册表的 isinstance(p, Plugin) 校验：缺方法会直接拒绝注册。"""
    assert isinstance(plugin, Plugin)
    for method in ("is_configured", "setup", "discover", "sync", "health"):
        assert callable(getattr(plugin, method, None)), f"{plugin.meta.id} 缺少 {method}()"


@pytest.mark.parametrize("plugin_id", sorted(SELF_HOSTED_PLUGINS))
def test_unconfigured_self_hosted_plugin_is_skipped(plugin_id, monkeypatch):
    from weread2notion.runner import run_plugin

    for env_key in SELF_HOSTED_PLUGINS[plugin_id]:
        monkeypatch.delenv(env_key, raising=False)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)

    plugin = next(p for p in BUILTIN_PLUGINS if p.meta.id == plugin_id)
    assert plugin.is_configured() is False

    result = run_plugin(plugin, notion=None, settings=object())
    assert result.skipped == 1
    assert result.errors == 0


def test_fix_plugin_needs_only_notion_token(monkeypatch):
    plugin = next(p for p in BUILTIN_PLUGINS if p.meta.id == "fix")
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    assert plugin.is_configured() is False
    monkeypatch.setenv("NOTION_TOKEN", "ntn_dummy_token_value")
    assert plugin.is_configured() is True


def test_discover_does_not_require_configured_credentials(monkeypatch):
    """discover 是协议成员，应存在且可调用（非数据源类插件返回空列表）。"""
    plugin = next(p for p in BUILTIN_PLUGINS if p.meta.id == "fix")
    assert plugin.discover(None) == []


# 全局 Notion 连接凭证，不属于任何单个数据源插件
_GLOBAL_ENV = {"NOTION_TOKEN", "NOTION_PAGE", "STORAGE_ENDPOINT"}


def _env_vars_read_by(plugin) -> set[str]:
    """静态扫描插件类的源码，取出它 os.getenv/os.environ 读取的环境变量名。"""
    import inspect
    import re

    try:
        src = inspect.getsource(type(plugin))
    except OSError:  # pragma: no cover - 源码不可得时跳过
        return set()
    found = re.findall(r"os\.(?:getenv|environ(?:\.get)?)\(\s*[\"']([A-Z0-9_]+)", src)
    return {e for e in found if e not in _GLOBAL_ENV}


@pytest.mark.parametrize("plugin", BUILTIN_PLUGINS, ids=[p.meta.id for p in BUILTIN_PLUGINS])
def test_declared_credentials_match_code(plugin):
    """credentials.py 声明的 env_key 必须与插件真正读取的环境变量对得上。

    历史坑：``douban`` 声明 ``DOUBAN_COOKIE`` 而代码读 ``DOUBAN_BOOK_URLS``、
    ``bilibili`` 声明 ``BILIBILI_COOKIE`` 而代码读 ``BILIBILI_EXPORT``。
    结果是面板让用户填一个插件永远不会读的值，同步永远被跳过且看不出原因。
    这里把两者钉在一起，防止再漂移。
    """
    from weread2notion.credentials import credentials_for

    read = _env_vars_read_by(plugin)
    if not read:
        pytest.skip(f"{plugin.meta.id} 未直接读取环境变量（如通过类属性间接取）")
    declared = {c.env_key for c in credentials_for(plugin.meta.id)}
    assert declared & read, (
        f"{plugin.meta.id}: credentials.py 声明 {sorted(declared)}，"
        f"但代码实际读取 {sorted(read)}——两者无交集，面板会收集到无效凭证"
    )
