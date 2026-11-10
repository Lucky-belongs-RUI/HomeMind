"""上下文工具：历史格式化、用户画像渲染与 token 粗估。

会话历史在请求入口从数据库载入，超预算时由 `compression.py` 做两级压缩，
不再直接丢弃旧轮次：

- `format_recent_history`：给意图路由/控制规划器一段短历史，用于消解指代；
- `render_profile`：把偏好画像渲染成提示词里的独立块。

token 用字符近似（中文 1 字≈1 token，其他 4 字符≈1 token），不引入 tokenizer。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage

_ROLE_LABELS = {
    "human": "用户",
    "user": "用户",
    "ai": "助手",
    "assistant": "助手",
}


def estimate_tokens(text: str) -> int:
    """粗估 token 数，宁可估大。"""
    if not text:
        return 0
    chinese = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return chinese + (len(text) - chinese + 3) // 4


def _role(message: Any) -> str:
    value = getattr(message, "type", "") or getattr(message, "role", "")
    return _ROLE_LABELS.get(str(value), "")


def _content(message: Any) -> str:
    return str(getattr(message, "content", "") or "").strip()


def history_without_current(messages: list[Any], user_input: str) -> list[Any]:
    """去掉最后一条“本轮用户输入”，避免把当前问题又当成历史。"""
    items = list(messages or [])
    text = str(user_input or "").strip()
    if (
        items
        and text
        and isinstance(items[-1], HumanMessage)
        and _content(items[-1]) == text
    ):
        return items[:-1]
    return items


def format_recent_history(messages: list[Any], max_chars: int = 600) -> str:
    """把最近对话渲染成短文本，供路由/规划理解指代；超出上限时从最旧处截断。"""
    if not messages:
        return ""

    lines: list[str] = []
    used = 0
    for message in reversed(messages):
        role = _role(message)
        content = _content(message)
        if not role or not content:
            continue
        if len(content) > max_chars:
            content = f"{content[:max_chars]}…"
        line = f"{role}：{content}"
        if lines and used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(reversed(lines))


def render_profile(profile: dict[str, Any] | None, max_chars: int = 500) -> str:
    """把偏好画像渲染成“- 键：值”的文本；空画像返回空串。"""
    if not isinstance(profile, dict) or not profile:
        return ""

    lines: list[str] = []
    for key, value in profile.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            text = "、".join(str(item) for item in value if item not in (None, ""))
        elif isinstance(value, dict):
            text = json.dumps(value, ensure_ascii=False, default=str)
        else:
            text = str(value)
        text = text.strip()
        if text:
            lines.append(f"- {key}：{text}")

    rendered = "\n".join(lines)
    if len(rendered) > max_chars:
        return f"{rendered[:max_chars]}…"
    return rendered


__all__ = [
    "estimate_tokens",
    "history_without_current",
    "format_recent_history",
    "render_profile",
]
