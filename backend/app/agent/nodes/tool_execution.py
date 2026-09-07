"""工具调用节点：执行已批准任务并收集结果。"""
import json
import logging

from app.agent.tools.device_tools import execute_tool
from app.services.conversation_service import save_conversation
from app.agent.nodes._base import log_node_run

logger = logging.getLogger(__name__)


@log_node_run
async def tool_execution_node(state: dict) -> dict:
    """遍历 approved 任务执行工具；权限校验由工具内部完成。"""
    state = dict(state)
    tasks = state.get("tasks", [])
    results = []

    for task in tasks:
        task_id = task.get("task_id", "")
        description = task.get("description", "")
        if task.get("status") != "approved":
            if task.get("needs_approval"):
                results.append(
                    {
                        "task_id": task_id,
                        "status": "skipped",
                        "description": description,
                        "data": {"success": False, "error": "用户未勾选该任务"},
                    }
                )
            continue

        tool_name = task.get("tool_name")
        if not tool_name:
            results.append(
                {
                    "task_id": task_id,
                    "status": "skipped",
                    "description": description,
                    "data": {"success": True, "message": "无需工具调用"},
                }
            )
            continue

        try:
            result = await execute_tool(
                tool_name=tool_name,
                arguments=task.get("arguments", {}),
                user_id=state["user_id"],
                user_role=state["user_role"],
                family_id=state["family_id"],
            )
        except Exception as exc:  # 单任务异常不影响其他任务
            logger.warning("工具执行异常 %s: %s", tool_name, exc)
            result = {"success": False, "error": f"工具执行异常: {exc}"}

        if result.get("success"):
            results.append(
                {
                    "task_id": task_id,
                    "status": "success",
                    "description": description,
                    "message": result.get("message", ""),
                    "data": result,
                }
            )
        else:
            results.append(
                {
                    "task_id": task_id,
                    "status": "failed",
                    "description": description,
                    "error": result.get("error", "未知错误"),
                    "data": result,
                }
            )

        result_text = json.dumps(result, ensure_ascii=False)
        state["messages"].append(
            {
                "role": "tool",
                "content": result_text,
                "tool_call_id": task_id,
                "name": tool_name,
            }
        )
        await save_conversation(
            family_id=state["family_id"],
            user_id=state["user_id"],
            session_id=state["session_id"],
            role="tool",
            content=result_text,
            tool_call_id=task_id,
            tool_name=tool_name,
        )

    state["tool_results"] = results
    chain_results = dict(state.get("chain_results") or {})
    chain_results["control"] = {"tool_results": results}
    state["chain_results"] = chain_results
    return state