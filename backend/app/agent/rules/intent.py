"""规则版意图识别：无 API Key 或 LLM 输出异常时的降级实现。"""
from typing import Any, Dict, List, Optional

from app.agent.rules.common import (
    COLOR_MAP,
    KNOWLEDGE_QUERY_KEYWORDS,
    device_label,
    find_device_type,
    find_room,
)

# 非闲聊触发词（命中任一即走完整意图识别链路，而非纯聊天链路）
NON_CHAT_TRIGGERS = (
    # 设备控制
    "打开", "关闭", "关掉", "开启", "调整", "调高", "调低", "设置", "改一下", "调一调", "帮我调", "帮我",
    # 设备查询（问句/强词/指标词）
    "查看", "查询", "展示", "显示", "看看", "读取", "获取", "汇报", "多少度", "什么状态", "状态怎么样",
    "是否开着", "有没有开", "有哪些设备", "什么设备", "设备列表", "房间有什么",
    "数据", "指标", "数值", "余额", "电费", "水费", "气费", "用电", "电量", "用水", "用气", "燃气",
    "情况", "信息",
    "温度", "湿度", "空气质量", "pm", "pm2.5", "甲醛", "tvoc", "信号", "网速", "宽带", "在线设备",
    "天气", "气压", "紫外线", "风速", "门窗", "人体", "漏水", "烟雾", "燃气泄漏",
    # 场景
    "回家", "离家", "出门", "睡觉", "就寝", "观影", "会客", "晨起", "睡眠",
    # 情感 + 设备联动
    "感冒", "发烧", "不舒服", "头疼", "喉咙痛", "身体难受", "我有点冷", "感觉冷", "好冷", "太冷了", "太冷",
    "好热", "太热", "真热", "天黑了", "太黑了", "外面好吵", "太吵",
    # 报告
    "报告", "总结", "汇总", "报表", "统计", "梳理", "盘点",
)

# 报告类触发词
REPORT_TRIGGERS = ("报告", "总结", "汇总", "报表", "统计", "梳理", "盘点")


def looks_like_pure_chat(text: str) -> bool:
    """判断是否为纯闲聊/寒暄（无需数据库、无需设备上下文）。"""
    if find_device_type(text) or find_room(text):
        return False
    if any(keyword in text for keyword in KNOWLEDGE_QUERY_KEYWORDS):
        return False
    return not any(keyword in text for keyword in NON_CHAT_TRIGGERS)


def compute_active_chains(intents: List[Dict[str, Any]]) -> List[str]:
    """根据识别到的意图集合计算需要激活的链路（可多条，并发执行）。"""
    chains: List[str] = []
    for item in intents or []:
        intent_type = item.get("type")
        if intent_type in ("emotional_care", "chat"):
            if "chat" not in chains:
                chains.append("chat")
        elif intent_type == "knowledge_query":
            if "knowledge" not in chains:
                chains.append("knowledge")
        elif intent_type in ("device_control", "device_query", "scene_trigger"):
            if "control" not in chains:
                chains.append("control")
        elif intent_type == "report":
            if "report" not in chains:
                chains.append("report")
    if not chains:
        chains = ["chat"]
    return chains



METRIC_DEVICE_TYPES = [
    ("温度", ["temp_humidity_sensor", "outdoor_sensor", "weather_station"]),
    ("湿度", ["temp_humidity_sensor", "outdoor_sensor", "weather_station"]),
    ("空气质量", ["air_monitor"]),
    ("PM", ["air_monitor"]),
    ("甲醛", ["air_monitor"]),
    ("TVOC", ["air_monitor"]),
    ("用电", ["electricity_meter", "smart_plug"]),
    ("电费", ["electricity_meter"]),
    ("电量", ["electricity_meter", "smart_plug"]),
    ("余额", ["electricity_meter", "water_meter", "gas_meter"]),
    ("用水", ["water_meter"]),
    ("水费", ["water_meter"]),
    ("用气", ["gas_meter"]),
    ("燃气", ["gas_meter", "gas_sensor"]),
    ("气费", ["gas_meter"]),
    ("信号", ["router"]),
    ("网速", ["router"]),
    ("宽带", ["router"]),
    ("在线设备", ["router"]),
    ("天气", ["weather_station"]),
    ("气压", ["weather_station"]),
    ("紫外线", ["weather_station"]),
    ("风速", ["weather_station"]),
    ("门窗", ["door_window_sensor"]),
    ("人体", ["presence_sensor"]),
    ("漏水", ["leak_sensor"]),
    ("烟雾", ["smoke_sensor"]),
    ("燃气泄漏", ["gas_sensor"]),
]


