"""集中凭证目录：声明每个数据源插件该如何完成第三方授权。

拆出来单独维护的原因：
1. 21 个内置插件的凭证散落在各自的 ``is_configured`` 里（``os.getenv(...)``），
   浏览器面板无法自动得知「需要什么凭证、属于哪种授权方式」。
2. 这里把凭证规格集中声明，面板即可据此自动渲染对应输入控件
   （API Key / Cookie / OAuth / 扫码 / 文件路径 / URL 列表），
   保存时写入 ``.env`` 的对应键，并可做一次连通性验证。

插件自己在 ``PluginMeta.credentials`` 里声明的规格**优先**于本目录，
便于新插件内聚地把凭证写在自己文件里。
"""
from __future__ import annotations

from .plugin import CredentialSpec, CredentialType

T = CredentialType

# plugin_id -> 该插件完成授权所需的凭证（按顺序展示）
PLUGIN_CREDENTIALS: dict[str, tuple[CredentialSpec, ...]] = {
    # ---- Token / API Key 类 ----
    "weread": (
        CredentialSpec("WEREAD_API_KEY", "微信读书 Gateway API Key", T.API_KEY,
                       "以 wrk_ 开头，从微信读书 Gateway 获取。"),
    ),
    "toggl": (
        CredentialSpec("TOGGL_API_TOKEN", "Toggl API Token", T.API_KEY,
                       "Toggl 网页版 → 个人设置 → API Token。"),
    ),
    "trakt": (
        CredentialSpec("TRAKT_CLIENT_ID", "Trakt Client ID", T.API_KEY,
                       "Trakt 应用设置里的 Client ID。"),
        CredentialSpec("TRAKT_TOKEN", "Trakt Access Token", T.OAUTH,
                       "OAuth 授权后获得的 access token。"),
    ),
    # ---- OAuth 类 ----
    "github": (
        CredentialSpec("GH_TOKEN", "GitHub Token", T.OAUTH,
                       "Personal Access Token（需 repo / read:user）；"
                       "或在插件「账号」页绑定 GitHub 自动填入。"),
    ),
    # ---- Cookie 类（浏览器复制）----
    "bilibili": (
        CredentialSpec("BILIBILI_EXPORT", "B站导出文件路径", T.FILE,
                       "B 站账号数据导出（JSON）的绝对路径。", secret=False),
    ),
    "douban": (
        CredentialSpec("DOUBAN_BOOK_URLS", "豆瓣书目 URL", T.URLS,
                       "多个 https://book.douban.com/subject/XXXX/ 用英文逗号分隔"
                       "（抓取公开页面，无需登录）。", secret=False),
    ),
    # ---- 扫码类（通常由配套导出脚本产出凭证）----
    "douyin": (
        CredentialSpec("DOUYIN_COOKIE", "抖音 Cookie / 扫码凭证", T.QRCODE,
                       "用手机抖音扫码登录后由配套脚本导出，或手动复制 Cookie。"),
    ),
    # 注：xiaohongshu 的凭证声明统一放在文件末尾「原云端集成补齐的自托管插件」
    # 段落中（同时含 XIAOHONGSHU_EXPORT 与可选的 XIAOHONGSHU_COOKIE）。
    # 此处不再重复声明——Python 字典字面量的重复键会静默覆盖，容易踩坑。
    # ---- 本地导出文件（多为各平台官方导出 / 第三方脚本产出）----
    "douyin_export": (
        CredentialSpec("DOUYIN_EXPORT", "抖音导出文件路径", T.FILE,
                       "导出 JSON 的绝对路径。", secret=False),
    ),
    "youtube": (
        CredentialSpec("YOUTUBE_EXPORT", "YouTube 导出文件路径", T.FILE,
                       "Google Takeout / yt-dlp 导出的 JSON 路径。",
                       required=False, secret=False),
        CredentialSpec("YOUTUBE_API_KEY", "YouTube Data API Key", T.API_KEY,
                       "使用在线拉取时需填 Google Cloud API Key。",
                       required=False),
    ),
    "flomo": (
        CredentialSpec("FLOMO_EXPORT", "Flomo 导出文件路径", T.FILE,
                       "Flomo 网页端导出的 JSON 路径。", secret=False),
    ),
    "telegram": (
        CredentialSpec("TELEGRAM_EXPORT", "Telegram 导出 result.json 路径", T.FILE,
                       "Telegram Desktop 导出后的 result.json。", secret=False),
    ),
    "keep": (
        CredentialSpec("KEEP_EXPORT", "Keep 导出文件路径", T.FILE,
                       "Google Takeout 中 Keep 的 JSON 路径。", secret=False),
    ),
    "forest": (
        CredentialSpec("FOREST_EXPORT", "Forest 导出文件路径", T.FILE,
                       "Forest 导出的 CSV / JSON 路径。", secret=False),
    ),
    "ticktick": (
        CredentialSpec("TICKTICK_EXPORT", "滴答清单导出文件路径", T.FILE,
                       "滴答清单导出的 CSV 路径。", secret=False),
    ),
    "duolingo": (
        CredentialSpec("DUOLINGO_EXPORT", "多邻国导出文件路径", T.FILE,
                       "多邻国数据导出的 JSON 路径。", secret=False),
    ),
    "dayone": (
        CredentialSpec("DAYONE_EXPORT", "Day One 导出文件路径", T.FILE,
                       "Day One 导出的 JSON 路径。", secret=False),
    ),
    "gutu": (
        CredentialSpec("GUTU_EXPORT", "古文岛导出文件路径", T.FILE,
                       "古文岛导出的 JSON 路径。", secret=False),
    ),
    "netease": (
        CredentialSpec("NETEASE_PLAYLIST", "网易云歌单 JSON 路径", T.FILE,
                       "网易云音乐歌单导出的 JSON 路径。", secret=False),
    ),
    "applemusic": (
        CredentialSpec("APPLEMUSIC_EXPORT", "Apple Music 导出文件路径", T.FILE,
                       "Apple Music 资料库导出的 JSON 路径。", secret=False),
    ),
    "beidanci": (
        CredentialSpec("BEIDANCI_EXPORT", "百词斩导出文件路径", T.FILE,
                       "百词斩导出的 JSON 路径。", secret=False),
    ),
    # ---- URL 列表类 ----
    "rss": (
        CredentialSpec("RSS_FEEDS", "RSS 订阅地址", T.URLS,
                       "多个 feed 用英文逗号分隔。", secret=False),
    ),
    "xiaoyuzhou": (
        CredentialSpec("XIAOYUZHOU_FEEDS", "小宇宙播客 feed 地址", T.URLS,
                       "多个播客 RSS 用英文逗号分隔。", secret=False),
    ),
    # ---- 新增：原云端集成补齐的自托管插件凭证 ----
    "spotify": (
        CredentialSpec("SPOTIFY_TOKEN", "Spotify Access Token", T.OAUTH,
                       "OAuth 授权后的 access token。", required=False),
        CredentialSpec("SPOTIFY_CLIENT_ID", "Spotify Client ID", T.API_KEY,
                       "开发者后台应用凭证。", required=False),
        CredentialSpec("SPOTIFY_CLIENT_SECRET", "Spotify Client Secret", T.API_KEY,
                       "与 Client ID 配对。", required=False, secret=True),
    ),
    "strava": (
        CredentialSpec("STRAVA_TOKEN", "Strava Access Token", T.OAUTH,
                       "Strava API access token（需 activity:read）。"),
    ),
    "weibo": (
        CredentialSpec("WEIBO_UID", "微博 UID", T.API_KEY,
                       "微博用户数字 ID（m.weibo.cn/u/<UID>）。"),
        CredentialSpec("WEIBO_COOKIE", "微博 Cookie（可选）", T.COOKIE,
                       "登录后复制 Cookie，提升抓取稳定性。", required=False),
    ),
    "xiaohongshu": (
        CredentialSpec("XIAOHONGSHU_EXPORT", "小红书导出文件路径", T.FILE,
                       "导出 JSON 的绝对路径。", secret=False),
        CredentialSpec("XIAOHONGSHU_COOKIE", "小红书 Cookie（可选）", T.COOKIE,
                       "在线抓取反爬严格，推荐改用本地导出。", required=False),
    ),
    "jike": (
        CredentialSpec("JIKE_EXPORT", "即刻导出文件路径", T.FILE,
                       "导出 JSON 的绝对路径。", secret=False),
        CredentialSpec("JIKE_COOKIE", "即刻 Cookie（可选）", T.COOKIE,
                       "在线抓取已不稳定，推荐改用本地导出。", required=False),
    ),
    "podcast": (
        CredentialSpec("PODCAST_OPML", "OPML 订阅文件路径", T.FILE,
                       "播客 App 导出的 OPML 绝对路径。", secret=False),
    ),
    "applepodcast": (
        CredentialSpec("APPLEPODCAST_OPML", "Apple 播客 OPML 路径", T.FILE,
                       "Apple 播客导出的 OPML 绝对路径。", secret=False),
    ),
    "daily": (
        CredentialSpec("DAILY_NOTES_DIR", "日记目录路径", T.FILE,
                       "按 YYYY-MM-DD 命名的 .md/.json 文件目录。", secret=False),
    ),
    "daily-weather": (
        CredentialSpec("DAILY_WEATHER_LOCATION", "经纬度 (lat,lon)", T.API_KEY,
                       "例如 39.9042,116.4074（北京）。", secret=False),
    ),
    "daily-location": (
        CredentialSpec("DAILY_LOCATION_LOCATION", "经纬度 (lat,lon)", T.API_KEY,
                       "例如 31.2304,121.4737（上海）。", secret=False),
    ),
    "guwendao": (
        CredentialSpec("GUWENDAO_EXPORT", "古文岛导出文件路径", T.FILE,
                       "导出 JSON 的绝对路径。", secret=False),
    ),
    "fix": (),
}

