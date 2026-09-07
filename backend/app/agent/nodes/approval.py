"""中断审批节点：普通模式等待用户勾选确认，高级模式自动跳过。"""
from app.agent.nodes._base import extract_decision, is_interrupted, log_node_run, wait_user


def _approval_payload(state: dict) -> dict:
    tasks = [
        {
            "task_id": task["task_id"],
            "description": task.get("description", ""),
            "tool_name": task.get("tool_name", ""),
            "arguments": task.get("arguments", {}),
            "expected_effect": task.get("expected_effect", ""),
            "risk_level": task.get("risk_level", "low"),
        }
        for task in state.get("tasks", [])
        if task.get("needs_approval")
    ]
    risk_levels = {task.get("risk_level") for task in tasks}
    risk_level = "high" if "high" in risk_levels else ("medium" if "medium" in risk_levels else "low")
    return {
        "type": "approval",
        "tasks": tasks,
        "risk_level": risk_level,
        "thread_id": state.get("thread_id", ""),
    }


@log_node_run
async def approval_node(state: dict) -> dict:
    """检查权限模式并执行审批中断。"""
    state = dict(state)
    tasks = state.get("tasks", [])
    approval_tasks = [task for task in tasks if task.get("needs_approval")]

    if state.get("permission_mode") == "high" or not approval_tasks:
        state["approval_granted"] = True
        state["approved_task_ids"] = [task["task_id"] for task in tasks]
        for task in tasks:
            task["status"] = "approved"
        return state

    resume_data = wait_user(state, _approval_payload(state))
    if is_interrupted(state):
        return state

    decision = extract_decision(resume_data)
    approved = bool(decision.get("approved", True))
    approved_ids = decision.get("task_ids") or []

    state["approval_granted"] = approved
    chain_results = dict(state.get("chain_results") or {})
    if not approved:
        for task in tasks:
            if task.get("needs_approval"):
                task["status"] = "skipped"
        chain_results["control"] = {"cancelled": True, "message": "好的，已取消本次操作。"}
        state["chain_results"] = chain_results
        state["avatar_emotion"] = "idle"
        return state

    approved_set = set(str(item) for item in approved_ids)
    state["approved_task_ids"] = list(approved_set)
    for task in tasks:
        if not task.get("needs_approval"):
            task["status"] = "approved"
        elif task["task_id"] in approved_set:
            task["status"] = "approved"
        else:
            task["status"] = "skipped"
    state["chain_results"] = chain_results
    return state