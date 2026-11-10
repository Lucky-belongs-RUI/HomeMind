"""会话历史两级压缩。

超出 token 预算时不再丢弃旧轮次：

- 最近 6 轮原文保留，不参与压缩；
- 更早且尚未压缩的轮次做一级压缩（去冗余、精简语句）；
- 已有压缩片段做二级压缩（摘要抽取、强压缩）；
- 压缩结果以字符串数组持久化，`compressed_until_id` 标记已压缩边界。

这样下一轮只需加载边界之后的消息，既能区分“已压缩/未压缩”，
也避免每轮重复压缩整段历史。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from homemind.agent.runtime.context import estimate_tokens
from homemind.llm.langchain import build_router_model, message_text

logger = logging.getLogger(__name__)

KEEP_RECENT_TURNS = 6
LEVEL1_MAX_CHARS = 600
LEVEL2_MAX_CHARS = 400

LEVEL1_PROMPT = (
    "你在压缩智能家居会话上下文。请对下面“首次压缩”的较早对话做冗余抽取与语句精简：\n"
    "1. 删除寒暄、重复表达、语气词和模型解释性套话；\n"
    "2. 保留用户明确指令、设备与房间、参数数值、执行成功/失败、用户偏好、未完成事项；\n"
    "3. 保留理解后续指代所需的信息（谁、哪台设备、哪个房间）；\n"
    "4. 不得编造事实，不得补充建议；\n"
    f"5. 用紧凑中文条目输出，不超过 {LEVEL1_MAX_CHARS} 字；只输出压缩结果。"
)

LEVEL2_PROMPT = (
    "你在对“已经压缩过一次”的会话摘要做二级强压缩。请合并重复信息并抽取长期有效内容：\n"
    "1. 只保留稳定偏好、重要事实、未完成事项、关键设备状态变更；\n"
    "2. 丢弃一次性闲聊和已经过时的操作细节；\n"
    "3. 不得编造事实；\n"
    f"4. 用要点输出，不超过 {LEVEL2_MAX_CHARS} 字；只输出压缩结果。"
)

Compressor = Callable[[str, int], Awaitable[str]]


@dataclass
class HistoryWindow:
    """压缩后的上下文窗口。"""

    messages: list[BaseMessage]
    summary: str
    parts: list[str]
    compressed_until_id: int | None
    usage: dict[str, Any]
    compressed: bool


def join_parts(parts: list[str] | None) -> str:
    """把压缩片段按时间顺序拼成提示词里的摘要块。"""
    return "\n".join(str(part).strip() for part in parts or [] if str(part).strip())


def _truncate(text: str, limit: int) -> str:
    """保尾截断：越靠后的内容越接近最近对话。"""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return f"…{cleaned[-limit:]}"


def _group_turns(rows: list[tuple[int, BaseMessage]]) -> list[list[tuple[int, BaseMessage]]]:
    """按“用户发起一轮”分组，最近 N 轮以组为单位保留。"""
    groups: list[list[tuple[int, BaseMessage]]] = []
    for row in rows:
        if not groups or isinstance(row[1], HumanMessage):
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups


def _render_rows(rows: list[tuple[int, BaseMessage]]) -> str:
    lines = []
    for _, message in rows:
        role = "用户" if isinstance(message, HumanMessage) else "助手"
        lines.append(f"{role}：{message_text(message)}")
    return "\n".join(lines)


async def _compress_with_model(system_prompt: str, text: str, max_chars: int) -> str:
    model = build_router_model()
    response = await model.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=text)]
    )
    return _truncate(message_text(response), max_chars)


async def compress_level1(text: str, max_chars: int = LEVEL1_MAX_CHARS) -> str:
    """首次压缩：去冗余、精简语句。"""
    return await _compress_with_model(LEVEL1_PROMPT, text, max_chars)


async def compress_level2(text: str, max_chars: int = LEVEL2_MAX_CHARS) -> str:
    """二次压缩：对已有摘要做强压缩。"""
    return await _compress_with_model(LEVEL2_PROMPT, text, max_chars)


def _usage(
    *,
    messages: list[BaseMessage],
    summary: str,
    budget: int,
    turns: int,
    total_turns: int,
    compressed_turns: int,
    trigger_tokens: int,
    compressed: bool,
    part_count: int,
) -> dict[str, Any]:
    tokens = estimate_tokens(summary) + sum(
        estimate_tokens(message_text(message)) for message in messages
    )
    return {
        "estimated_tokens": tokens,
        "budget": budget,
        "messages": len(messages),
        "turns": turns,
        "total_turns": total_turns,
        "compressed_turns": compressed_turns,
        "compressed": compressed,
        "compressed_parts": part_count,
        "trigger_tokens": trigger_tokens,
    }


async def build_history_window(
    rows: list[tuple[int, BaseMessage]],
    current: BaseMessage,
    parts: list[str] | None,
    compressed_until_id: int | None,
    budget: int,
    *,
    keep_turns: int = KEEP_RECENT_TURNS,
    level1: Compressor | None = None,
    level2: Compressor | None = None,
) -> HistoryWindow:
    """按预算构造上下文窗口；超预算时压缩最近 N 轮之外的内容。"""
    budget = max(int(budget or 0), 1)
    parts = [str(part).strip() for part in parts or [] if str(part).strip()]
    groups = _group_turns(rows)
    split = max(len(groups) - max(int(keep_turns), 0), 0)
    older_groups = groups[:split]
    recent_groups = groups[split:]
    all_messages = [message for _, message in rows]
    summary = join_parts(parts)
    trigger_tokens = (
        estimate_tokens(summary)
        + sum(estimate_tokens(message_text(message)) for message in all_messages)
        + estimate_tokens(message_text(current))
    )

    if trigger_tokens <= budget or (not older_groups and not parts):
        messages = [*all_messages, current]
        return HistoryWindow(
            messages=messages,
            summary=summary,
            parts=parts,
            compressed_until_id=compressed_until_id,
            usage=_usage(
                messages=messages,
                summary=summary,
                budget=budget,
                turns=len(groups),
                total_turns=len(groups),
                compressed_turns=0,
                trigger_tokens=trigger_tokens,
                compressed=False,
                part_count=len(parts),
            ),
            compressed=False,
        )

    level1 = level1 or compress_level1
    level2 = level2 or compress_level2
    older_rows = [row for group in older_groups for row in group]

    new_part = ""
    if older_rows:
        older_text = _render_rows(older_rows)
        try:
            new_part = str(await level1(older_text, LEVEL1_MAX_CHARS) or "").strip()
        except Exception as exc:
            logger.warning("一级上下文压缩失败，改用保尾截断: %s", exc)
        if not new_part:
            new_part = _truncate(older_text, LEVEL1_MAX_CHARS)

    strong_part = ""
    if parts:
        try:
            strong_part = str(await level2(summary, LEVEL2_MAX_CHARS) or "").strip()
        except Exception as exc:
            logger.warning("二级上下文压缩失败，沿用已有摘要: %s", exc)
        strong_part = strong_part or summary

    new_parts = [part for part in (strong_part, new_part) if part]
    recent_messages = [message for group in recent_groups for _, message in group]
    messages = [*recent_messages, current]
    new_summary = join_parts(new_parts)
    return HistoryWindow(
        messages=messages,
        summary=new_summary,
        parts=new_parts,
        compressed_until_id=older_rows[-1][0] if older_rows else compressed_until_id,
        usage=_usage(
            messages=messages,
            summary=new_summary,
            budget=budget,
            turns=len(recent_groups),
            total_turns=len(groups),
            compressed_turns=len(older_groups),
            trigger_tokens=trigger_tokens,
            compressed=True,
            part_count=len(new_parts),
        ),
        compressed=True,
    )


__all__ = [
    "HistoryWindow",
    "KEEP_RECENT_TURNS",
    "build_history_window",
    "compress_level1",
    "compress_level2",
    "join_parts",
]