def _match_device_by_metric(text: str, devices: List[Dict[str, Any]]) -> Optional[str]:
    """按指标词匹配家庭中实际存在的设备类型。"""
    available = {row.get("type") for row in devices or []}
    for keyword, device_types in METRIC_DEVICE_TYPES:
        if keyword in text:
            for device_type in device_types:
                if device_type in available:
                    return device_type
    return None




def _parse_attributes(text: str, device_type: str) -> Dict[str, Any]:
    """从用户文本提取设备属性，未识别时返回空字典。"""
    import re

    attrs: Dict[str, Any] = {}

    if device_type == "air_conditioner":
        temp_match = re.search(r"(\d{1,2})\s*度", text)
        if temp_match:
            attrs["temperature"] = int(temp_match.group(1))
        elif any(word in text for word in ("调高", "升高", "高一点", "热一点", "更暖")):
            attrs["temperature"] = 28
        elif any(word in text for word in ("调低", "降低", "低一点", "冷一点", "更凉")):
            attrs["temperature"] = 24
        if any(word in text for word in ("制冷", "冷风")):
            attrs["mode"] = "cool"
        elif "制热" in text or "暖风" in text:
            attrs["mode"] = "heat"
        elif "除湿" in text:
            attrs["mode"] = "dry"
        elif "送风" in text:
            attrs["mode"] = "fan"
        elif "睡眠" in text:
            attrs["mode"] = "sleep"
        if "开机" in text or "打开" in text or "开启" in text:
            attrs["power"] = "on"
        elif "关机" in text or "关闭" in text or "关掉" in text:
            attrs["power"] = "off"

    elif device_type == "light":
        bright_match = re.search(r"(\d{1,3})\s*%", text)
        if bright_match:
            attrs["brightness"] = int(bright_match.group(1))
        elif any(word in text for word in ("调亮", "亮一点", "更亮")):
            attrs["brightness"] = 100
        elif any(word in text for word in ("调暗", "暗一点", "更暗")):
            attrs["brightness"] = 30
        for color_name, color_value in COLOR_MAP.items():
            if color_name in text and ("颜色" in text or "变色" in text or f"{color_name}色" in text):
                attrs["color"] = color_value
                break
        if "开灯" in text or "打开" in text or "开启" in text:
            attrs["power"] = "on"
        elif "关灯" in text or "关闭" in text or "关掉" in text:
            attrs["power"] = "off"

    elif device_type == "curtain":
        if any(word in text for word in ("拉开", "打开", "全部拉开")):
            attrs["position"] = 100
        elif any(word in text for word in ("拉上", "关上", "关闭")):
            attrs["position"] = 0
        elif "一半" in text:
            attrs["position"] = 50

    elif device_type == "speaker":
        volume_match = re.search(r"音量.{0,4}(\d{1,3})", text)
        if volume_match:
            attrs["volume"] = int(volume_match.group(1))
        elif "调大" in text or "大声" in text:
            attrs["volume"] = 60
        elif "调小" in text or "小声" in text:
            attrs["volume"] = 10
        if "播放" in text:
            attrs["power"] = "on"
            attrs["playing"] = True
        elif "关闭" in text or "关掉" in text or "静音" in text:
            attrs["power"] = "off"
            attrs["playing"] = False

    elif device_type == "tv":
        volume_match = re.search(r"音量.{0,4}(\d{1,3})", text)
        if volume_match:
            attrs["volume"] = int(volume_match.group(1))
        channel_match = re.search(r"频道.{0,3}(\d{1,3})", text)
        if channel_match:
            attrs["channel"] = int(channel_match.group(1))
        if "打开" in text or "开机" in text:
            attrs["power"] = "on"
        elif "关闭" in text or "关机" in text:
            attrs["power"] = "off"

    elif device_type == "door_lock":
        if any(word in text for word in ("锁门", "上锁", "锁上")):
            attrs["locked"] = True
        elif any(word in text for word in ("开锁", "解锁", "开门")):
            attrs["locked"] = False

    elif device_type == "robot_vacuum":
        if "清扫" in text or "扫地" in text:
            attrs["power"] = "on"
            attrs["status"] = "running"
            attrs["cleaning_mode"] = "auto"

    elif device_type == "air_purifier":
        if "打开" in text or "开启" in text:
            attrs["power"] = "on"
        elif "关闭" in text or "关掉" in text:
            attrs["power"] = "off"

    elif device_type == "humidifier":
        if "打开" in text or "开启" in text:
            attrs["power"] = "on"
        elif "关闭" in text or "关掉" in text:
            attrs["power"] = "off"

    elif device_type == "water_heater":
        temp_match = re.search(r"(\d{1,2})\s*度", text)
        if temp_match:
            attrs["temperature"] = int(temp_match.group(1))
        if "烧水" in text or "加热" in text or "打开" in text or "开启" in text:
            attrs["power"] = "on"

    if not attrs:
        if "开" in text and any(word in text for word in ("打开", "开一下", "开启")):
            attrs["power"] = "on"
        elif "关" in text and any(word in text for word in ("关闭", "关掉", "关一下")):
            attrs["power"] = "off"
    return attrs