# 部分插件 id 与其「导出源」id 不同名，做一层别名映射，
# 让面板能把导出行归并到对应插件卡片上。
_EXPORT_ALIAS = {
    "douyin": ("douyin_export",),
}


def credentials_for(plugin_id: str) -> tuple[CredentialSpec, ...]:
    """返回某插件的凭证规格（含导出别名）。"""
    specs = list(PLUGIN_CREDENTIALS.get(plugin_id, ()))
    for alias in _EXPORT_ALIAS.get(plugin_id, ()):
        specs.extend(PLUGIN_CREDENTIALS.get(alias, ()))
    return tuple(specs)


def all_credentials() -> dict[str, list[dict]]:
    """返回全部插件的凭证规格字典，供面板一次性拉取。"""
    return {
        pid: [s.to_dict() for s in credentials_for(pid)]
        for pid in PLUGIN_CREDENTIALS
    }


# ---------------------------------------------------------------- 凭证验证
# 面板保存凭证后应能立刻知道「填得对不对」，而不必等到同步时才失败。

def _check_file(value: str) -> tuple[bool, str]:
    from pathlib import Path
    if not value.strip():
        return False, "路径为空"
    if not Path(value).exists():
        return False, f"文件不存在：{value}"
    return True, "文件存在"


def _check_urls(value: str) -> tuple[bool, str]:
    items = [u.strip() for u in value.split(",") if u.strip()]
    if not items:
        return False, "未填写任何地址"
    bad = [u for u in items if not (u.startswith("http://") or u.startswith("https://"))]
    if bad:
        return False, "以下地址格式不正确：" + "、".join(bad[:3])
    return True, f"已填写 {len(items)} 个地址"


