"""Agent 规则引擎公共部分：设备 / 房间映射常量与文本匹配工具。

JSON 提取已迁到 `homemind.llm.structured`（与结构化输出校验放在一起，
避免 llm 层反向依赖 agent 层）。
"""

DEVICE_TYPE_ALIASES: dict[str, str] = {
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
    "热水": "water_heater",
    "洗衣机": "washer",
    "窗帘": "curtain",
    "窗户": "curtain",
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

DEVICE_LABELS: dict[str, str] = {
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

ROOM_ALIASES: dict[str, str] = {
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
    # v2.3：文档/知识类问题，让"讲解/介绍/文档"等触发 RAG 预判，
    # 不再只依赖模型自主检索（实测 qwen 对"讲解"类问题不一定会调用工具）
    "讲解",
    "介绍",
    "讲讲",
    "文档",
    "文件",
    "知识",
    "资料",
    "内容",
    "摘要",
    "讲了什么",
    "说了什么",
    "写的什么",
    "里面有什么",
    "查阅",
    "检索",
    "搜索",
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


def find_room(text: str, room_names: list[str] | None = None) -> str | None:
    """从用户文本中识别房间名。

    传入 room_names（家庭实际存在的房间）时优先精确匹配实际房间名：
    “主卧”和“次卧”都归一化为“卧室”，只看别名表会把它们错误地都指到“卧室”，
    进而规划出实际不存在的房间。无法落到真实房间时返回 None，交给后续澄清。
    """
    if not text:
        return None

    names = [name for name in (room_names or []) if name]
    contained = [name for name in names if name in text]
    if contained:
        return max(contained, key=len)

    for alias, room in ROOM_ALIASES.items():
        if alias in text:
            if not names:
                return room
            resolved = resolve_room_name(room, names)
            return resolved if resolved in names else None
    return None


def find_device_type(text: str) -> str | None:
    """从用户文本中识别设备类型（英文枚举值）。"""
    for alias, device_type in DEVICE_TYPE_ALIASES.items():
        if alias in text:
            return device_type
    return None


def find_device_types(text: str) -> list[str]:
    """识别文本中出现的全部设备类型，按首次出现位置排序并去重。"""
    matches: list[tuple[int, str]] = []
    for alias, device_type in DEVICE_TYPE_ALIASES.items():
        index = text.find(alias)
        if index == -1:
            continue
        if any(existing == device_type for _, existing in matches):
            continue
        matches.append((index, device_type))
    return [device_type for _, device_type in sorted(matches)]


def device_label(device_type: str) -> str:
    return DEVICE_LABELS.get(device_type, device_type)


def normalize_room_name(room_name: str) -> str:
    """将用户说法（主卧/次卧等）归一化为标准房间名。"""
    for alias, room in ROOM_ALIASES.items():
        if alias in room_name:
            return room
    return room_name


def resolve_room_name(room_name: str | None, room_names: list[str] | None) -> str | None:
    """把房间说法解析为家庭实际存在的房间名。

    解析顺序：精确同名 → 归一化后同名（实际房间就叫“卧室”）→
    同一标准名的唯一具体房间（说“卧室”而家里只有“主卧”）→ 文本包含匹配。
    都匹配不上时原样返回，由调用方决定是否澄清。
    """
    if not room_name:
        return None

    names = [name for name in (room_names or []) if name]
    text = room_name.strip()
    if not names:
        return text
    if text in names:
        return text

    canonical = normalize_room_name(text)
    if canonical in names:
        return canonical

    variants = [name for name in names if ROOM_ALIASES.get(name) == canonical]
    if len(variants) == 1:
        return variants[0]

    contained = [name for name in names if name in text or text in name]
    if contained:
        return max(contained, key=len)
    return text
