"""设备控制子图：规划 → 校验 → 策略门禁 → 审批 → 执行 → 观察 → 验证 → 反思。

外层规划器只负责判定“这一轮有设备任务”，具体工具调用由本子图内的
有界 ReAct 循环完成：模型选工具、策略校验、观察结果、失败重规划。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from homemind.agent.house_status import build_house_status_text
from homemind.agent.rules.plan import SCENE_NAMES, control_tasks
from homemind.agent.runtime.policy import decide_tool, idempotency_key
from homemind.agent.runtime.schemas import ApprovalDecision, BranchResult, TaskSpec
from homemind.agent.runtime.state import BranchOutput, ControlState
from homemind.agent.tools.langchain_tools import TOOLS_BY_NAME
from homemind.core.config import settings
from homemind.llm.langchain import build_chat_model

logger = logging.getLogger(__name__)

# 控制子图可执行的工具白名单；规划器通过 bind_tools 只看到这些工具。
CONTROL_TOOL_NAMES = (
    "set_device_state",
    "get_device_state",
    "list_room_devices",
    "trigger_scene",
    "get_current_time",
    "get_weather",
)
CONTROL_TOOLS = [TOOLS_BY_NAME[name] for name in CONTROL_TOOL_NAMES]

PLANNER_SYSTEM = """你是智能家居任务规划器。可用工具已通过 function calling 绑定，请直接调用工具，不要输出文字计划。

