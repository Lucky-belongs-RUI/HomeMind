"""任务规划节点：优先由模型结合全屋状态动态规划，失败时回退规则映射。"""
import json
import logging

from app.agent.nodes._base import log_node_run
from app.agent.nodes.house_status import build_house_status_text
from app.agent.rules.common import device_label, extract_json, find_room
from app.agent.rules.planning import _describe_effect, build_rule_tasks
from app.llm.factory import get_llm_client
from app.llm.message import Message

logger = logging.getLogger(__name__)

PLANNING_PROMPT = """你是智能家居任务规划器，请根据识别到的意图和当前家庭状态生成可执行任务。

当前家庭状态：
{house_status}

识别到的意图（JSON）：
{intents}

当前权限模式：{permission_mode}

输出要求：
1. 只输出 JSON，结构为 {{"tasks": [...]}}。
2. 每个 task 字段：intent_type(device_control/scene_trigger/device_query)、description、device_type、room_name、attributes、scene_name、tool_name(set_device_state/trigger_scene/get_device_state/list_room_devices)、priority(high/medium/low)、risk_level(high/medium/low)。
3. 设备控制必须基于当前家庭状态中真实存在的设备类型与房间；attributes 必须包含明确参数（如 power、temperature、brightness、position、volume、mode、locked）。
4. 依据当前时间、季节、天气和家庭设备自由决定合理操作，不要套用固定规则；身体不适等场景应先考虑舒适度再执行设备调整。
5. 房间不确定且家庭中该设备仅出现在一个房间时自动补全；出现在多个房间时 room_name 留空。
6. 没有可执行设备操作时返回空数组。"""


def _default_attributes(device_type: str) -> dict:
    """高级模式下空属性任务的默认值。"""
    defaults = {
        "air_conditioner": {"power": "on"},
        "light": {"power": "on"},
        "curtain": {"position": 100},
        "speaker": {"volume": 30},
        "tv": {"power": "on"},
        "air_purifier": {"power": "on"},
        "humidifier": {"power": "on"},
        "water_heater": {"power": "on"},
        "robot_vacuum": {"power": "on", "status": "running"},
    }
    return defaults.get(device_type, {"power": "on"})


def _default_tool(intent_type: str, device_type: str) -> str:
    if intent_type == "scene_trigger":
        return "trigger_scene"
    if intent_type == "device_query":
        return "get_device_state" if device_type else "list_room_devices"
    return "set_device_state"


async def _llm_plan_tasks(state: dict) -> list | None:
    """调用模型生成任务；异常或格式非法时返回 None 交由规则回退。"""
    try:
        client = get_llm_client()
        system = PLANNING_PROMPT.format(
            house_status=build_house_status_text(state.get("house_status") or {}),
            intents=json.dumps(state.get("intents", []), ensure_ascii=False),
            permission_mode=state.get("permission_mode", "normal"),
        )
        result = await client.chat(
            messages=[Message(role="user", content="请根据意图生成任务列表")],
            system=system,
            temperature=0.2,
            max_tokens=1600,
        )
        data = extract_json(result.content)
        raw_tasks = data.get("tasks") if isinstance(data, dict) else None
        if not raw_tasks:
            return None
        tasks = []
        for index, raw in enumerate(raw_tasks, 1):
            if not isinstance(raw, dict):
                continue
            task = _normalize_llm_task(raw, index)
            if task:
                tasks.append(task)
        return tasks or None
    except Exception as exc:
        logger.warning("任务规划 LLM 调用异常: %s", exc)
        return None


