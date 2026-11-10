"""Agent 工具集：设备控制、查询与场景触发。

所有工具执行都接收 family_id 并严格限定在当前家庭内操作，
避免跨家庭数据访问（开发文档 4.6）。
"""

import re
from typing import Any

from homemind.agent.tools.registry import ToolRegistry
from homemind.core.exceptions import PermissionDeniedError
from homemind.llm.types import ToolDefinition
from homemind.schemas.device import validate_device_attributes
from homemind.services.device_service import (
    CONTROLLABLE_TYPES,
    get_device_by_room_and_type,
    list_devices_by_family,
    list_devices_by_room,
    list_devices_by_type,
    update_device_status,
)
from homemind.services.room_service import get_room, get_room_by_name, list_rooms_by_family
from homemind.services.scene_service import execute_scene
from homemind.websocket.manager import broadcast_device_update

# ============ 工具定义（传给 LLM）============

TOOL_DEFINITIONS = [
    ToolDefinition(
        name="set_device_state",
        description=(
            "设置智能设备的状态。当用户要求控制设备时调用此工具。"
            "例如：将卧室空调调到27度、关闭客厅灯、打开窗帘。"
            "注意：设置空调温度时会自动开启空调。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "room_name": {
                    "type": "string",
                    "description": "房间名称，如：客厅、卧室、厨房、书房",
                },
                "device_type": {
                    "type": "string",
                    "description": (
                        "设备类型，可选值：air_conditioner(空调)、light(灯)、"
                        "robot_vacuum(扫地机器人)、curtain(窗帘)、speaker(音箱)、"
                        "tv(电视)、air_purifier(空气净化器)、humidifier(加湿器)、"
                        "water_heater(热水器)、washer(洗衣机)、fridge(冰箱)、"
                        "door_lock(智能门锁)、camera(摄像头)"
                    ),
                    "enum": [
                        "air_conditioner",
                        "light",
                        "robot_vacuum",
                        "curtain",
                        "speaker",
                        "tv",
                        "air_purifier",
                        "humidifier",
                        "water_heater",
                        "washer",
                        "fridge",
                        "door_lock",
                        "camera",
                    ],
                },
                "attributes": {
                    "type": "object",
                    "description": (
                        "要设置的状态键值对。空调可设：power(on/off)、temperature(16-30)、"
                        "mode(cool/heat/fan/dry/auto)、fan_speed(low/medium/high/auto)。"
                        "灯可设：power、brightness(0-100)、color。窗帘可设：position(0-100)。"
                        "电视可设：power、volume(0-100)、channel、input_source。"
                        "空气净化器可设：power、mode(auto/manual/sleep)、fan_speed。"
                        "加湿器可设：power、mode、target_humidity(30-80)。"
                        "热水器可设：power、temperature(30-75)、mode(standard/eco/turbo)。"
                        "洗衣机可设：power、status(idle/running/paused/finished)、mode、water_temp。"
                        "冰箱可设：power、temperature(1-10)、mode(smart/turbo/vacation)。"
                        "智能门锁可设：power、locked、auto_lock。"
                        "摄像头可设：power、recording、motion_detection、night_vision。"
                    ),
                    "additionalProperties": True,
                },
            },
            "required": ["room_name", "device_type", "attributes"],
        },
    ),
    ToolDefinition(
        name="get_device_state",
        description=(
            "查询设备当前状态与实时指标，支持全屋所有设备类型，例如：空调(air_conditioner)、灯(light)、"
            "空气质量检测仪(air_monitor)、温湿度传感器(temp_humidity_sensor)、室外气象站(weather_station)、"
            "智能电表(electricity_meter)、智能水表(water_meter)、智能燃气表(gas_meter)、路由器(router)、"
            "门窗/人体/水浸/燃气/烟雾传感器等。当用户询问设备状态、温度、湿度、空气质量、用电用水等数据时调用。"
            "room_name 可省略：该类型全屋唯一时自动定位，多台时返回设备列表。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "room_name": {"type": "string", "description": "房间名称，可省略"},
                "device_type": {"type": "string", "description": "设备类型"},
            },
            "required": ["device_type"],
        },
    ),
    ToolDefinition(
        name="list_room_devices",
        description="列出某房间的所有设备。当用户询问房间有哪些设备，或指令中房间/设备不明确时调用。",
        parameters={
            "type": "object",
            "properties": {
                "room_name": {
                    "type": "string",
                    "description": "房间名称，传 'all' 列出所有房间设备",
                }
            },
            "required": ["room_name"],
        },
    ),
    ToolDefinition(
        name="trigger_scene",
        description="触发预设场景，批量控制多个设备。如回家模式、睡眠模式。",
        parameters={
            "type": "object",
            "properties": {
                "scene_name": {"type": "string", "description": "场景名称，如：回家模式、睡眠模式"}
            },
            "required": ["scene_name"],
        },
    ),
    ToolDefinition(
        name="get_current_time",
        description=(
            "查询当前真实日期与时间（年、月、日、星期、几点几分、季节、时段）。"
            "当用户询问现在几点、几月几号、今天星期几、当前日期时间时调用。"
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDefinition(
        name="get_weather",
        description=(
            "查询家庭室外天气：从家庭气象站/室外温湿度传感器读取天气现象、室外温度、湿度、"
            "空气质量、PM2.5、气压、紫外线等实时数据。当用户询问今天天气、室外温度、气温、"
            "要不要加衣服等时调用。家庭未安装气象设备时返回无法查询。"
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    ),
]


def get_tool_definitions() -> list[ToolDefinition]:
    """返回当前家庭可用的工具定义列表。"""
    return registry.definitions()


# ============ 工具执行实现 ============


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    user_id: int,
    user_role: str,
    family_id: int,
) -> dict[str, Any]:
    """统一工具执行入口，按名字分发。family_id 用于数据隔离。"""
    return await registry.execute(tool_name, arguments, user_id, user_role, family_id)


def _require_control_permission(user_role: str) -> None:
    """访客仅可查看，不能控制设备或触发场景。"""
    if user_role not in ("owner", "resident"):
        raise PermissionDeniedError("需要房主或住户权限")


_NUMERIC_CONTROL_KEYS = frozenset(
    {
        "temperature",
        "freezer_temperature",
        "brightness",
        "position",
        "volume",
        "channel",
        "target_humidity",
        "water_temp",
    }
)
_NUMERIC_TEXT = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:度|摄氏度|°\s*C|℃|°|%|)\s*$", re.IGNORECASE)


