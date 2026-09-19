"""版本号必须在四处保持一致：pyproject.toml、manifest.json、package.json 与 __init__.py。

CHANGELOG 的最新条目也要对得上，否则会出现「改了代码忘了改版本」或
「CHANGELOG 写了 v2.12 但扩展还是 2.8」这类漂移。
"""

import json
import re
from pathlib import Path

from weread2notion import __version__

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml 中未找到 version"
    return match.group(1)


def _json_version(name: str) -> str:
    data = json.loads((ROOT / name).read_text(encoding="utf-8"))
    return data["version"]


def _changelog_latest() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^##\s+v([0-9][0-9A-Za-z.\-]*)\b", text, re.MULTILINE)
    assert match, "CHANGELOG.md 中未找到版本条目"
    return match.group(1)


def test_version_consistent_across_manifests():
    assert _pyproject_version() == __version__
    assert _json_version("manifest.json") == __version__
    assert _json_version("package.json") == __version__


def test_changelog_latest_matches_package_version():
    assert _changelog_latest() == __version__


def test_version_is_semver_like():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__