def _check_key(value: str) -> tuple[bool, str]:
    v = value.strip()
    if len(v) < 8:
        return False, "内容过短，可能填写不完整"
    return True, "格式基本正常"


def _check_cookie(value: str) -> tuple[bool, str]:
    v = value.strip()
    if "=" not in v:
        return False, "Cookie 应形如 key=value; key2=value2"
    if len(v) < 16:
        return False, "Cookie 过短，请确认已完整复制"
    return True, "格式基本正常"


_CHECKERS = {
    T.FILE: _check_file,
    T.URLS: _check_urls,
    T.COOKIE: _check_cookie,
    T.API_KEY: _check_key,
    T.OAUTH: _check_key,
    T.QRCODE: _check_cookie,
}


def verify_credential(cred_type: str, value: str) -> dict:
    """对单个凭证做本地可判定的校验，返回 {ok, message}。

    只做「无需联网即可确定」的检查；真正鉴权是否通过，
    仍以插件的 ``health()`` / 实际同步为准。
    """
    try:
        t = CredentialType(cred_type)
    except ValueError:
        return {"ok": False, "message": f"未知授权类型：{cred_type}"}
    if not (value or "").strip():
        return {"ok": False, "message": "未填写"}
    ok, message = _CHECKERS[t](value)
    return {"ok": ok, "message": message, "cred_type": t.value}
