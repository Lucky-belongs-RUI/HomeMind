"""Agent 规则引擎公共部分：设备/房间映射常量与 JSON 提取工具。"""
import json
import re
from typing import Any, Dict, List, Optional


DEVICE_TYPE_ALIASES: Dict[str, str] = {
"空气质量检测仪": "air_monitor",
    "空气质量监测仪": "air_monitor",
    "空气检测仪": "air_monitor",
    "空气监测仪": "air_monitor",
    "室外温湿度传感器": "outdoor_sensor",
    "室外温湿度计": "outdoor_sensor",
    "温湿度传感器": "temp_humidity_sensor",
    "温湿度计": "temp_humidity_sensor",
    "室外气象站": "weather_station",
    "气象站": "weather_station",
    "天气站": "weather_station",
    "智能电表": "electricity_meter",
    "电表": "electricity_meter",
    "智能插座": "smart_plug",
    "插座": "smart_plug",
    "智能水表": "water_meter",
    "水表": "water_meter",
    "智能燃气表": "gas_meter",
    "燃气表": "gas_meter",
    "煤气表": "gas_meter",
    "门窗传感器": "door_window_sensor",
    "门窗磁": "door_window_sensor",
    "门磁": "door_window_sensor",
    "窗磁": "door_window_sensor",
    "人体存在传感器": "presence_sensor",
    "人体传感器": "presence_sensor",
    "存在传感器": "presence_sensor",
    "水浸传感器": "leak_sensor",
    "漏水传感器": "leak_sensor",
    "燃气泄漏传感器": "gas_sensor",
    "燃气传感器": "gas_sensor",
    "煤气传感器": "gas_sensor",
    "烟雾传感器": "smoke_sensor",
    "烟雾报警器": "smoke_sensor",
    "烟感": "smoke_sensor",
    "路由器": "router",
    "无线路由器": "router",
    "无线网络设备": "router",
        "空气净化器": "air_purifier",
    "净化器": "air_purifier",
    "扫地机器人": "robot_vacuum",
    "扫地机": "robot_vacuum",
    "空调": "air_conditioner",
    "加湿器": "humidifier",
    "热水器": "water_heater",
    "洗衣机": "washer",
    "窗帘": "curtain",
    "音箱": "speaker",
    "音响": "speaker",
    "喇叭": "speaker",
    "电视": "tv",
    "冰箱": "fridge",
    "门锁": "door_lock",
    "智能锁": "door_lock",
    "摄像头": "camera",
    "监控": "camera",
    "灯光": "light",
    "照明": "light",
    "灯": "light",
}

DEVICE_LABELS: Dict[str, str] = {
    "air_monitor": "空气质量检测仪",
    "temp_humidity_sensor": "温湿度传感器",
    "outdoor_sensor": "室外温湿度传感器",
    "weather_station": "室外气象站",
    "electricity_meter": "智能电表",
    "smart_plug": "智能插座",
    "water_meter": "智能水表",
    "gas_meter": "智能燃气表",
    "door_window_sensor": "门窗传感器",
    "presence_sensor": "人体存在传感器",
    "leak_sensor": "水浸传感器",
    "gas_sensor": "燃气传感器",
    "smoke_sensor": "烟雾传感器",
    "router": "路由器",
    "air_conditioner": "空调",
    "light": "灯",
    "robot_vacuum": "扫地机器人",
    "curtain": "窗帘",
    "speaker": "音箱",
    "tv": "电视",
    "air_purifier": "空气净化器",
    "humidifier": "加湿器",
    "water_heater": "热水器",
    "washer": "洗衣机",
    "fridge": "冰箱",
    "door_lock": "智能门锁",
    "camera": "摄像头",
}

ROOM_ALIASES: Dict[str, str] = {
    "主卧": "卧室",
    "次卧": "卧室",
    "卧室": "卧室",
    "儿童房": "卧室",
    "老人房": "卧室",
    "客厅": "客厅",
    "厨房": "厨房",
    "书房": "书房",
    "阳台": "阳台",
    "餐厅": "餐厅",
    "卫生间": "卫生间",
    "浴室": "卫生间",
    "厕所": "卫生间",
}

KNOWLEDGE_QUERY_KEYWORDS = [
    "规定",
    "制度",
    "规则",
    "规范",
    "规章",
    "规矩",
    "公约",
    "偏好",
    "习惯",
    "要求",
    "几点下班",
]

COLOR_MAP = {
    "红": "#FF4D4F",
    "橙": "#FA8C16",
    "黄": "#FADB14",
    "绿": "#52C41A",
    "蓝": "#1677FF",
    "紫": "#722ED1",
    "白": "#FFFFFF",
    "暖": "#FFE1A8",
    "冷": "#BDE0FE",
}


def extract_json(text: Optional[str]) -> Optional[dict]:
    """从 LLM 输出中提取 JSON 对象，兼容 markdown 代码块。"""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def find_room(text: str) -> Optional[str]:
    """从用户文本中识别房间名（归一化为标准房间）。"""
    for alias, room in ROOM_ALIASES.items():
        if alias in text:
            return room
    return None


def find_device_type(text: str) -> Optional[str]:
    """从用户文本中识别设备类型（英文枚举值）。"""
    for alias, device_type in DEVICE_TYPE_ALIASES.items():
        if alias in text:
            return device_type
    return None


def device_label(device_type: str) -> str:
    return DEVICE_LABELS.get(device_type, device_type)


def normalize_room_name(room_name: str) -> str:
    """将用户说法（主卧/次卧等）归一化为标准房间名。"""
    for alias, room in ROOM_ALIASES.items():
        if alias in room_name:
            return room
    return room_name