"""Agent 核心：工具集导出；状态图采用惰性加载避免与 llm 层循环导入。"""
from app.agent.tools.device_tools import (
    TOOL_DEFINITIONS,
    execute_tool,
    get_tool_definitions,
)

__all__ = [
    "MAX_ITERATIONS",
    "agent_app",
    "TOOL_DEFINITIONS",
    "execute_tool",
    "get_tool_definitions",
]


def __getattr__(name):
    """延迟加载 graph 相关导出，只有显式使用才构建状态图。"""
    if name == "agent_app":
        from app.agent.graph import agent_app
        return agent_app
    if name == "MAX_ITERATIONS":
        from app.agent.graph import MAX_ITERATIONS
        return MAX_ITERATIONS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")