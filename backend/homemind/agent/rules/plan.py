"""规则版任务规划：模型不可用时的确定性兜底。

只处理**用户明确表达**的指令：
- 明确动作词 + 家庭中真实存在的设备/场景才生成控制任务；
- “我感冒了 / 好冷 / 不舒服”只生成闲聊关怀，不再自动联动设备；
- 时间、天气、报告、知识问题各归其位。

隐式生活场景（生病自动调温、关窗帘、烧水）已移除：
未经用户要求改变设备状态属于越权操作，也容易让回复声称未执行的动作。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from homemind.agent.rules.devices import (
    COLOR_MAP,
    KNOWLEDGE_QUERY_KEYWORDS,
    device_label,
    find_device_type,
    find_device_types,
    find_room,
)

REPORT_TRIGGERS = ("报告", "总结", "汇总", "报表", "统计", "梳理", "盘点")

_TIME_TRIGGERS = ("几点", "几点钟", "时间", "日期", "几号", "星期", "礼拜", "年月日")
_WEATHER_TRIGGERS = (
    "天气",
    "气温",
    "室外温度",
    "外面温度",
    "外面多少度",
    "室外多少度",
    "冷不冷",
    "热不热",
)
_SCENE_NAMES = (
    "回家模式",
    "睡眠模式",
    "离家模式",
    "观影模式",
    "会客模式",
    "晨起模式",
)
# 用户口语里的明确场景指令；只触发预设场景，不擅自拆成多条设备操作
_SCENE_WORDS = {
    "回家": "回家模式",
    "离家": "离家模式",
    "出门": "离家模式",
    "睡觉": "睡眠模式",
    "就寝": "睡眠模式",
}
_CARE_TRIGGERS = (
    "感冒",
    "发烧",
    "不舒服",
    "头疼",
    "喉咙痛",
    "身体难受",
    "我有点冷",
    "感觉冷",
    "好冷",
    "太冷",
    "好热",
    "太热",
    "真热",
    "难过",
    "不开心",
    "累了",
    "孤独",
)
_KNOWLEDGE_HINTS = tuple(KNOWLEDGE_QUERY_KEYWORDS) + (
    "药箱",
    "用药",
    "吃药",
    "吃什么药",
    "药物",
    "药品",
    "说明书",
    "病历",
    "过敏",
)
_QUERY_WORDS = (
    "查看",
    "查询",
    "展示",
    "显示",
    "看看",
    "读取",
    "获取",
    "汇报",
    "多少度",
    "什么状态",
    "状态怎么样",
    "是否开着",
    "有没有开",
    "情况",
    "数据",
    "指标",
    "数值",
    "余额",
    "电费",
    "水费",
    "气费",
    "用电",
    "水量",
    "用水",
    "用气",
    "温度",
    "湿度",
    "空气质量",
    "在哪个房间",
    "在哪个屋",
    "在哪里",
    "在哪儿",
    "放在哪",
    "位置",
    "位于",
)
# 有动作但识别不出设备时的兜底澄清，避免规则层把“帮我调一下”当成闲聊
_ACTION_HINTS = ("打开", "关闭", "关掉", "开启", "调节", "调一下", "调到", "设置", "切换", "启动")
# 知识问题里只有这些明确的查询词才同时执行设备查询
_EXPLICIT_QUERY_WORDS = (
    "查询",
    "查看",
    "看看",
    "显示",
    "读取",
    "获取",
    "多少度",
    "什么状态",
    "状态怎么样",
    "是否开着",
    "有没有开",
)
# 空调 / 热水器温度：兼容“26度”“23°”“23℃”“26 °C”“26摄氏度”
_TEMPERATURE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:°\s*C|℃|摄氏度|度|°)", re.IGNORECASE)
_CLAUSE_SPLIT = re.compile(r"[，,。；;！!？?\n]+")
# 知识/咨询类分句里的动作词不是控制指令，例如“打开空调费电吗”
_NON_COMMAND_MARKERS = (
    "怎么",
    "如何",
    "为什么",
    "注意",
    "讲讲",
    "介绍",
    "讲解",
    "文档",
    "资料",
    "规定",
    "费电",
    "省电",
    "耗电",
    "多少钱",
    "是什么",
    "有什么",
)


@dataclass
class RulePlan:
    tasks: list[dict[str, Any]] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_options: list[str] = field(default_factory=list)


def _temperature_value(text: str) -> int | float | None:
    match = _TEMPERATURE.search(text)
    if not match:
        return None
    value = float(match.group(1))
    return int(value) if value.is_integer() else value


def _parse_attributes(text: str, device_type: str) -> dict[str, Any]:
    """从中文指令中提取设备属性；无法识别时返回空字典。"""
    attrs: dict[str, Any] = {}

    if device_type == "air_conditioner":
        temperature = _temperature_value(text)
        if temperature is not None:
            attrs["temperature"] = temperature
        elif any(word in text for word in ("调高", "升高", "高一点", "热一点", "更暖")):
            attrs["temperature"] = 28
        elif any(word in text for word in ("调低", "降低", "低一点", "冷一点", "更凉")):
            attrs["temperature"] = 24
        if "制冷" in text or "冷风" in text:
            attrs["mode"] = "cool"
        elif "制热" in text or "暖风" in text:
            attrs["mode"] = "heat"
        elif "除湿" in text:
            attrs["mode"] = "dry"
        elif "送风" in text:
            attrs["mode"] = "fan"
        elif "睡眠" in text and any(
            word in text for word in ("模式", "调到", "设为", "设置", "切换", "开启")
        ):
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
            if color_name in text and (
                "颜色" in text or "变色" in text or f"{color_name}色" in text
            ):
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

    elif device_type == "water_heater":
        temperature = _temperature_value(text)
        if temperature is not None:
            attrs["temperature"] = temperature
        if any(word in text for word in ("烧", "加热", "打开", "开启")):
            attrs["power"] = "on"
        elif any(word in text for word in ("关", "停")):
            attrs["power"] = "off"

    elif device_type == "speaker":
        volume_match = re.search(r"音量[^\d]{0,4}(\d{1,3})", text)
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
        volume_match = re.search(r"音量[^\d]{0,4}(\d{1,3})", text)
        if volume_match:
            attrs["volume"] = int(volume_match.group(1))
        channel_match = re.search(r"频道[^\d]{0,3}(\d{1,3})", text)
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
        if any(word in text for word in ("停止", "暂停", "回充", "回去充电", "停止清扫")):
            attrs["power"] = "off"
            attrs["status"] = "idle"
        elif any(word in text for word in ("清扫", "扫地", "打扫", "开始")):
            attrs["power"] = "on"
            attrs["status"] = "cleaning"
            attrs["cleaning_mode"] = "auto"

    elif device_type in ("air_purifier", "humidifier"):
        if "打开" in text or "开启" in text:
            attrs["power"] = "on"
        elif "关闭" in text or "关掉" in text:
            attrs["power"] = "off"

    if not attrs:
        if "开" in text and any(word in text for word in ("打开", "开一下", "开启")):
            attrs["power"] = "on"
        elif "关" in text and any(word in text for word in ("关闭", "关掉", "关一下")):
            attrs["power"] = "off"
    return attrs


def _device_rooms(device_type: str, devices: list[dict[str, Any]]) -> list[str]:
    rooms: list[str] = []
    for device in devices:
        if device.get("type") == device_type and device.get("room_name"):
            room = str(device["room_name"])
            if room not in rooms:
                rooms.append(room)
    return rooms


def _task(task_id: str, tool: str, arguments: dict[str, Any], description: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "tool": tool,
        "arguments": arguments,
        "description": description,
    }


def _clarify_room(device_type: str, rooms: list[str]) -> tuple[str, list[str]]:
    label = device_label(device_type)
    options = [f"{index}.{room}{label}" for index, room in enumerate(rooms[:8], 1)]
    return f"请问您想调整哪个房间的{label}？当前有：{'、'.join(options)}", options


def _split_clauses(text: str) -> list[str]:
    return [part.strip() for part in _CLAUSE_SPLIT.split(str(text or "")) if part.strip()]


def _device_write_tasks(
    text: str,
    devices: list[dict[str, Any]],
    rooms: list[str],
) -> tuple[list[tuple[str, str, dict[str, Any], str]], list[tuple[str, list[str]]]]:
    """按分句解析显式设备指令，避免“一个设备名吃掉整句参数”。

    返回 (写任务, 待澄清问题)；每个分句独立解析，互不串参。
    """
    writes: dict[tuple[str, str], list[Any]] = {}
    questions: list[tuple[str, list[str]]] = []
    for clause in _split_clauses(text):
        if any(marker in clause for marker in _NON_COMMAND_MARKERS):
            continue
        for device_type in find_device_types(clause):
            attrs = _parse_attributes(clause, device_type)
            if not attrs:
                continue
            label = device_label(device_type)
            candidates = _device_rooms(device_type, devices)
            room = find_room(clause, rooms) or find_room(text, rooms)
            if not room and len(candidates) == 1:
                room = candidates[0]
            if not room and len(candidates) > 1:
                questions.append(_clarify_room(device_type, candidates))
                continue
            key = (device_type, room)
            if key in writes:
                writes[key][2].update(attrs)
            else:
                writes[key] = [device_type, room, attrs, f"调整{room}{label}"]
    return [
        (str(device_type), str(room), dict(attrs), str(description))
        for device_type, room, attrs, description in writes.values()
    ], questions


def control_tasks(
    text: str,
    devices: list[dict[str, Any]],
    rooms: list[str],
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """把一条显式指令解析成控制子图任务，返回 (tasks, 澄清问题, 选项)。"""
    tasks: list[dict[str, Any]] = []
    question = ""
    options: list[str] = []
    index = 0

    def _add(tool: str, arguments: dict[str, Any], description: str) -> None:
        nonlocal index
        index += 1
        tasks.append(_task(f"task_{index}", tool, arguments, description))

    if any(word in text for word in _TIME_TRIGGERS):
        _add("get_current_time", {}, "查询当前日期与时间")
    if any(word in text for word in _WEATHER_TRIGGERS):
        _add("get_weather", {}, "查询家庭室外天气")

    scene_names: list[str] = []
    for scene_name in _SCENE_NAMES:
        if scene_name in text and scene_name not in scene_names:
            scene_names.append(scene_name)
    implicit_scenes: list[str] = []
    for word, scene_name in _SCENE_WORDS.items():
        if word in text and scene_name not in scene_names and scene_name not in implicit_scenes:
            implicit_scenes.append(scene_name)

    if any(word in text for word in ("有哪些设备", "什么设备", "设备列表", "房间有什么")):
        for scene_name in scene_names + implicit_scenes:
            _add("trigger_scene", {"scene_name": scene_name}, f"触发{scene_name}")
        room = find_room(text, rooms) or "all"
        _add("list_room_devices", {"room_name": room}, f"列出{room}的设备")
        return tasks, question, options

    writes, write_questions = _device_write_tasks(text, devices, rooms)

    if writes:
        # 用户已经给出明确的设备指令时，不再叠加“睡觉/回家”等隐式场景，
        # 否则场景与显式设置会同时下发并互相覆盖。
        for scene_name in scene_names:
            _add("trigger_scene", {"scene_name": scene_name}, f"触发{scene_name}")
        for device_type, room, attrs, description in writes:
            _add(
                "set_device_state",
                {"room_name": room, "device_type": device_type, "attributes": attrs},
                description,
            )
        if write_questions:
            question, options = write_questions[0]
        return tasks, question, options

    for scene_name in scene_names + implicit_scenes:
        _add("trigger_scene", {"scene_name": scene_name}, f"触发{scene_name}")

    device_type = find_device_type(text)
    if not device_type:
        # 用户说的是指标而不是设备名：落到家庭里承载该指标的传感器/表计
        if any(word in text for word in ("温度", "湿度", "多少度", "空气质量")) and not any(
            word in text for word in _WEATHER_TRIGGERS
        ):
            device_type = "air_monitor" if "空气质量" in text else "temp_humidity_sensor"
        else:
            for word, meter_type in (
                ("用电", "electricity_meter"),
                ("电费", "electricity_meter"),
                ("用水", "water_meter"),
                ("水量", "water_meter"),
                ("水费", "water_meter"),
                ("用气", "gas_meter"),
                ("气费", "gas_meter"),
            ):
                if word in text:
                    device_type = meter_type
                    break
    if not device_type:
        return tasks, question, options

    label = device_label(device_type)
    candidates = _device_rooms(device_type, devices)
    room = find_room(text, rooms) or (candidates[0] if len(candidates) == 1 else "")
    attrs = _parse_attributes(text, device_type)
    if any(marker in text for marker in _NON_COMMAND_MARKERS):
        attrs = {}

    # 知识类问题（“有什么规定/讲解一下”）不应顺带执行设备查询
    if (
        any(keyword in text for keyword in _KNOWLEDGE_HINTS)
        and not attrs
        and not any(word in text for word in _EXPLICIT_QUERY_WORDS)
        and not any(word in text for word in _ACTION_HINTS)
    ):
        return tasks, question, options

    if attrs:
        if not room and len(candidates) > 1:
            question, options = _clarify_room(device_type, candidates)
            return tasks, question, options
        _add(
            "set_device_state",
            {"room_name": room, "device_type": device_type, "attributes": attrs},
            f"调整{room}{label}",
        )
        return tasks, question, options

    if any(word in text for word in _QUERY_WORDS):
        arguments: dict[str, Any] = {"device_type": device_type}
        if room:
            arguments["room_name"] = room
        _add("get_device_state", arguments, f"查询{room}{label}状态")
        return tasks, question, options

    question = f"请问您想把{room or ''}{label}调整到什么状态？"
    return tasks, question, options


def rule_plan(
    text: str,
    devices: list[dict[str, Any]],
    rooms: list[str],
) -> RulePlan:
    """无模型时的粗粒度任务规划。"""
    text = str(text or "").strip()
    tasks: list[dict[str, Any]] = []
    control, question, options = control_tasks(text, devices, rooms)

    if not control and not question and any(word in text for word in _ACTION_HINTS):
        question = "请补充一下要控制的房间、设备和目标状态？"

    if control:
        tasks.append({"branch": "control", "instruction": text, "query": ""})
    if any(keyword in text for keyword in REPORT_TRIGGERS):
        tasks.append({"branch": "report", "instruction": text, "query": ""})
    if any(keyword in text for keyword in _KNOWLEDGE_HINTS):
        tasks.append({"branch": "knowledge", "instruction": text, "query": text})
    if any(keyword in text for keyword in _CARE_TRIGGERS) or not tasks:
        tasks.append({"branch": "chat", "instruction": text, "query": ""})

    return RulePlan(
        tasks=tasks,
        needs_clarification=bool(question),
        clarification_question=question,
        clarification_options=options,
    )


# 回复证据校验复用同一套属性解析，保证“用户说了什么”与“回复声称什么”按同一口径比对
parse_attributes = _parse_attributes
SCENE_NAMES = _SCENE_NAMES
ACTION_HINTS = _ACTION_HINTS

__all__ = [
    "ACTION_HINTS",
    "RulePlan",
    "SCENE_NAMES",
    "control_tasks",
    "parse_attributes",
    "rule_plan",
]
