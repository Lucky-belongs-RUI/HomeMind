"""Agent 工具集：设备控制、查询与场景触发。

所有工具执行都接收 family_id 并严格限定在当前家庭内操作，
避免跨家庭数据访问（开发文档 4.6）。
"""
from typing import Any, Dict, List

from app.llm.message import ToolDefinition

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
                    "enum": ["air_conditioner", "light", "robot_vacuum", "curtain", "speaker", "tv", "air_purifier", "humidifier", "water_heater", "washer", "fridge", "door_lock", "camera"],
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
]


def get_tool_definitions() -> List[ToolDefinition]:
    """返回当前家庭可用的工具定义列表。"""
    return TOOL_DEFINITIONS


# ============ 工具执行实现 ============

async def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: int,
    user_role: str,
    family_id: int,
) -> Dict[str, Any]:
    """统一工具执行入口，根据工具名分发。family_id 用于数据隔离。"""
    try:
        if tool_name == "set_device_state":
            return await _tool_set_device_state(arguments, user_id, user_role, family_id)
        if tool_name == "get_device_state":
            return await _tool_get_device_state(arguments, user_id, user_role, family_id)
        if tool_name == "list_room_devices":
            return await _tool_list_room_devices(arguments, user_id, user_role, family_id)
        if tool_name == "trigger_scene":
            return await _tool_trigger_scene(arguments, user_id, user_role, family_id)
        return {"success": False, "error": f"未知工具: {tool_name}"}
    except (ValueError, PermissionError) as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"工具执行异常: {exc}"}


def _require_control_permission(user_role: str) -> None:
    """访客仅可查看，不能控制设备或触发场景。"""
    if user_role not in ("owner", "resident"):
        raise PermissionError("需要房主或住户权限")


async def _tool_set_device_state(
    arguments: Dict[str, Any], user_id: int, user_role: str, family_id: int
) -> Dict[str, Any]:
    """★核心工具：设置设备状态，完整链路（含家庭隔离）。"""
    _require_control_permission(user_role)
    from app.services.device_service import get_device_by_room_and_type, update_device_status
    from app.services.room_service import get_room_by_name
    from app.websocket.manager import broadcast_device_update

    room_name = arguments["room_name"]
    device_type = arguments["device_type"]
    attributes = dict(arguments["attributes"])

    # 数据采集/安防类设备只读，防止 AI 误控传感器、计量表与路由器
    CONTROLLABLE_TYPES = {
        "air_conditioner", "light", "robot_vacuum", "curtain", "speaker",
        "tv", "air_purifier", "humidifier", "water_heater", "washer",
        "fridge", "door_lock", "camera",
    }
    if device_type not in CONTROLLABLE_TYPES:
        return {
            "success": False,
            "error": f"设备类型 {device_type} 为数据采集/安防设备，仅支持查看状态",
        }

    # 设置空调温度时自动开启空调（开发文档约定）
    if device_type == "air_conditioner" and "temperature" in attributes and "power" not in attributes:
        attributes["power"] = "on"

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
    arguments: Dict[str, Any], user_id: int, user_role: str, family_id: int
) -> Dict[str, Any]:
    from app.services.device_service import (
        get_device_by_room_and_type,
        list_devices_by_type,
    )
    from app.services.room_service import get_room, get_room_by_name

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
    return {
        "success": True,
        "room_name": "全部房间",
        "devices": [
            {"id": d.id, "name": d.name, "type": d.type, "status": d.status}
            for d in devices
        ],
    }


async def _tool_list_room_devices(
    arguments: Dict[str, Any], user_id: int, user_role: str, family_id: int
) -> Dict[str, Any]:
    from app.services.device_service import list_devices_by_family, list_devices_by_room
    from app.services.room_service import get_room_by_name

    room_name = arguments.get("room_name", "all")
    if room_name == "all":
        devices = await list_devices_by_family(family_id)
        result = [
            {"id": d.id, "name": d.name, "type": d.type, "status": d.status} for d in devices
        ]
        return {"success": True, "room_name": "全部房间", "devices": result}

    room = await get_room_by_name(room_name, family_id)
    if not room:
        return {"success": False, "error": f"家庭中未找到房间: {room_name}"}
    devices = await list_devices_by_room(room.id, family_id)
    result = [
        {"id": d.id, "name": d.name, "type": d.type, "status": d.status} for d in devices
    ]
    return {"success": True, "room_name": room.name, "devices": result}


async def _tool_trigger_scene(
    arguments: Dict[str, Any], user_id: int, user_role: str, family_id: int
) -> Dict[str, Any]:
    _require_control_permission(user_role)
    from app.services.scene_service import execute_scene

    return await execute_scene(
        scene_name=arguments["scene_name"],
        family_id=family_id,
        user_id=user_id,
        source="agent",
    )