def _device_rooms(device_type: str, devices: List[Dict[str, Any]]) -> List[str]:
    rooms = []
    for device in devices:
        if device.get("type") == device_type and device.get("room_name"):
            room = device["room_name"]
            if room not in rooms:
                rooms.append(room)
    return rooms


def _build_device_options(devices: List[Dict[str, Any]]) -> List[str]:
    options = []
    for index, device in enumerate(devices[:8], 1):
        room = device.get("room_name") or "未分区"
        label = device_label(device.get("type", "设备"))
        options.append(f"{index}.{room}{label}")
    return options


def _control_intent(
    text: str,
    device_type: str,
    room: Optional[str],
    devices: List[Dict[str, Any]],
    clarity: float,
    description: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    attrs = _parse_attributes(text, device_type)
    if attributes:
        attrs = {**attrs, **attributes}
    intent: Dict[str, Any] = {
        "type": "device_control",
        "description": description,
        "device_type": device_type,
        "attributes": attrs,
        "clarity": clarity,
        "dependencies": {"room_name": room, "attributes": list(attrs.keys())},
    }
    if room:
        intent["room_name"] = room
    return intent


def build_rule_intents(
    text: str,
    rag_context: str = "",
    rooms: Optional[List[str]] = None,
    devices: Optional[List[Dict[str, Any]]] = None,
    season: str = "",
) -> Dict[str, Any]:
    """规则版意图识别：返回与 LLM 输出一致的结构。"""
    devices = devices or []
    result: Dict[str, Any] = {
        "intents": [],
        "intent_clarity_score": 1.0,
        "needs_clarification": False,
        "clarification_question": "",
        "clarification_options": [],
    }
    question = ""

    # 情感与生活场景（隐式意图）
    if any(word in text for word in ("感冒", "发烧", "不舒服", "头疼", "喉咙痛", "身体难受")):
        device_types = {row.get("type") for row in devices}
        ac_temp = 26
        if season == "冬季":
            ac_temp = 28
        elif season == "夏季":
            ac_temp = 24
        intents = [
            {"type": "emotional_care", "description": "表达关心并给出健康建议", "clarity": 0.95}
        ]
        if "air_conditioner" in device_types:
            intents.append(
                _control_intent(
                    text, "air_conditioner", None, devices, 0.85,
                    "根据季节调节室温", {"temperature": ac_temp, "power": "on"},
                )
            )
        if "curtain" in device_types:
            intents.append(
                _control_intent(
                    text, "curtain", None, devices, 0.85,
                    "关闭窗帘营造安静环境", {"position": 0},
                )
            )
        result.update(
            {
                "intents": intents,
                "intent_clarity_score": 0.85,
                "clarification_question": (
                    "听到您身体不适，需要我帮您调整室内环境吗？" if len(intents) > 1 else ""
                ),
            }
        )
        return result
    if any(word in text for word in ("我有点冷", "感觉冷", "好冷", "太冷了")):
        ac_temp = 28 if season == "冬季" else 26
        result.update(
            {
                "intents": [
                    _control_intent(text, "air_conditioner", None, devices, 0.85, "调高空调温度", {"temperature": ac_temp, "power": "on"}),
                    _control_intent(text, "curtain", None, devices, 0.85, "关闭窗帘保温", {"position": 0}),
                ],
                "intent_clarity_score": 0.85,
                "clarification_question": "需要我调高空调并拉上窗帘帮您保暖吗？",
            }
        )
        return result
    if "睡觉" in text or "就寝" in text:
        result.update(
            {
                "intents": [
                    _control_intent(text, "light", None, devices, 0.9, "关闭灯光", {"power": "off"}),
                    _control_intent(text, "air_conditioner", None, devices, 0.9, "空调切换睡眠模式", {"mode": "sleep", "power": "on"}),
                    _control_intent(text, "curtain", None, devices, 0.9, "关闭窗帘", {"position": 0}),
                    _control_intent(text, "speaker", None, devices, 0.9, "降低音量", {"volume": 0, "power": "off"}),
                ],
                "intent_clarity_score": 0.9,
                "clarification_question": "需要我为您准备睡眠模式吗？",
            }
        )
        return result
    if "外面好吵" in text or "太吵" in text:
        result.update(
            {
                "intents": [
                    _control_intent(text, "curtain", None, devices, 0.8, "关闭窗帘隔音", {"position": 0}),
                    _control_intent(text, "speaker", None, devices, 0.8, "降低音量", {"volume": 0}),
                ],
                "intent_clarity_score": 0.8,
                "clarification_question": "需要我关闭窗帘并降低音量吗？",
            }
        )
        return result
    if "天黑了" in text or "太黑了" in text:
        result.update(
            {
                "intents": [
                    _control_intent(text, "light", None, devices, 0.8, "打开灯光", {"power": "on"}),
                    _control_intent(text, "curtain", None, devices, 0.8, "关闭窗帘", {"position": 0}),
                ],
                "intent_clarity_score": 0.8,
                "clarification_question": "需要我为您打开灯光并拉上窗帘吗？",
            }
        )
        return result
    if "回家" in text:
        result.update(
            {
                "intents": [
                    {
                        "type": "scene_trigger",
                        "description": "触发回家模式",
                        "scene_name": "回家模式",
                        "clarity": 0.9,
                    }
                ],
                "intent_clarity_score": 0.9,
                "clarification_question": "",
            }
        )
        return result
    if "出门" in text or "离家" in text:
        result.update(
            {
                "intents": [
                    _control_intent(text, "light", None, devices, 0.85, "关闭灯光", {"power": "off"}),
                    _control_intent(text, "air_conditioner", None, devices, 0.85, "关闭空调", {"power": "off"}),
                    _control_intent(text, "curtain", None, devices, 0.85, "关闭窗帘", {"position": 0}),
                    _control_intent(text, "door_lock", None, devices, 0.85, "锁定门锁", {"locked": True}),
                ],
                "intent_clarity_score": 0.85,
                "clarification_question": "需要我关闭家中设备并锁门吗？",
            }
        )
        return result
    if "好热" in text or "太热" in text or "真热" in text:
        result.update(
            {
                "intents": [
                    _control_intent(text, "air_conditioner", None, devices, 0.85, "调低空调温度", {"temperature": 24, "power": "on"}),
                    _control_intent(text, "curtain", None, devices, 0.85, "拉开窗帘通风", {"position": 100}),
                    {"type": "emotional_care", "description": "提醒补充水分", "clarity": 0.9},
                ],
                "intent_clarity_score": 0.85,
                "clarification_question": "需要我调低空调并开窗通风吗？",
            }
        )
        return result

    # 报告生成
    if any(keyword in text for keyword in REPORT_TRIGGERS):
        result.update(
            {
                "intents": [
                    {
                        "type": "report",
                        "description": "生成家庭情况报告/总结",
                        "clarity": 0.9,
                    }
                ],
                "intent_clarity_score": 0.9,
                "clarification_question": "",
            }
        )
        return result

    # 知识查询（RAG 优先）
    if any(keyword in text for keyword in KNOWLEDGE_QUERY_KEYWORDS) or "有什么规定" in text:
        result.update(
            {
                "intents": [
                    {
                        "type": "knowledge_query",
                        "description": "查询知识库相关规定或偏好",
                        "clarity": 0.9,
                    }
                ],
                "intent_clarity_score": 0.9,
                "clarification_question": "",
            }
        )
        return result

    # 场景触发
    scene_names = ["回家模式", "睡眠模式", "离家模式", "观影模式", "会客模式", "晨起模式"]
    for scene_name in scene_names:
        if scene_name in text:
            result.update(
                {
                    "intents": [
                        {
                            "type": "scene_trigger",
                            "description": f"触发{scene_name}",
                            "scene_name": scene_name,
                            "clarity": 0.95,
                        }
                    ],
                    "intent_clarity_score": 0.95,
                    "clarification_question": "",
                }
            )
            return result

    # 设备查询：动作词 / 问句词 / 指标词均可触发
    QUERY_ACTION_WORDS = ("查看", "查询", "展示", "显示", "看看", "读取", "获取", "汇报")
    QUERY_QUESTION_WORDS = ("多少度", "什么状态", "状态怎么样", "是否开着", "有没有开")
    QUERY_STRONG_WORDS = ("数据", "指标", "情况", "信息", "数值", "余额", "电费", "水费", "气费")
    QUERY_METRIC_WORDS = tuple(keyword for keyword, _ in METRIC_DEVICE_TYPES)
    if (
        any(word in text for word in QUERY_ACTION_WORDS)
        or any(word in text for word in QUERY_QUESTION_WORDS)
        or any(word in text for word in QUERY_STRONG_WORDS)
        or (find_device_type(text) and any(word in text for word in QUERY_METRIC_WORDS))
    ):
        device_type = find_device_type(text)
        if not device_type:
            device_type = _match_device_by_metric(text, devices)
        room = find_room(text)
        clarity = 0.95 if device_type else 0.6
        intent: Dict[str, Any] = {
            "type": "device_query",
            "description": f"查询{device_label(device_type or '设备')}状态",
            "clarity": clarity,
        }
        if device_type:
            intent["device_type"] = device_type
        if room:
            intent["room_name"] = room
        result.update(
            {
                "intents": [intent],
                "intent_clarity_score": clarity,
                "clarification_question": "请问您想查询哪个房间、哪个设备？" if not device_type else "",
            }
        )
        return result
    if any(word in text for word in ("有哪些设备", "什么设备", "设备列表", "房间有什么")):
        room = find_room(text)
        result.update(
            {
                "intents": [
                    {
                        "type": "device_query",
                        "description": f"列出{room or '全部'}设备",
                        "room_name": room or "all",
                        "clarity": 0.95,
                    }
                ],
                "intent_clarity_score": 0.95,
                "clarification_question": "",
            }
        )
        return result

    # 设备控制
    device_type = find_device_type(text)
    room = find_room(text)
    if device_type:
        attrs = _parse_attributes(text, device_type)
        device_rooms = _device_rooms(device_type, devices)
        if not room and device_rooms and len(device_rooms) == 1:
            room = device_rooms[0]
        has_attr = bool(attrs)
        if room and has_attr:
            clarity = 0.9
        elif room and not has_attr:
            clarity = 0.55
            question = f"请问您想把{room}{device_label(device_type)}调整到什么状态？"
        elif not room and has_attr:
            clarity = 0.9 if len(device_rooms) <= 1 else 0.5
            if len(device_rooms) > 1:
                option_text = "、".join(
                    f"{index}.{room_name}" for index, room_name in enumerate(device_rooms[:6], 1)
                )
                question = f"请问您想调整哪个房间的{device_label(device_type)}？当前有：{option_text}"
        else:
            clarity = 0.5
            question = f"请问您想调整哪个房间的{device_label(device_type)}？"

        intent = _control_intent(
            text, device_type, room, devices, clarity, f"调整{room or ''}{device_label(device_type)}"
        )
        options = device_rooms[:6] if len(device_rooms) > 1 else []
        result.update(
            {
                "intents": [intent],
                "intent_clarity_score": clarity,
                "clarification_question": question,
                "clarification_options": options,
            }
        )
        return result

    # 仅表示“调整/设置”，未指明设备
    if any(word in text for word in ("调一下", "设置一下", "调整一下", "改一下", "帮我调", "调一调")):
        options = _build_device_options(devices)
        option_text = "、".join(options) if options else "当前家庭暂无设备"
        result.update(
            {
                "intents": [
                    {
                        "type": "clarification",
                        "description": "用户意图不明确，需要询问",
                        "clarity": 0.3,
                    }
                ],
                "intent_clarity_score": 0.3,
                "clarification_question": f"请问您想调整哪个设备？当前家庭有：{option_text}",
                "clarification_options": options,
            }
        )
        return result

    # 普通闲聊
    return result