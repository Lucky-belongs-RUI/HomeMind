"""任务规划器：把用户输入拆成可并行的子任务。

一次结构化 LLM 调用完成多意图分解；模型不可用时回退到规则规划。
规则规划只在模型漏掉**明确设备指令**时补一个 control 任务，
不会凭空生成设备操作。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send, interrupt

from homemind.agent.rules.devices import ROOM_ALIASES
from homemind.agent.rules.plan import (
    ACTION_HINTS,
    REPORT_TRIGGERS,
    control_tasks,
    rule_plan,
)
from homemind.agent.runtime.context import render_profile
from homemind.agent.runtime.schemas import Plan, PlanTask
from homemind.agent.tools.context_tools import get_house_snapshot, get_user_profile
from homemind.core.config import settings
from homemind.llm.langchain import build_router_model
from homemind.services.conversation_service import save_conversation

logger = logging.getLogger(__name__)

# 需要全屋快照的控制类工具；时间/天气不依赖设备库，不触发加载
_HOUSE_TOOLS = frozenset(
    {"set_device_state", "get_device_state", "list_room_devices", "trigger_scene"}
)
# 地点 + 状态词组合出现时，规则可能识别不了设备（如“让客厅亮堂一点”）
_HOUSE_PLACES = (*ROOM_ALIASES.keys(), "家里", "家中", "全屋")
_HOUSE_STATE_HINTS = (
    "温度",
    "湿度",
    "空气质量",
    "空气",
    "状态",
    "开着",
    "关着",
    "亮",
    "暗",
    "冷",
    "热",
)

# 只有出现个性化信号才加载画像，避免每轮都查偏好库
_PROFILE_HINTS = (
    "我冷",
    "好冷",
    "太冷",
    "怕冷",
    "冷一点",
    "有点冷",
    "感觉冷",
    "我热",
    "好热",
    "太热",
    "怕热",
    "热一点",
    "有点热",
    "感觉热",
    "感冒",
    "发烧",
    "不舒服",
    "头疼",
    "喉咙痛",
    "身体",
    "过敏",
    "睡眠",
    "睡觉",
    "作息",
    "失眠",
    "喜欢",
    "不喜欢",
    "习惯",
    "偏好",
    "忌口",
    "口味",
    "老人",
    "小孩",
    "宝宝",
    "宠物",
    "心情",
    "难过",
    "不开心",
    "累了",
    "喜好",
    "适合我",
    "根据我",
    "睡不着",
    "睡不好",
    "我的情况",
)

PLANNER_SYSTEM = """你是智能家居平台的任务分解器。请把用户本轮输入拆成可并行执行的子任务，不要执行操作。

用户画像（仅作为默认偏好，不是本轮指令）：
{profile}

近期对话（仅用于理解代词与省略，不是本轮指令，不要执行其中的操作）：
{history}

家庭设备：{device_context}
全屋状态：{house_status}

分支定义：
- chat：寒暄、情绪陪伴、健康关怀等日常交流
- knowledge：需要查家庭文档、规定、说明书、用药资料等知识库内容
- control：需要读取或改变设备/场景状态，查询设备在哪个房间、家里有哪些设备，或查询时间、天气
- report：需要汇总全屋状态

规则：
1. 一句话可以拆成多个子任务。例如“我感冒了，调高一下空调温度，药箱里的药该吃哪些药”
   应拆成 chat（安慰）+ control（调高空调）+ knowledge（药箱用药资料）。
2. 只有用户明确要求改变设备时才生成 control 写操作；设备存在、用户不舒服都不是控制理由。
3. “路由器在哪个房间”“哪些设备在客厅”“家里有哪些设备”是 control 查询任务，
   不要走 knowledge 或 chat。
