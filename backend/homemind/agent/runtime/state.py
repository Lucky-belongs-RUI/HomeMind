"""图状态定义。

并发安全的关键：并行分支使用 `Send` 获得独立的 BranchState，
只允许往 `results` / `tool_events` 追加结果，不写共享标量。
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


def merge_dict(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """并发写入字典字段时做浅合并（右侧优先）。"""
    return {**(left or {}), **(right or {})}


def merge_emotion(left: str | None, right: str | None) -> str:
    """并发分支不直接写情绪；这里仅保留后写非空值，最终由 aggregate 裁决。"""
    return right or left or "idle"


class RequestContext(TypedDict, total=False):
    """一次请求的可信身份上下文，全部由服务端鉴权结果填充。"""

    user_id: int
    family_id: int
    role: str
    session_id: str
    thread_id: str
    trace_id: str
    provider: str
    model: str
    permission_mode: str


class AgentState(TypedDict, total=False):
    """主图状态。"""

    request: RequestContext
    user_input: str
    messages: Annotated[list[AnyMessage], add_messages]
    profile: dict[str, Any]
    profile_text: str
    history_text: str
    history_summary: str
    context_usage: dict[str, Any]
    house_snapshot: dict[str, Any] | None
    plan: dict[str, Any] | None
    clarification: dict[str, Any] | None
    results: Annotated[list[dict[str, Any]], add]
    tool_events: Annotated[list[dict[str, Any]], add]
    token_usage: Annotated[dict[str, Any], merge_dict]
    final_answer: str | None
    avatar_emotion: Annotated[str, merge_emotion]
    degraded: bool
    blocked: bool
    error: str | None
    clarification_attempts: int
    trace_id: str


class BranchState(TypedDict, total=False):
    """子图输入：由主图通过 Send 注入，分支之间互不共享。"""

    request: RequestContext
    query: str
    task: dict[str, Any]
    profile: dict[str, Any]
    profile_text: str
    history_text: str
    house_snapshot: dict[str, Any] | None
    messages: Annotated[list[AnyMessage], add_messages]
    results: Annotated[list[dict[str, Any]], add]
    tool_events: Annotated[list[dict[str, Any]], add]
    token_usage: Annotated[dict[str, Any], merge_dict]


class BranchOutput(TypedDict, total=False):
    """子图对外输出：只允许追加结果，避免并行分支回写 request 等共享标量。

    LangGraph 把子图当节点时会返回子图完整状态；若不裁剪，多个 Send
    分支同时写 `request` 会触发 InvalidUpdateError。
    """

    results: Annotated[list[dict[str, Any]], add]
    tool_events: Annotated[list[dict[str, Any]], add]
    token_usage: Annotated[dict[str, Any], merge_dict]


class ControlState(BranchState, total=False):
    """设备控制子图状态。"""

    tasks: list[dict[str, Any]]
    plan_ready: bool
    policy_action: str  # allow / approval / deny
    policy_reason: str
    approval_granted: bool
    approved_task_ids: list[str]
    observations: Annotated[list[dict[str, Any]], add]
    retry_count: int
    last_error: str | None
