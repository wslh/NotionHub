"""NotionHub: connect your digital life to Notion through a plugin hub."""

# 与 pyproject.toml / manifest.json / package.json 保持一致（发版时四处同步）。
# 不采用 importlib.metadata 动态读取：editable 安装的元数据会停留在安装时的
# 旧版本，环境无法重装时反而给出错误答案。
__version__ = "2.12.0"

from .plugin import Category, Plugin, PluginContext, PluginMeta, SyncResult
from .plugins import BUILTIN_PLUGINS
from .registry import PluginRegistry, build_default_registry
from .runner import run_plugin

__all__ = [
    "Category", "Plugin", "PluginContext", "PluginMeta", "SyncResult",
    "PluginRegistry", "build_default_registry", "run_plugin", "BUILTIN_PLUGINS",
    "__version__",
]
