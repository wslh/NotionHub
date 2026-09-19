"""可选的 AI 书摘摘要（智能化）。

仅当环境变量 OPENAI_API_KEY（或兼容端点 OPENAI_BASE_URL）存在时启用。
无密钥时所有函数安全返回 None，主流程不受影响（优雅降级）。
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

PROMPT = (
    "你是一名阅读助手。请基于以下书籍的划线与想法，生成一段不超过 150 字的"
    "中文导读，概括核心主题与值得关注的要点。只输出导读正文，不要解释。\n\n"
    "书名：{title}\n\n内容：\n{content}"
)


def _client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        log.warning("未安装 openai 库，跳过 AI 摘要（pip install openai）")
        return None
    base_url = os.getenv("OPENAI_BASE_URL")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def summarize_book(title: str, highlights: list[str], model: str | None = None) -> str | None:
    """为单本书生成 AI 导读。无密钥或失败时返回 None。"""
    client = _client()
    if not client:
        return None
    content = "\n".join(f"- {h}" for h in highlights[:40]) or "（无划线）"
    try:
        resp = client.chat.completions.create(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": PROMPT.format(title=title, content=content)}],
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception as exc:  # noqa: BLE001 - AI 为增强能力，失败不影响同步
        log.warning("AI 摘要生成失败：%s", exc)
        return None