def _coerce_numeric_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """容忍模型把数值参数写成“23°”“26度”这类字符串。"""
    coerced = dict(attributes)
    for key in _NUMERIC_CONTROL_KEYS:
        value = coerced.get(key)
        if not isinstance(value, str):
            continue
        match = _NUMERIC_TEXT.match(value)
        if not match:
            continue
        number = float(match.group(1))
        coerced[key] = int(number) if number.is_integer() else number
    return coerced


async def _tool_set_device_state(
    arguments: dict[str, Any], user_id: int, user_role: str, family_id: int
) -> dict[str, Any]:
    """★核心工具：设置设备状态，完整链路（含家庭隔离）。"""
    _require_control_permission(user_role)

    room_name = arguments["room_name"]
    device_type = arguments["device_type"]
    attributes = dict(arguments["attributes"])

    # 数据采集/安防类设备只读，防止 AI 误控传感器、计量表与路由器
    if device_type not in CONTROLLABLE_TYPES:
        return {
            "success": False,
            "error": f"设备类型 {device_type} 为数据采集/安防设备，仅支持查看状态",
        }

    # 设置空调温度时自动开启空调（开发文档约定）
    if (
        device_type == "air_conditioner"
        and "temperature" in attributes
        and "power" not in attributes
    ):
        attributes["power"] = "on"

    attributes = _coerce_numeric_attributes(attributes)
    try:
        validate_device_attributes(attributes)
    except ValueError as exc:
        return {"success": False, "error": f"设备状态不合法：{exc}"}

    room = await get_room_by_name(room_name, family_id)
    if not room:
        return {"success": False, "error": f"家庭中未找到房间: {room_name}"}

    device = await get_device_by_room_and_type(room.id, device_type, family_id)
    if not device:
        return {
            "success": False,
            "error": f"家庭中 {room_name} 未找到设备: {device_type}",
        }

    updated = await update_device_status(
        device_id=device.id,
        attributes=attributes,
        user_id=user_id,
        source="agent",
        family_id=family_id,
    )
    await broadcast_device_update(
        {
            "type": "device_status_update",
            "device_id": device.id,
            "family_id": device.family_id,
            "room_id": room.id,
            "device_type": device.type,
            "status": updated.status,
        }
    )
    summary = "、".join(f"{key}={value}" for key, value in attributes.items())
    return {
        "success": True,
        "message": f"已将{room.name}的{device.name}更新为: {summary}",
        "device": device.name,
        "status": updated.status,
    }


