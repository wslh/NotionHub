"""GitHub Stars plugin: fetches the authenticated user starred repos into Notion."""
from __future__ import annotationsimport osfrom typing import Anyimport requestsfrom ..plugin import Category, CredentialSpec, CredentialType, PluginMetafrom .base import BasePlugin_API = "https://api.github.com/user/starred"


def _fetch_stars(token: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    items: list[dict[str, Any]] = []
    url: str | None = _API
    while url:
        resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=20)
        resp.raise_for_status()
        items.extend(resp.json())
        link = resp.headers.get("Link", "")
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part[part.find("<") + 1 : part.find(">")]
                break
    return items


class GithubPlugin(BasePlugin):
    """GitHub Star 同步：把已 Star 的仓库 upsert 到 Notion。"""

    DB_NAME = "GitHub Stars"
    TITLE_PROP = "仓库"
    KEY_PROP = "仓库"
    SCHEMA = {
        "仓库": {"title": {}},
        "描述": {"rich_text": {}},
        "链接": {"url": {}},
        "语言": {"select": {"options": []}},
        "Stars": {"number": {"format": "number"}},
        "话题": {"multi_select": {"options": []}},
        "推送时间": {"date": {}},
    }

    meta = PluginMeta(
        id="github",
        name="GitHub Stars",
        category=Category.PRODUCTIVITY,
        description="把 GitHub Star 仓库同步到 Notion，便于回顾与分类。",
        docs_url="https://github.com/wslh/NotionHub#github",
        icon="⭐",
        credentials=(
            CredentialSpec(
                env_key="GH_TOKEN",
                label="GitHub Personal Access Token",
                cred_type=CredentialType.OAUTH,
                hint="需要 repo / read:user 权限。也可在插件「账号」页绑定 GitHub 自动填入。",
            ),
        ),
    )

    def is_configured(self) -> bool:
        return bool(os.getenv("GH_TOKEN"))

    def _items(self, ctx):
        for repo in _fetch_stars(os.environ["GH_TOKEN"]):
            full_name = repo.get("full_name") or ""
            raw = {
                "仓库": full_name,
                "描述": (repo.get("description") or "")[:1900],
                "链接": repo.get("html_url") or "",
                "Stars": int(repo.get("stargazers_count") or 0),
            }
            lang = repo.get("language")
            if lang:
                raw["语言"] = {"select": {"name": lang}}
            topics = repo.get("topics") or []
            if topics:
                raw["话题"] = {"multi_select": [{"name": t} for t in topics]}
            pushed = repo.get("pushed_at")
            if pushed:
                raw["推送时间"] = {"date": {"start": pushed}}
            yield full_name, raw
