"""主图：任务规划 + 子任务并发 + 汇总 + 真流式回复。

编译后的图挂载 Postgres checkpointer（中断态）与 Store（长期记忆）。
未注入 checkpointer 时使用进程内 MemorySaver，仅用于本地开发与测试。
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from homemind.agent.runtime.branches import chat_node, knowledge_node, report_node
from homemind.agent.runtime.control import build_control_subgraph
from homemind.agent.runtime.nodes import (
    aggregate,
    compose,
    input_guard,
    load_context,
    output_guard,
    persist,
    route_after_guard,
)
from homemind.agent.runtime.planner import (
    clarify,
    plan_node,
    route_after_clarify,
    route_after_plan,
)
from homemind.agent.runtime.state import AgentState

logger = logging.getLogger(__name__)

BRANCHES = ("chat", "knowledge", "control", "report")


def build_agent_graph(checkpointer=None, store=None):
    graph = StateGraph(AgentState)

    graph.add_node("input_guard", input_guard)
    graph.add_node("load_context", load_context)
    graph.add_node("planner", plan_node)
    graph.add_node("clarify", clarify)
    graph.add_node("chat", chat_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("control", build_control_subgraph())
    graph.add_node("report", report_node)
    graph.add_node("aggregate", aggregate)
    graph.add_node("compose", compose)
    graph.add_node("output_guard", output_guard)
    graph.add_node("persist", persist)

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard",
        route_after_guard,
        {"continue": "load_context", "blocked": "output_guard"},
    )
    graph.add_edge("load_context", "planner")
    graph.add_conditional_edges(
        "planner",
        route_after_plan,
        ["clarify", *BRANCHES],
    )
    graph.add_conditional_edges(
        "clarify",
        route_after_clarify,
        ["planner", "chat"],
    )
    for branch in BRANCHES:
        graph.add_edge(branch, "aggregate")

    graph.add_edge("aggregate", "compose")
    graph.add_edge("compose", "output_guard")
    graph.add_edge("output_guard", "persist")
    graph.add_edge("persist", END)

    return graph.compile(checkpointer=checkpointer, store=store)


_agent_app = None


def get_agent_app():
    """运行时单例：未注入持久化时使用进程内 MemorySaver。"""
    global _agent_app
    if _agent_app is None:
        _agent_app = build_agent_graph(checkpointer=MemorySaver())
    return _agent_app


def set_agent_app(app) -> None:
    global _agent_app
    _agent_app = app


async def reset_thread(app, thread_id: str) -> None:
    """清空上一轮 checkpoint，再开始新一轮对话。

    会话历史每轮都从数据库重新载入，checkpoint 只在本轮内承担中断恢复职责。
    保留旧 checkpoint 会让 `final_answer` 续用、`results`/`messages` 等
    reducer 字段跨轮累加（曾导致第二轮直接返回上一轮回复）。
    """
    checkpointer = getattr(app, "checkpointer", None)
    if checkpointer is None:
        return
    try:
        if hasattr(checkpointer, "adelete_thread"):
            await checkpointer.adelete_thread(thread_id)
        elif hasattr(checkpointer, "delete_thread"):
            checkpointer.delete_thread(thread_id)
    except Exception as exc:  # 清理失败不阻断本轮，但要能定位到残留状态
        logger.warning("清理会话 checkpoint 失败 %s: %s", thread_id, exc)
