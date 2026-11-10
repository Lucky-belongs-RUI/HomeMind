"""LangChain 工具层。

身份信息通过 InjectedState 注入，模型只能填业务参数。
这样即使发生提示注入，模型也无法伪造 user_id / family_id / role。
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from homemind.agent.tools.context_tools import get_house_snapshot, get_user_profile
from homemind.agent.tools.device_tools import execute_tool
from homemind.agent.tools.identity import extract_identity
from homemind.core.config import settings
from homemind.rag.retriever import retrieve_relevant_docs


async def _call_home_tool(
    tool_name: str,
    arguments: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    identity = extract_identity(state)
    if identity is None:
        return {"success": False, "error": "缺少可信身份上下文，拒绝执行工具"}
    user_id, role, family_id = identity
    try:
        return await asyncio.wait_for(
            execute_tool(tool_name, arguments, user_id, role, family_id),
            timeout=settings.agent_tool_timeout_seconds,
        )
    except TimeoutError:
        return {"success": False, "error": f"工具 {tool_name} 执行超时"}


@tool
async def set_device_state(
    room_name: str,
    device_type: str,
    attributes: dict[str, Any],
    state: Annotated[dict, InjectedState],
) -> dict[str, Any]:
    """设置某个房间内指定设备的属性，例如灯光开关、空调温度、窗帘开合。

    attributes 是设备属性字典，例如 {"power": "on"} 或 {"temperature": 26}。
    """
    return await _call_home_tool(
        "set_device_state",
        {"room_name": room_name, "device_type": device_type, "attributes": attributes},
        state,
    )


@tool
async def get_device_state(
    device_type: str,
    room_name: str = "",
    state: Annotated[dict, InjectedState] = None,
) -> dict[str, Any]:
    """查询指定设备状态；不传 room_name 时查询该类型在所有房间的状态。"""
    arguments: dict[str, Any] = {"device_type": device_type}
    if room_name:
        arguments["room_name"] = room_name
    return await _call_home_tool("get_device_state", arguments, state or {})


@tool
async def list_room_devices(
    room_name: str = "all",
    state: Annotated[dict, InjectedState] = None,
) -> dict[str, Any]:
    """列出某个房间的全部设备；room_name=all 时列出全屋设备。"""
    return await _call_home_tool("list_room_devices", {"room_name": room_name}, state or {})


@tool
async def trigger_scene(
    scene_name: str,
    state: Annotated[dict, InjectedState],
) -> dict[str, Any]:
    """触发家庭预设场景（批量控制多个设备），例如回家模式、睡眠模式。"""
    return await _call_home_tool("trigger_scene", {"scene_name": scene_name}, state)


@tool
async def get_current_time(
    state: Annotated[dict, InjectedState] = None,
) -> dict[str, Any]:
    """获取当前真实日期、时间、星期与时段。"""
    # 与其他工具一样走统一入口：保留身份校验与执行超时
    return await _call_home_tool("get_current_time", {}, state or {})


@tool
async def get_weather(state: Annotated[dict, InjectedState] = None) -> dict[str, Any]:
    """读取家庭气象站或室外传感器的真实天气数据。"""
    return await _call_home_tool("get_weather", {}, state or {})


@tool
async def retrieve_knowledge(
    query: str,
    top_k: int = 3,
    state: Annotated[dict, InjectedState] = None,
) -> dict[str, Any]:
    """检索家庭规章制度与用户上传的私有文档，返回带来源的片段。"""
    identity = extract_identity(state or {})
    if identity is None:
        return {"success": False, "error": "缺少可信身份上下文"}
    user_id, _role, family_id = identity
    try:
        docs = await retrieve_relevant_docs(
            query=query,
            user_id=user_id,
            family_id=family_id,
            top_k=top_k,
        )
    except Exception as exc:
        return {"success": False, "error": f"知识库检索失败: {exc}"}
    return {"success": True, "documents": docs}


TOOLS = [
    set_device_state,
    get_device_state,
    list_room_devices,
    trigger_scene,
    get_current_time,
    get_weather,
    retrieve_knowledge,
    get_user_profile,
    get_house_snapshot,
]

TOOLS_BY_NAME = {item.name: item for item in TOOLS}