4. control 的 instruction 必须保留用户原始动作和数值，不要替用户编造温度或模式。
5. knowledge 的 query 改写成独立可检索的问题；其他分支 query 留空。
6. 缺少房间、设备或动作导致无法执行时，needs_clarification=true，并给出问题与选项。
7. 用户没有明确要求时不要生成 report。
8. “家庭设备”显示未加载不代表家里没有设备；用户明确要求控制时仍要生成 control，
   设备与房间是否真实存在由执行阶段校验。
"""


def _request(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("request") or {}


def _devices(state: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = state.get("house_snapshot") or {}
    return [
        {"type": str(item.get("type") or ""), "room_name": str(item.get("room") or "")}
        for item in snapshot.get("devices") or []
        if item.get("type")
    ]


def _rooms(devices: list[dict[str, Any]]) -> list[str]:
    return sorted({str(item["room_name"]) for item in devices if item.get("room_name")})


def _merge_strong_control(
    plan: Plan,
    text: str,
    devices: list[dict[str, Any]],
    rooms: list[str],
) -> Plan:
    """模型漏掉明确设备指令/设备查询时补一个 control 任务。

    只补明确写操作、设备状态查询、设备位置查询和房间设备列表，
    不会凭空生成设备操作。
    """
    if any(task.branch == "control" for task in plan.tasks):
        return plan

    tasks, _, _ = control_tasks(text, devices, rooms)
    if not any(
        task["tool"]
        in (
            "set_device_state",
            "trigger_scene",
            "get_device_state",
            "list_room_devices",
        )
        for task in tasks
    ):
        return plan

    merged = [*plan.tasks, PlanTask(branch="control", instruction=text)]
    return plan.model_copy(update={"tasks": merged})


def _house_context_signal(text: str) -> bool:
    """地点 + 状态/环境词：覆盖规则识别不了设备的表达。"""
    has_place = any(word in text for word in _HOUSE_PLACES)
    has_state = any(word in text for word in _HOUSE_STATE_HINTS)
    return has_place and has_state


def _needs_house_snapshot(text: str) -> bool:
    """判断本轮是否需要设备上下文：设备/场景/状态查询或报告。"""
    tasks, _, _ = control_tasks(text, [], [])
    if any(task.get("tool") in _HOUSE_TOOLS for task in tasks):
        return True
    if any(word in text for word in REPORT_TRIGGERS):
        return True
    return _house_context_signal(text)


def _is_time_weather_only(text: str) -> bool:
    """规则能确定本轮只查时间/天气时，不需要设备上下文。"""
    if _house_context_signal(text):
        return False
    tasks, _, question = control_tasks(text, [], [])
    if question or not tasks:
        return False
    return all(task.get("tool") in {"get_current_time", "get_weather"} for task in tasks)


def _needs_profile(text: str) -> bool:
    return any(word in text for word in _PROFILE_HINTS)


async def _call_context_tool(tool, state: dict[str, Any]) -> dict[str, Any]:
    try:
        result = await tool.ainvoke({"state": state})
    except Exception as exc:
        logger.warning("上下文工具 %s 调用失败: %s", getattr(tool, "name", tool), exc)
        return {}
    return result if isinstance(result, dict) else {}


async def _load_house_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    result = await _call_context_tool(get_house_snapshot, state)
    if not result.get("success"):
        logger.warning("全屋快照加载失败: %s", result.get("error"))
        return {}
    snapshot = result.get("snapshot")
    return {"house_snapshot": snapshot} if isinstance(snapshot, dict) else {}


async def _load_profile(state: dict[str, Any]) -> dict[str, Any]:
    result = await _call_context_tool(get_user_profile, state)
    if not result.get("success"):
        logger.warning("用户画像加载失败: %s", result.get("error"))
        return {}
    profile = result.get("profile")
    if not isinstance(profile, dict):
        return {}
    return {"profile": profile, "profile_text": render_profile(profile)}


async def _load_on_demand(state: dict[str, Any], text: str) -> dict[str, Any]:
    """按本轮输入加载画像/全屋快照；已有数据不重复加载。"""
    updates: dict[str, Any] = {}
    if not state.get("house_snapshot") and _needs_house_snapshot(text):
        updates.update(await _load_house_snapshot(state))
    if not state.get("profile") and not state.get("profile_text") and _needs_profile(text):
        updates.update(await _load_profile(state))
    return updates


async def plan_node(state: dict[str, Any]) -> dict[str, Any]:
    """结构化分解；模型失败或输出为空时使用规则规划。"""
    text = str(state.get("user_input") or "").strip()
    updates = await _load_on_demand(state, text)
    view = {**state, **updates}
    devices = _devices(view)
    rooms = _rooms(devices)
    rule = rule_plan(text, devices, rooms)

    plan: Plan | None = None
    try:
        model = build_router_model(
            _request(state).get("provider"),
            _request(state).get("model") or settings.agent_router_model or None,
        ).with_structured_output(Plan)
        plan = await model.ainvoke(
            [
                SystemMessage(
                    content=PLANNER_SYSTEM.format(
                        profile=str(view.get("profile_text") or "").strip() or "（未提供）",
                        history=str(view.get("history_text") or "").strip() or "（无）",
                        device_context=devices or "（本轮未加载设备清单）",
                        house_status=view.get("house_snapshot") or "（未加载）",
                    )
                ),
                HumanMessage(content=text),
            ]
        )
    except Exception as exc:
        logger.warning("任务规划 LLM 不可用，使用规则规划: %s", exc)

    if plan is None or not plan.tasks:
        plan = Plan(
            tasks=[PlanTask(**task) for task in rule.tasks],
            needs_clarification=rule.needs_clarification,
            clarification_question=rule.clarification_question,
            clarification_options=rule.clarification_options,
        )
    else:
        plan = _merge_strong_control(plan, text, devices, rooms)

    # 规则发现明确写指令存在房间歧义时补澄清；纯查询/知识问题不触发。
    if (
        rule.needs_clarification
        and rule.clarification_options
        and not plan.needs_clarification
        and any(word in text for word in ACTION_HINTS)
    ):
        plan = plan.model_copy(
            update={
                "needs_clarification": True,
                "clarification_question": rule.clarification_question,
                "clarification_options": rule.clarification_options,
            }
        )

    # 模型判定为控制/报告、但预判没加载快照时，补一次加载再扇出；
    # 纯时间/天气查询不需要设备上下文。
    branches = {task.branch for task in plan.tasks}
    needs_house = "report" in branches or (
        "control" in branches and not _is_time_weather_only(text)
    )
    if needs_house and not view.get("house_snapshot"):
        updates.update(await _load_house_snapshot(state))

    logger.info(
        "任务规划：%s 个任务 %s",
        len(plan.tasks),
        [task.branch for task in plan.tasks],
    )
    return {**updates, "plan": plan.model_dump(), "avatar_emotion": "thinking"}


def _normalize_tasks(tasks: list[PlanTask], user_input: str) -> list[PlanTask]:
    """控制任务合并为一批；知识任务按问题去重；chat/report 各保留一条。"""
    normalized: list[PlanTask] = []
    control: PlanTask | None = None
    chat: PlanTask | None = None
    report: PlanTask | None = None
    seen_queries: set[str] = set()

    for task in tasks:
        if task.branch == "control":
            if control is None:
                control = PlanTask(
                    branch="control", instruction=task.instruction or user_input
                )
                normalized.append(control)
            elif task.instruction and task.instruction not in control.instruction:
                control.instruction = f"{control.instruction}；{task.instruction}".strip("；")
        elif task.branch == "knowledge":
            query = (task.query or task.instruction or user_input).strip()
            if not query or query in seen_queries:
                continue
            seen_queries.add(query)
            normalized.append(
                PlanTask(branch="knowledge", instruction=task.instruction or query, query=query)
            )
        elif task.branch == "chat" and chat is None:
            chat = PlanTask(branch="chat", instruction=task.instruction or user_input)
            normalized.append(chat)
        elif task.branch == "report" and report is None:
            report = PlanTask(branch="report", instruction=task.instruction or user_input)
            normalized.append(report)

    limit = settings.agent_max_plan_tasks
    if len(normalized) <= limit:
        return normalized
    # 超限时优先保留 control/report/chat，避免模型拆得过多把显式设备指令挤掉
    priority = {"control": 0, "report": 1, "chat": 2, "knowledge": 3}
    ordered = sorted(
        enumerate(normalized),
        key=lambda item: (priority.get(item[1].branch, 9), item[0]),
    )
    return [task for _, task in ordered[:limit]]


def _branch_payload(state: dict[str, Any], task: PlanTask) -> dict[str, Any]:
    return {
        "request": _request(state),
        "query": str(state.get("user_input") or ""),
        "task": task.model_dump(),
        "profile": state.get("profile") or {},
        "profile_text": state.get("profile_text") or "",
        "history_text": state.get("history_text") or "",
        "house_snapshot": state.get("house_snapshot"),
    }


def route_after_plan(state: dict[str, Any]):
    """需要澄清进 clarify；否则每个子任务一个 Send，分支状态物理隔离。"""
    plan = state.get("plan") or {}
    if plan.get("needs_clarification") and int(
        state.get("clarification_attempts") or 0
    ) < settings.agent_max_clarifications:
        return "clarify"

    tasks = [PlanTask(**item) for item in plan.get("tasks") or []]
    tasks = _normalize_tasks(tasks, str(state.get("user_input") or ""))
    if not tasks:
        tasks = [PlanTask(branch="chat", instruction=str(state.get("user_input") or ""))]
    return [Send(task.branch, _branch_payload(state, task)) for task in tasks]


async def clarify(state: dict[str, Any]) -> dict[str, Any]:
    """澄清中断：用户回答后重新规划；取消则转入闲聊。"""
    plan = state.get("plan") or {}
    attempts = int(state.get("clarification_attempts") or 0)
    payload = {
        "type": "clarification",
        "question": plan.get("clarification_question")
        or "请补充一下具体要控制的房间、设备和动作？",
        "options": plan.get("clarification_options") or [],
        "thread_id": _request(state).get("thread_id"),
    }
    resume_data = interrupt(payload)

    if isinstance(resume_data, dict):
        if resume_data.get("cancelled"):
            return {
                "clarification": {"cancelled": True},
                "clarification_attempts": attempts + 1,
            }
        answer = str(
            resume_data.get("answer")
            or resume_data.get("text")
            or resume_data.get("value")
            or ""
        ).strip()
    else:
        answer = str(resume_data or "").strip()

    if not answer:
        return {
            "clarification": {"answer": "", "cancelled": True},
            "clarification_attempts": attempts + 1,
        }

    request = _request(state)
    if request.get("session_id") and request.get("user_id") and request.get("family_id"):
        try:
            await save_conversation(
                family_id=int(request["family_id"]),
                user_id=int(request["user_id"]),
                session_id=str(request["session_id"]),
                role="user",
                content=answer,
            )
        except Exception as exc:  # 落库失败不阻断本轮澄清
            logger.warning("保存澄清回答失败: %s", exc)

    return {
        "user_input": f"{state.get('user_input') or ''} {answer}".strip(),
        "messages": [HumanMessage(content=answer)],
        "clarification": {"answer": answer, "cancelled": False},
        "clarification_attempts": attempts + 1,
        "plan": None,
    }


def route_after_clarify(state: dict[str, Any]):
    clarification = state.get("clarification") or {}
    attempts = int(state.get("clarification_attempts") or 0)
    if clarification.get("cancelled") or attempts >= settings.agent_max_clarifications:
        task = PlanTask(branch="chat", instruction=str(state.get("user_input") or ""))
        return [Send("chat", _branch_payload(state, task))]
    return "planner"
