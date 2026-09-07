"""结果汇总节点：聚合多链路执行结果，统计工具执行情况。"""
from typing import Any, Dict, List

from app.agent.nodes._base import log_node_run


@log_node_run
async def result_aggregation_node(state: dict) -> dict:
    """分类统计成功/失败/跳过任务数，并整理链路结果供回复生成使用。"""
    state = dict(state)
    results: List[Dict[str, Any]] = state.get("tool_results", [])
    state["success_count"] = sum(1 for item in results if item.get("status") == "success")
    state["failure_count"] = sum(1 for item in results if item.get("status") == "failed")
    state["skipped_count"] = sum(1 for item in results if item.get("status") == "skipped")
    state.setdefault("chain_results", {})
    return state