async def _tool_get_device_state(
    arguments: dict[str, Any], user_id: int, user_role: str, family_id: int
) -> dict[str, Any]:
    device_type = str(arguments.get("device_type") or "")
    room_name = str(arguments.get("room_name") or "").strip()
    if room_name:
        room = await get_room_by_name(room_name, family_id)
        if not room:
            return {"success": False, "error": f"家庭中未找到房间: {room_name}"}
        device = await get_device_by_room_and_type(room.id, device_type, family_id)
        if not device:
            return {
                "success": False,
                "error": f"家庭中 {room.name} 未找到设备: {device_type}",
            }
        return {
            "success": True,
            "device_id": device.id,
            "room_name": room.name,
            "device_type": device.type,
            "status": device.status,
        }

    devices = await list_devices_by_type(device_type, family_id)
    if not devices:
        return {"success": False, "error": f"家庭中未找到设备: {device_type}"}
    if len(devices) == 1:
        device = devices[0]
        room = await get_room(device.room_id, family_id)
        return {
            "success": True,
            "device_id": device.id,
            "room_name": room.name if room else "",
            "device_type": device.type,
            "status": device.status,
        }
    room_map = {room.id: room.name for room in await list_rooms_by_family(family_id)}
    return {
        "success": True,
        "room_name": "全部房间",
        "devices": [
            {
                "id": d.id,
                "name": d.name,
                "type": d.type,
                "room_name": room_map.get(d.room_id, ""),
                "status": d.status,
            }
            for d in devices
        ],
    }


async def _tool_list_room_devices(
    arguments: dict[str, Any], user_id: int, user_role: str, family_id: int
) -> dict[str, Any]:
    room_name = arguments.get("room_name", "all")
    if room_name == "all":
        devices = await list_devices_by_family(family_id)
        room_map = {room.id: room.name for room in await list_rooms_by_family(family_id)}
        seen: set[int] = set()
        result = []
        for device in devices:
            if device.id in seen:
                continue
            seen.add(device.id)
            result.append(
                {
                    "id": device.id,
                    "name": device.name,
                    "type": device.type,
                    "room_name": room_map.get(device.room_id, ""),
                    "status": device.status,
                }
            )
        return {"success": True, "room_name": "全部房间", "devices": result}

    room = await get_room_by_name(room_name, family_id)
    if not room:
        return {"success": False, "error": f"家庭中未找到房间: {room_name}"}
    devices = await list_devices_by_room(room.id, family_id)
    result = [
        {
            "id": device.id,
            "name": device.name,
            "type": device.type,
            "room_name": room.name,
            "status": device.status,
        }
        for device in devices
    ]
    return {"success": True, "room_name": room.name, "devices": result}


async def _tool_trigger_scene(
    arguments: dict[str, Any], user_id: int, user_role: str, family_id: int
) -> dict[str, Any]:
    _require_control_permission(user_role)

    return await execute_scene(
        scene_name=arguments["scene_name"],
        family_id=family_id,
        user_id=user_id,
        source="agent",
    )


