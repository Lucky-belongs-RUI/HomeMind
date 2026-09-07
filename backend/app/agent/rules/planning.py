"""规则版任务规划与回复生成：将意图映射为工具任务，并生成降级回复。"""
from typing import Any, Dict, List

from app.agent.rules.common import device_label


def _describe_effect(device_type: str, attrs: Dict[str, Any], room: str) -> str:
    label = device_label(device_type)
    parts = []
    if "power" in attrs:
        parts.append("电源开启" if attrs["power"] == "on" else "电源关闭")
    if "temperature" in attrs:
        parts.append(f"温度设为 {attrs['temperature']} 度")
    if "brightness" in attrs:
        parts.append(f"亮度设为 {attrs['brightness']}%")
    if "position" in attrs:
        parts.append(f"开合位置设为 {attrs['position']}%")
    if "volume" in attrs:
        parts.append(f"音量设为 {attrs['volume']}")
    if "mode" in attrs:
        parts.append(f"模式切换为 {attrs['mode']}")
    if "locked" in attrs:
        parts.append("上锁" if attrs["locked"] else "解锁")
    if not parts:
        parts.append("更新状态")
    return f"{room}{label}：{'，'.join(parts)}"


def build_rule_tasks(
    intents: List[Dict[str, Any]], permission_mode: str = "normal"
) -> List[Dict[str, Any]]:
    """将意图列表转换为工具任务；房间补全由任务规划节点完成。"""
    tasks: List[Dict[str, Any]] = []
    control_count = 0

    for index, intent in enumerate(intents, 1):
        intent_type = intent.get("type")
        task_id = f"task_{index}"

        if intent_type == "device_control":
            device_type = intent.get("device_type", "")
            attrs = dict(intent.get("attributes") or {})
            room = intent.get("room_name")
            control_count += 1
            tasks.append(
                {
                    "task_id": task_id,
                    "intent_type": "device_control",
                    "description": intent.get("description", f"调整{device_label(device_type)}"),
                    "tool_name": "set_device_state",
                    "arguments": {
                        "room_name": room or "",
                        "device_type": device_type,
                        "attributes": attrs,
                    },
                    "room_name": room,
                    "device_type": device_type,
                    "attributes": attrs,
                    "priority": "high" if intent.get("clarity", 1) >= 0.8 else "medium",
                    "status": "pending",
                    "needs_approval": True,
                    "risk_level": "medium" if device_type == "door_lock" else "low",
                    "expected_effect": _describe_effect(device_type, attrs, room or ""),
                }
            )

        elif intent_type == "scene_trigger":
            scene_name = intent.get("scene_name", "")
            tasks.append(
                {
                    "task_id": task_id,
                    "intent_type": "scene_trigger",
                    "description": intent.get("description", f"触发{scene_name}"),
                    "tool_name": "trigger_scene",
                    "arguments": {"scene_name": scene_name},
                    "scene_name": scene_name,
                    "priority": "medium",
                    "status": "pending",
                    "needs_approval": True,
                    "risk_level": "medium",
                    "expected_effect": f"执行{scene_name}，批量调整相关设备",
                }
            )

        elif intent_type == "device_query":
            room = intent.get("room_name")
            device_type = intent.get("device_type")
            if device_type:
                tasks.append(
                    {
                        "task_id": task_id,
                        "intent_type": "device_query",
                        "description": f"查询{room or ''}{device_label(device_type)}状态",
                        "tool_name": "get_device_state",
                        "arguments": {"room_name": room or "", "device_type": device_type},
                        "room_name": room,
                        "device_type": device_type,
                        "priority": "low",
                        "status": "pending",
                        "needs_approval": False,
                        "risk_level": "low",
                        "expected_effect": "返回设备当前状态",
                    }
                )
            else:
                tasks.append(
                    {
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
                )

    needs_approval = any(task.get("needs_approval") for task in tasks)
    risk_level = "medium" if control_count > 1 or needs_approval else "low"
    for task in tasks:
        if task.get("risk_level") == "low":
            task["risk_level"] = risk_level
    return tasks


def build_rule_response(state: Dict[str, Any]) -> str:
    """规则版回复生成：知识查询、设备控制、情感关怀、闲聊四类。

    有实际工具执行结果时优先汇报结果（情感关怀由聊天链路单独产出）。
    """
    intents = state.get("intents", [])
    intent_types = {item.get("type") for item in intents}
    is_knowledge = state.get("is_knowledge_query") or "knowledge_query" in intent_types

    if is_knowledge:
        sources = state.get("rag_sources") or []
        context = state.get("rag_context") or ""
        if sources:
            source_names = "、".join(dict.fromkeys(s.get("source") or "知识库" for s in sources))
            return f"根据《{source_names}》：{context}"
        if context and context not in ("（无私有知识库相关内容）", "（私有知识库检索不可用）"):
            return f"根据知识库：{context}"
        return "暂未找到相关规定或偏好内容，您可以上传规章制度或偏好文档供我学习。"

    tool_results = state.get("tool_results") or []
    success = [r for r in tool_results if r.get("status") == "success"]
    failed = [r for r in tool_results if r.get("status") == "failed"]
    skipped = [r for r in tool_results if r.get("status") == "skipped"]

    if success or failed or skipped:
        lines = []
        for item in success:
            message = item.get("message") or item.get("data", {}).get("message")
            data = item.get("data") or {}
            if isinstance(data.get("status"), dict):
                status_text = "，".join(f"{key}={value}" for key, value in data["status"].items())
                lines.append(f"{item.get('description', '查询设备')}：{status_text}")
            elif data.get("devices"):
                device_names = "、".join(
                    f"{d.get('name') or device_label(d.get('type', ''))}"
                    for d in data["devices"][:20]
                )
                lines.append(f"{item.get('description', '设备列表')}：{device_names}")
            else:
                lines.append(f"已{message or item.get('description', '完成操作')}")
        for item in failed:
            error = item.get("error") or item.get("data", {}).get("error")
            lines.append(f"操作未完成：{item.get('description', '任务')}，原因：{error or '未知错误'}")
        for item in skipped:
            lines.append(f"已跳过：{item.get('description', '未勾选的任务')}")
        return "；".join(lines) if lines else "操作已完成。"

    if "emotional_care" in intent_types:
        return "收到，我已经记在心里啦。您可以告诉我想做什么，我马上帮您安排。"

    user_input = state.get("user_input", "")
    if not intent_types or intent_types == {"clarification"}:
        return "请告诉我您想做什么，比如“将卧室空调调到 27 度”或“我要回家了”。"
    return f"我理解您的需求是：{user_input}。相关功能已为您准备就绪。"


def _contains_any(text: str, keywords) -> bool:
    return any(keyword in text for keyword in keywords)


def _scene_avatar_emotion(scene_name: str) -> str:
    """把场景名映射为对应的虚拟形象动作。"""
    scene_name = scene_name or ""
    if _contains_any(scene_name, ("睡眠", "晚安", "夜间")):
        return "sleeping"
    if _contains_any(scene_name, ("节能", "省电", "离家", "低功耗")):
        return "energy_saving"
    return "controlling"


def _house_has_security_issue(state: Dict[str, Any]) -> bool:
    """检查当前家庭状态里是否存在安防类异常。"""
    for device in (state.get("house_status") or {}).get("devices") or []:
        status = device.get("status") or {}
        device_type = device.get("type", "")
        if device_type == "door_lock" and status.get("locked") is False:
            return True
        if device_type == "door_window_sensor" and status.get("status") == "open":
            return True
        if device_type == "leak_sensor" and status.get("leak"):
            return True
        if device_type == "gas_sensor" and status.get("gas_leak"):
            return True
        if device_type == "smoke_sensor" and (status.get("smoke") or status.get("alarm")):
            return True
    return False


def build_rule_avatar_emotion(state: Dict[str, Any]) -> str:
    """规则版虚拟形象状态：按意图、场景与执行结果切换动作。"""
    intents = state.get("intents") or []
    intent_types = {item.get("type") for item in intents}
    user_input = state.get("user_input") or ""
    tool_results = state.get("tool_results") or []

    if "emotional_care" in intent_types:
        return "caring"

    if _contains_any(user_input, ("安防", "安全", "门锁", "警报", "报警", "异常", "提醒")):
        return "security"
    if _house_has_security_issue(state):
        return "security"

    if any(r.get("status") == "failed" for r in tool_results):
        return "sad"

    scene_names = [
        item.get("scene_name", "")
        for item in intents
        if item.get("type") == "scene_trigger"
    ]
    if scene_names:
        return _scene_avatar_emotion(scene_names[0])

    if _contains_any(user_input, ("节能", "省电", "低功耗")):
        return "energy_saving"

    if any(r.get("status") == "success" for r in tool_results):
        if "device_control" in intent_types:
            security_types = (
                "door_lock",
                "door_window_sensor",
                "leak_sensor",
                "gas_sensor",
                "smoke_sensor",
            )
            if any(
                item.get("device_type") in security_types
                for item in intents
                if item.get("type") == "device_control"
            ):
                return "security"
            return "controlling"
        if "device_query" in intent_types:
            return "working"
        return "leisure"

    if state.get("is_knowledge_query") or "knowledge_query" in intent_types:
        return "neutral"
    if "device_control" in intent_types or "scene_trigger" in intent_types:
        return "controlling"
    if "device_query" in intent_types:
        return "working"
    if intent_types:
        return "leisure"
    return "idle"
