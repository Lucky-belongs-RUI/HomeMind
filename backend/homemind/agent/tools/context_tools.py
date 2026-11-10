"""上下文工具：用户画像与全屋快照按需加载。

请求入口不再预加载这两类数据，由 planner 根据本轮输入决定是否调用：
- 纯闲聊、纯知识问答不查设备库 / 偏好库；
- 设备控制、状态查询、家庭报告才加载全屋快照；
- 出现健康、冷暖、作息、偏好等个性化信号时才加载用户画像。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from homemind.agent.house_status import collect_house_status
from homemind.agent.runtime.persistence import get_store
from homemind.agent.tools.identity import extract_identity
from homemind.core.config import settings
from homemind.services.preference_service import get_user_preferences

logger = logging.getLogger(__name__)


def _timeout() -> float:
    return settings.agent_tool_timeout_seconds


@tool
async def get_user_profile(
    state: Annotated[dict, InjectedState] = None,
) -> dict[str, Any]:
    """读取当前登录用户的长期偏好画像（怕冷怕热、作息、忌口等）。

    只在需要个性化建议、健康关怀或默认偏好时调用。
    """
    identity = extract_identity(state or {})
    if identity is None:
        return {"success": False, "error": "缺少可信身份上下文"}
    user_id, _role, family_id = identity
    namespace = ("family", str(family_id), "user", str(user_id), "profile")

    store = get_store()
    if store is not None:
        try:
            item = await asyncio.wait_for(store.aget(namespace, "profile"), timeout=_timeout())
            if item and item.value:
                return {"success": True, "profile": dict(item.value)}
        except Exception as exc:
            logger.warning("读取长期画像失败，回退数据库: %s", exc)

    try:
        profile = await asyncio.wait_for(get_user_preferences(user_id), timeout=_timeout())
    except Exception as exc:
        return {"success": False, "error": f"读取用户画像失败: {exc}"}

    profile = dict(profile or {})
    if store is not None and profile:
        try:
            await asyncio.wait_for(
                store.aput(namespace, "profile", profile),
                timeout=_timeout(),
            )
        except Exception as exc:
            logger.warning("回填长期画像失败: %s", exc)
    return {"success": True, "profile": profile}


@tool
async def get_house_snapshot(
    state: Annotated[dict, InjectedState] = None,
) -> dict[str, Any]:
    """读取全屋房间、设备状态、环境指标与当前时间。

    只在设备控制、设备/房屋状态查询或家庭报告时调用。
    """
    identity = extract_identity(state or {})
    if identity is None:
        return {"success": False, "error": "缺少可信身份上下文"}
    _user_id, _role, family_id = identity

    try:
        snapshot = await asyncio.wait_for(
            collect_house_status(family_id),
            timeout=_timeout(),
        )
    except Exception as exc:
        return {"success": False, "error": f"读取全屋状态失败: {exc}"}
    return {"success": True, "snapshot": snapshot}


__all__ = ["get_house_snapshot", "get_user_profile"]