def _normalize_llm_task(raw: dict, index: int) -> dict | None:
    """把 LLM 输出任务规范化为工具执行所需结构。"""
    intent_type = raw.get("intent_type")
    if intent_type not in ("device_control", "scene_trigger", "device_query"):
        return None
    device_type = raw.get("device_type") or ""
    room = str(raw.get("room_name") or "")
    scene_name = str(raw.get("scene_name") or "")
    description = str(raw.get("description") or "")
    attrs = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {}
    priority = raw.get("priority") if raw.get("priority") in ("high", "medium", "low") else "medium"
    risk_level = raw.get("risk_level") if raw.get("risk_level") in ("high", "medium", "low") else "low"
    task_id = f"task_{index}"

    if intent_type == "device_control":
        if not device_type:
            return None
        if risk_level == "low" and device_type == "door_lock":
            risk_level = "medium"
        return {
            "task_id": task_id,
            "intent_type": "device_control",
            "description": description or f"调整{device_label(device_type)}",
            "tool_name": "set_device_state",
            "arguments": {"room_name": room, "device_type": device_type, "attributes": attrs},
            "room_name": room or None,
            "device_type": device_type,
            "attributes": attrs,
            "priority": priority,
            "status": "pending",
            "needs_approval": True,
            "risk_level": risk_level,
            "expected_effect": _describe_effect(device_type, attrs, room),
        }

    if intent_type == "scene_trigger":
        if not scene_name:
            return None
        return {
            "task_id": task_id,
            "intent_type": "scene_trigger",
            "description": description or f"触发{scene_name}",
            "tool_name": "trigger_scene",
            "arguments": {"scene_name": scene_name},
            "scene_name": scene_name,
            "priority": priority,
            "status": "pending",
            "needs_approval": True,
            "risk_level": "medium",
            "expected_effect": f"执行{scene_name}，批量调整相关设备",
        }

    if device_type:
        return {
            "task_id": task_id,
            "intent_type": "device_query",
            "description": f"查询{room or ''}{device_label(device_type)}状态",
            "tool_name": "get_device_state",
            "arguments": {"room_name": room or "", "device_type": device_type},
            "room_name": room or None,
            "device_type": device_type,
            "priority": "low",
            "status": "pending",
            "needs_approval": False,
            "risk_level": "low",
            "expected_effect": "返回设备当前状态",
        }

    return {
        "task_id": task_id,
        "intent_type": "device_query",
        "description": f"列出{room or '全部房间'}的设备",
        "tool_name": "list_room_devices",
        "arguments": {"room_name": room or "all"},
        "room_name": room or "all",
        "priority": "low",
        "status": "pending",
        "needs_approval": False,
        "risk_level": "low",
        "expected_effect": "返回房间设备列表",
    }


@log_node_run
async def task_planning_node(state: dict) -> dict:
    """生成任务列表；普通模式房间不明确时再次触发澄清。"""
    from app.services.device_service import list_devices_by_family
    from app.services.room_service import list_rooms_by_family

    state = dict(state)
    permission_mode = state.get("permission_mode", "normal")

    tasks = await _llm_plan_tasks(state)
    if not tasks:
        tasks = build_rule_tasks(state.get("intents", []), permission_mode)

    rooms = await list_rooms_by_family(state["family_id"])
    devices = await list_devices_by_family(state["family_id"])
    room_map = {room.id: room.name for room in rooms}
    device_rows = [
        {"room_name": room_map.get(device.room_id, ""), "type": device.type}
        for device in devices
    ]
    available_types = {device.type for device in devices}
    tasks = [
        task
        for task in tasks
        if task.get("intent_type") != "device_control" or task.get("device_type") in available_types
    ]

    needs_clarification = False
    question = ""
    clarification_options = []
    user_clarification = state.get("user_clarification") or ""

    for task in tasks:
        device_type = task.get("device_type")
        if not device_type:
            continue

        # 从澄清回答中提取房间
        if not task.get("room_name") and user_clarification:
            room_from_answer = find_room(user_clarification)
            if room_from_answer:
                task["room_name"] = room_from_answer
                task["arguments"]["room_name"] = room_from_answer

        if task.get("room_name") not in (None, "", "all"):
            continue

        candidates = sorted(
            {
                row["room_name"]
                for row in device_rows
                if row["type"] == device_type and row["room_name"]
            }
        )
        if len(candidates) == 1:
            task["room_name"] = candidates[0]
            task["arguments"]["room_name"] = candidates[0]
        elif len(candidates) > 1:
            if permission_mode == "high":
                task["room_name"] = candidates[0]
                task["arguments"]["room_name"] = candidates[0]
            else:
                needs_clarification = True
                option_text = "、".join(
                    f"{index}.{room_name}" for index, room_name in enumerate(candidates[:6], 1)
                )
                clarification_options = candidates[:6]
                action_word = "查看" if task.get("intent_type") == "device_query" else "调整"
                question = f"请问您想{action_word}哪个房间的{device_label(device_type)}？当前有：{option_text}"

        # 控制任务无具体属性时给出默认值（高级模式）或澄清（普通模式）
        if task.get("intent_type") == "device_control" and not task.get("attributes"):
            if permission_mode == "high":
                task["attributes"] = _default_attributes(device_type)
                task["arguments"]["attributes"] = task["attributes"]
            else:
                needs_clarification = True
                question = question or f"请问您想对{device_label(device_type)}执行什么操作？"

    state["tasks"] = tasks
    state["needs_approval"] = any(task.get("needs_approval") for task in tasks)
    state["needs_clarification"] = needs_clarification
    state["clarification_question"] = question
    state["clarification_options"] = clarification_options
    if needs_clarification:
        state["clarify_source"] = "plan"
    return state
