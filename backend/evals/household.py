"""评测用标准家庭。

评测必须可复现：所有用例都在同一个固定家庭上下文下运行，
与 database/init.sql 的演示数据保持一致（张三的家，4 个房间）。

这样做的好处是评测结果只反映"模型/规则的能力"，不掺入数据差异。
"""

from typing import Any

# 标准房间（与 init.sql 的 family_id=1 一致）
STANDARD_ROOMS: list[str] = ["客厅", "卧室", "厨房", "书房"]

# 标准设备：room_name + type，与 init.sql 的 devices 表一致
STANDARD_DEVICES: list[dict[str, Any]] = [
    {"room_name": "客厅", "type": "air_conditioner"},
    {"room_name": "卧室", "type": "air_conditioner"},
    {"room_name": "客厅", "type": "light"},
    {"room_name": "卧室", "type": "light"},
    {"room_name": "客厅", "type": "tv"},
    {"room_name": "客厅", "type": "air_purifier"},
    {"room_name": "卧室", "type": "humidifier"},
    {"room_name": "厨房", "type": "water_heater"},
    {"room_name": "厨房", "type": "fridge"},
    {"room_name": "客厅", "type": "door_lock"},
    {"room_name": "客厅", "type": "air_monitor"},
    {"room_name": "客厅", "type": "temp_humidity_sensor"},
    {"room_name": "卧室", "type": "temp_humidity_sensor"},
    {"room_name": "客厅", "type": "outdoor_sensor"},
    {"room_name": "客厅", "type": "weather_station"},
    {"room_name": "客厅", "type": "electricity_meter"},
    {"room_name": "客厅", "type": "water_meter"},
    {"room_name": "客厅", "type": "gas_meter"},
    {"room_name": "客厅", "type": "router"},
    {"room_name": "客厅", "type": "door_window_sensor"},
    {"room_name": "客厅", "type": "leak_sensor"},
    {"room_name": "客厅", "type": "gas_sensor"},
    {"room_name": "客厅", "type": "smoke_sensor"},
    {"room_name": "客厅", "type": "presence_sensor"},
]


def standard_device_types() -> set:
    """标准家庭的设备类型集合。"""
    return {row["type"] for row in STANDARD_DEVICES}