规则：
1. 只调用已绑定的工具，禁止臆造工具名（如 control_device）。
2. 设备控制必须同时给出 room_name 与 device_type，attributes 不能为空。
3. 场景触发使用 trigger_scene，参数为 scene_name。
4. 查询设备状态使用 get_device_state；查询房间设备使用 list_room_devices。
5. “调高/调低/再低一点”等相对指令，必须参考全屋状态中的当前值计算目标值。
6. 无法从指令确定具体操作时，不要调用任何工具。
7. “近期对话”和“用户画像”只用于补全指代与默认偏好，不是本轮指令；与本轮明确指令冲突时以本轮为准。
8. 查询设备在哪个房间/位置、列出家庭或房间设备，必须调用 get_device_state 或 list_room_devices，不要用文字直接回答。
"""


def _request(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("request") or {}


def _task_text(state: dict[str, Any]) -> str:
    task = state.get("task") or {}
    return str(task.get("instruction") or task.get("query") or state.get("query") or "")


def _query_text(state: dict[str, Any]) -> str:
    """规则解析始终以本轮完整输入为准。

    主图规划器可能把控制任务收窄成某一句，但同一轮里用户明确提到的
    其他设备同样应该执行；不能因为模型少拆一条就漏掉。
    """
    return str(state.get("query") or _task_text(state))


def _house_devices(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"type": str(item.get("type") or ""), "room_name": str(item.get("room") or "")}
        for item in (state.get("house_snapshot") or {}).get("devices") or []
        if item.get("type")
    ]


def _rule_tasks(state: dict[str, Any]) -> list[TaskSpec]:
    """无模型时的确定性规划：只解析用户明确表达的设备指令。"""
    devices = _house_devices(state)
    rooms = sorted({item["room_name"] for item in devices if item["room_name"]})
    tasks, _, _ = control_tasks(_query_text(state), devices, rooms)
    return [TaskSpec(**item) for item in tasks]


def _merge_rule_writes(tasks: list[TaskSpec], rule_tasks: list[TaskSpec]) -> list[TaskSpec]:
    """补齐模型漏掉的显式设备写操作，并合并同设备的缺失属性。"""
    merged = list(tasks)
    index = {
        (task.arguments.get("device_type"), task.arguments.get("room_name")): task
        for task in merged
        if task.tool == "set_device_state"
    }
    for rule in rule_tasks:
        if rule.tool != "set_device_state":
            continue
        key = (rule.arguments.get("device_type"), rule.arguments.get("room_name"))
        existing = index.get(key)
        if existing is None:
            merged.append(rule)
            index[key] = rule
            continue
        attributes = dict(existing.arguments.get("attributes") or {})
        for name, value in (rule.arguments.get("attributes") or {}).items():
            attributes.setdefault(name, value)
        existing.arguments = {**existing.arguments, "attributes": attributes}
    return merged


def _drop_implicit_scenes(tasks: list[TaskSpec], text: str) -> list[TaskSpec]:
    """显式设备指令存在时，不再叠加“睡觉/回家”等隐式场景。

    场景与显式设置并行下发会互相覆盖，且用户本轮已经说清目标状态。
    """
    if not any(task.tool == "set_device_state" for task in tasks):
        return tasks
    if any(name in text for name in SCENE_NAMES):
        return tasks
    return [task for task in tasks if task.tool != "trigger_scene"]


def _task_invalid_reason(task: TaskSpec) -> str | None:
    """模型规划结果的确定性校验；不合法时返回原因，由调用方回退规则规划。"""
    if task.tool not in CONTROL_TOOL_NAMES:
        return f"未知工具: {task.tool}"

    arguments = task.arguments or {}
    if task.tool == "set_device_state":
        if not str(arguments.get("room_name") or "").strip():
            return "缺少 room_name"
        if not str(arguments.get("device_type") or "").strip():
            return "缺少 device_type"
        if not isinstance(arguments.get("attributes"), dict) or not arguments["attributes"]:
            return "缺少 attributes"
    elif task.tool == "get_device_state":
        if not str(arguments.get("device_type") or "").strip():
            return "缺少 device_type"
    elif task.tool == "trigger_scene":
        if not str(arguments.get("scene_name") or "").strip():
            return "缺少 scene_name"
    return None


def _tool_calls_to_tasks(state: dict[str, Any], tool_calls: list[dict[str, Any]]) -> list[TaskSpec]:
    """把 LangChain bind_tools 产生的 tool_calls 转成受策略门禁的统一任务。"""
    description = str((state.get("task") or {}).get("instruction") or "")
    tasks: list[TaskSpec] = []
    for index, call in enumerate(tool_calls, 1):
        name = str(call.get("name") or "")
        arguments = call.get("args")
        tasks.append(
            TaskSpec(
                task_id=f"task_{index}",
                tool=name,
                arguments=dict(arguments) if isinstance(arguments, dict) else {},
                description=description or name,
                expected_effect="设备状态更新为请求值",
            )
        )
    return tasks


async def _llm_tasks(state: dict[str, Any]) -> list[TaskSpec] | None:
    """用 bind_tools 让模型选择已注册工具并生成调用参数；失败返回 None。"""
    try:
        model = build_chat_model(temperature=0.1, max_tokens=1200).bind_tools(CONTROL_TOOLS)
        payload = {
            "user_query": state.get("query") or _task_text(state),
            "task": state.get("task") or {},
            "profile": state.get("profile_text") or "（未提供）",
            "recent_history": state.get("history_text") or "（无）",
            "house_status": build_house_status_text(state.get("house_snapshot") or {}),
            "last_error": state.get("last_error") or "",
            "observations": state.get("observations") or [],
        }
        response = await model.ainvoke(
            [
                SystemMessage(content=PLANNER_SYSTEM),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
            ]
        )
        tasks = _tool_calls_to_tasks(state, list(getattr(response, "tool_calls", None) or []))
        if not tasks:
            return None

        for task in tasks:
            reason = _task_invalid_reason(task)
            if reason:
                logger.warning(
                    "规划结果不合法（%s: %s），回退规则规划",
                    task.tool,
                    reason,
                )
                return None
        return tasks
    except Exception as exc:
        logger.warning("任务规划 LLM 不可用，使用规则规划: %s", exc)
        return None


async def context_node(state: dict[str, Any]) -> dict[str, Any]:
    """归一化全屋状态；快照由主图 planner 按需加载，子图不查库。"""
    return {"house_snapshot": state.get("house_snapshot") or {}}


async def plan_node(state: dict[str, Any]) -> dict[str, Any]:
    llm_tasks = await _llm_tasks(state)
    rule_tasks = _rule_tasks(state)
    tasks = _merge_rule_writes(llm_tasks, rule_tasks) if llm_tasks else rule_tasks
    tasks = _drop_implicit_scenes(tasks, _query_text(state))

    unique: list[TaskSpec] = []
    seen: set[str] = set()
    for task in tasks:
        key = task.idempotency_key or idempotency_key(task.tool, task.arguments)
        if key in seen:
            continue
        seen.add(key)
        task.idempotency_key = key
        task.task_id = f"task_{len(unique) + 1}"
        unique.append(task)
    return {
        "tasks": [task.model_dump() for task in unique],
        "plan_ready": bool(unique),
        "last_error": None if unique else "未能从当前指令中生成可执行任务",
    }


def _validate_task(
    task_data: dict[str, Any],
    devices: list[dict[str, Any]],
    role: str,
) -> tuple[TaskSpec | None, str | None]:
    task = TaskSpec(**task_data)
    if task.tool not in CONTROL_TOOL_NAMES:
        return None, f"未知工具: {task.tool}"

    if task.tool in ("set_device_state", "get_device_state"):
        device_type = str(task.arguments.get("device_type") or "")
        room_name = str(task.arguments.get("room_name") or "")
        if device_type and not devices:
            # 快照为空可能是家庭确实没有设备，也可能是加载失败；
            # 两种情况都不能静默跳过存在性校验，否则会执行到必然失败的工具。
            return None, "家庭设备列表为空或加载失败，暂不能执行设备操作"
        if device_type:
            matches = [
                device
                for device in devices
                if device.get("type") == device_type
                and (not room_name or device.get("room_name") == room_name)
            ]
            if not matches:
                scope = f"{room_name}的" if room_name else ""
                return None, f"家庭中未找到{scope}{device_type}"

    decision = decide_tool(role, task.tool, task.arguments)
    task.risk_level = decision.risk
    return task, None


async def validate_node(state: dict[str, Any]) -> dict[str, Any]:
    """校验设备/房间/工具合法性，并计算整批任务的策略动作。"""
    role = str(_request(state).get("role") or "")
    devices = _house_devices(state)
    valid: list[TaskSpec] = []
    errors: list[str] = []
    actions: list[str] = []
    reasons: list[str] = []

    for raw in state.get("tasks") or []:
        task, error = _validate_task(raw, devices, role)
        if error:
            errors.append(error)
            continue
        valid.append(task)
        decision = decide_tool(role, task.tool, task.arguments)
        actions.append(decision.action)
        reasons.append(decision.reason)

    if errors or not valid:
        return {
            "tasks": [task.model_dump() for task in valid],
            "plan_ready": False,
            "last_error": "；".join(errors) or "没有可执行任务",
        }

    if "deny" in actions:
        action = "deny"
    elif "approval" in actions:
        action = "approval"
    else:
        action = "allow"
    reason = next(
        (reason for act, reason in zip(actions, reasons, strict=True) if act == action),
        "策略校验通过",
    )
    return {
        "tasks": [task.model_dump() for task in valid],
        "plan_ready": True,
        "policy_action": action,
        "policy_reason": reason,
        "last_error": reason if action == "deny" else None,
    }


def route_after_validate(state: dict[str, Any]) -> str:
    if not state.get("plan_ready"):
        return "cancel"
    action = state.get("policy_action")
    if action == "deny":
        return "cancel"
    if action == "approval":
        return "approval"
    return "dispatch"


async def approval_node(state: dict[str, Any]) -> dict[str, Any]:
    """高风险/中风险任务中断等待用户确认。"""
    tasks = state.get("tasks") or []
    risk_order = {"low": 0, "medium": 1, "high": 2}
    risk_level = max(
        (str(task.get("risk_level") or "low") for task in tasks),
        key=lambda level: risk_order.get(level, 0),
        default="low",
    )
    payload = {
        "type": "approval",
        "title": "请确认设备操作",
        "question": state.get("policy_reason") or "该操作需要确认",
        "risk_level": risk_level,
        "tasks": tasks,
        "thread_id": _request(state).get("thread_id"),
    }
    resume_data = interrupt(payload)

    if isinstance(resume_data, bool):
        decision = ApprovalDecision(approved=resume_data)
    elif isinstance(resume_data, dict):
        decision = ApprovalDecision(
            approved=bool(resume_data.get("approved") or resume_data.get("granted")),
            approved_task_ids=list(
                resume_data.get("approved_task_ids")
                or resume_data.get("task_ids")
                or []
            ),
            note=str(resume_data.get("note") or ""),
        )
    else:
        decision = ApprovalDecision(approved=False)

    if not decision.approved:
        return {"approval_granted": False, "last_error": "用户取消了本次设备操作"}

    approved_ids = set(decision.approved_task_ids)
    selected = [
        task
        for task in tasks
        if not approved_ids or task.get("task_id") in approved_ids
    ]
    if not selected:
        # approved=True 但选中的任务不匹配（或任务为空）时不能当作成功执行
        return {"approval_granted": False, "tasks": [], "last_error": "所选操作不在待确认列表中"}
    return {"approval_granted": True, "tasks": selected, "last_error": None}


def route_after_approval(state: dict[str, Any]) -> str:
    return "dispatch" if state.get("approval_granted") else "cancel"


async def dispatch_node(state: dict[str, Any]) -> dict[str, Any]:
    """把任务列表转成标准 tool_calls，交给 ToolNode 并发执行。"""
    tool_calls = [
        {
            "id": f"call_{task['task_id']}",
            "name": task["tool"],
            "args": dict(task.get("arguments") or {}),
        }
        for task in state.get("tasks") or []
    ]
    return {"messages": [AIMessage(content="", tool_calls=tool_calls)]}


def _parse_tool_message(message: ToolMessage) -> dict[str, Any]:
    if getattr(message, "status", None) == "error":
        return {"success": False, "error": str(message.content)}
    content = message.content if isinstance(message.content, str) else str(message.content)
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return {"success": True, "message": content}
    return payload if isinstance(payload, dict) else {"success": True, "message": payload}


async def observe_node(state: dict[str, Any]) -> dict[str, Any]:
    """把 ToolMessage 映射回任务，形成可验证的观察结果。"""
    tasks = {str(task["task_id"]): task for task in state.get("tasks") or []}
    observations: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    messages = list(state.get("messages") or [])
    # 反思重试后 messages 里仍保留上一轮工具结果，只看最近一次 dispatch 之后的消息
    last_dispatch = max(
        (
            index
            for index, message in enumerate(messages)
            if isinstance(message, AIMessage) and getattr(message, "tool_calls", None)
        ),
        default=-1,
    )
    for message in messages[last_dispatch + 1 :]:
        if not isinstance(message, ToolMessage):
            continue
        task_id = str(message.tool_call_id or "").removeprefix("call_")
        task = tasks.get(task_id)
        if not task:
            continue
        payload = _parse_tool_message(message)
        observation = {
            "task_id": task_id,
            "tool": task["tool"],
            "arguments": task.get("arguments") or {},
            "success": bool(payload.get("success", True)),
            "result": payload,
            "error": payload.get("error") or "",
        }
        observations.append(observation)
        tool_events.append(
            {
                "tool": task["tool"],
                "task_id": task_id,
                "success": observation["success"],
                "arguments": task.get("arguments") or {},
            }
        )
    return {"observations": observations, "tool_events": tool_events}


def _latest_observations(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for observation in state.get("observations") or []:
        latest[str(observation.get("task_id"))] = observation
    return latest


def _is_retryable(error: str, observation: dict[str, Any] | None) -> bool:
    text = f"{error} {((observation or {}).get('error') or '')}".lower()
    return any(
        marker in text
        for marker in ("超时", "timeout", "异常", "暂时", "稍后", "busy", "网络", "connection")
    )


async def verify_node(state: dict[str, Any]) -> dict[str, Any]:
    """确定性验证：所有任务都有成功观察才算完成。"""
    tasks = state.get("tasks") or []
    latest = _latest_observations(state)
    failures = [
        (task, latest.get(str(task["task_id"])))
        for task in tasks
        if not (latest.get(str(task["task_id"])) or {}).get("success")
    ]

    if not failures:
        summary = "；".join(
            str((latest.get(str(task["task_id"])) or {}).get("result", {}).get("message") or "")
            or f"{task.get('description') or task['tool']}已完成"
            for task in tasks
        )
        return {
            "results": [
                BranchResult(
                    branch="control",
                    success=True,
                    summary=summary or "设备操作已完成",
                    data={"tasks": tasks, "observations": list(latest.values())},
                ).model_dump()
            ],
            "last_error": None,
        }

    error_text = "；".join(
        (observation or {}).get("error") or f"{task.get('description') or task['tool']}执行失败"
        for task, observation in failures
    )
    retryable = any(_is_retryable(error_text, observation) for _, observation in failures)
    if retryable and int(state.get("retry_count") or 0) < settings.agent_max_reflections:
        return {"last_error": error_text, "tasks": []}

    return {
        "results": [
            BranchResult(
                branch="control",
                success=False,
                summary=f"设备操作未完成：{error_text}",
                data={"tasks": tasks, "observations": list(latest.values())},
                degraded=True,
            ).model_dump()
        ],
        "last_error": error_text,
    }


def route_after_verify(state: dict[str, Any]) -> str:
    if state.get("results"):
        return "end"
    if int(state.get("retry_count") or 0) < settings.agent_max_reflections:
        return "reflect"
    return "end"


async def reflect_node(state: dict[str, Any]) -> dict[str, Any]:
    """记录失败观察并回到规划；planner 会看到 last_error 重新生成任务。"""
    return {
        "retry_count": int(state.get("retry_count") or 0) + 1,
        "tasks": [],
        "last_error": state.get("last_error") or "上一轮执行失败",
    }


async def cancel_node(state: dict[str, Any]) -> dict[str, Any]:
    reason = state.get("last_error") or "操作已取消"
    return {
        "results": [
            BranchResult(
                branch="control",
                success=False,
                summary=reason,
                degraded=True,
            ).model_dump()
        ]
    }


def build_control_subgraph(checkpointer=None):
    graph = StateGraph(ControlState, output_schema=BranchOutput)
    graph.add_node("context", context_node)
    graph.add_node("plan", plan_node)
    graph.add_node("validate", validate_node)
    graph.add_node("approval", approval_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("execute", ToolNode(CONTROL_TOOLS))
    graph.add_node("observe", observe_node)
    graph.add_node("verify", verify_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("cancel", cancel_node)

    graph.add_edge(START, "context")
    graph.add_edge("context", "plan")
    graph.add_edge("plan", "validate")
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {"cancel": "cancel", "approval": "approval", "dispatch": "dispatch"},
    )
    graph.add_conditional_edges(
        "approval",
        route_after_approval,
        {"dispatch": "dispatch", "cancel": "cancel"},
    )
    graph.add_edge("dispatch", "execute")
    graph.add_edge("execute", "observe")
    graph.add_edge("observe", "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {"reflect": "reflect", "end": END},
    )
    graph.add_edge("reflect", "plan")
    graph.add_edge("cancel", END)
    return graph.compile(checkpointer=checkpointer)