# ============ 时间 / 天气查询工具（真实数据，非 mock）============

WEEKDAY_LABELS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

SEASON_BY_MONTH = {
    1: "冬季",
    2: "冬季",
    3: "春季",
    4: "春季",
    5: "春季",
    6: "夏季",
    7: "夏季",
    8: "夏季",
    9: "秋季",
    10: "秋季",
    11: "秋季",
    12: "冬季",
}


def _season_label(month: int) -> str:
    return SEASON_BY_MONTH.get(month, "")


def _period_label(hour: int) -> str:
    if 5 <= hour < 9:
        return "早上"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 23:
        return "晚上"
    return "凌晨"


async def _tool_get_current_time(
    arguments: dict[str, Any], user_id: int, user_role: str, family_id: int
) -> dict[str, Any]:
    """用 Python 直接读取系统真实时间，返回完整日期时间信息。

    签名与其他工具保持一致（注册表要求统一签名），本工具不使用任何入参。
    """
    from datetime import datetime

    now = datetime.now()
    date_text = now.strftime("%Y年%m月%d日")
    time_text = now.strftime("%H:%M")
    message = (
        f"现在是{date_text} {time_text}，{WEEKDAY_LABELS[now.weekday()]}，"
        f"{_season_label(now.month)}{_period_label(now.hour)}。"
    )
    return {
        "success": True,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": date_text,
        "time": time_text,
        "weekday": WEEKDAY_LABELS[now.weekday()],
        "season": _season_label(now.month),
        "period": _period_label(now.hour),
        "message": message,
    }


async def _tool_get_weather(
    arguments: dict[str, Any], user_id: int, user_role: str, family_id: int
) -> dict[str, Any]:
    """从家庭气象站/室外温湿度传感器读取真实天气；无相关设备明确返回无法查询。"""

    weather_stations = await list_devices_by_type("weather_station", family_id)
    outdoor_sensors = await list_devices_by_type("outdoor_sensor", family_id)
    source = (
        weather_stations[0]
        if weather_stations
        else (outdoor_sensors[0] if outdoor_sensors else None)
    )
    if source is None:
        return {
            "success": False,
            "error": "家庭中未安装气象站或室外温湿度传感器，无法查询天气",
        }
    room = await get_room(source.room_id, family_id) if source.room_id else None
    st = dict(source.status or {})
    temperature = st.get("temp")
    if temperature is None:
        temperature = st.get("temperature")
    return {
        "success": True,
        "source": source.name,
        "room_name": room.name if room else "",
        "weather": st.get("weather") or "",
        "temperature": temperature,
        "humidity": st.get("humidity"),
        "air_quality": st.get("air_quality"),
        "pm25": st.get("pm25"),
        "pressure": st.get("pressure"),
        # 气象站默认字段是 uv_index；兼容旧数据的 uv 写法
        "uv": st.get("uv_index") if st.get("uv_index") is not None else st.get("uv"),
        "wind_speed": st.get("wind_speed") or st.get("wind"),
        "message": (
            f"{source.name}（{room.name if room else ''}）显示：天气{st.get('weather') or '未知'}，"
            f"温度{temperature if temperature is not None else '未知'}℃，"
            f"湿度{st.get('humidity') if st.get('humidity') is not None else '未知'}%。"
        ),
    }


# ============ 注册表 ============
#
# 放在文件末尾：需要引用上面所有执行函数。
# 构造时做双向一致性校验——TOOL_DEFINITIONS 与 handlers 不匹配会在
# **导入阶段**直接抛 ToolRegistryError，而不是等用户对话时才发现。

registry = ToolRegistry(
    definitions=TOOL_DEFINITIONS,
    handlers={
        "set_device_state": _tool_set_device_state,
        "get_device_state": _tool_get_device_state,
        "list_room_devices": _tool_list_room_devices,
        "trigger_scene": _tool_trigger_scene,
        "get_current_time": _tool_get_current_time,
        "get_weather": _tool_get_weather,
    },
)
