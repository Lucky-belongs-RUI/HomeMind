"""工具风险分级与服务端审批策略。

原则：授权只看服务端可信身份（role）与工具真实风险，
客户端传入的 permission_mode 不能成为免审批开关。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

RiskLevel = Literal["low", "medium", "high"]
PolicyAction = Literal["allow", "approval", "deny"]

_RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}

# 工具默认风险；设备类型可在 effective_risk 里进一步抬高
TOOL_RISK: dict[str, RiskLevel] = {
    "set_device_state": "low",
    "get_device_state": "low",
    "list_room_devices": "low",
    "trigger_scene": "high",
    "get_current_time": "low",
    "get_weather": "low",
    "retrieve_knowledge": "low",
}

WRITE_TOOLS = frozenset({"set_device_state", "trigger_scene"})

HIGH_RISK_DEVICE_TYPES = frozenset({"door_lock", "camera"})
MEDIUM_RISK_DEVICE_TYPES = frozenset({"water_heater"})


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    risk: RiskLevel
    reason: str


def _max_risk(left: RiskLevel, right: RiskLevel) -> RiskLevel:
    return left if _RISK_ORDER[left] >= _RISK_ORDER[right] else right


def effective_risk(tool_name: str, arguments: dict[str, Any] | None = None) -> RiskLevel:
    """结合工具与目标设备计算真实风险。"""
    risk: RiskLevel = TOOL_RISK.get(tool_name, "medium")
    args = arguments or {}
    device_type = str(args.get("device_type") or "")
    if device_type in HIGH_RISK_DEVICE_TYPES:
        risk = _max_risk(risk, "high")
    elif device_type in MEDIUM_RISK_DEVICE_TYPES:
        risk = _max_risk(risk, "medium")
    return risk


def decide_policy(user_role: str, risk: RiskLevel) -> PolicyDecision:
    """按角色与风险给出 allow / approval / deny。

    - 访客：只读放行，任何写操作拒绝；
    - 住户：低风险放行，中高风险必须审批；
    - 房主：低/中风险放行，高风险必须审批；
    - 高风险对任何人都不自动执行。
    """
    role = (user_role or "").strip().lower()
    if role not in ("owner", "resident", "visitor"):
        return PolicyDecision("deny", risk, "当前角色没有设备控制权限")

    if risk == "high":
        return PolicyDecision("approval", risk, "高风险操作必须人工确认")
    if risk == "medium":
        if role == "owner":
            return PolicyDecision("allow", risk, "房主可执行中风险操作")
        if role == "resident":
            return PolicyDecision("approval", risk, "中风险操作需要房主确认")
        return PolicyDecision("deny", risk, "访客不能执行中风险操作")
    return PolicyDecision("allow", risk, "低风险操作自动执行")


def decide_tool(user_role: str, tool_name: str, arguments: dict[str, Any] | None = None) -> PolicyDecision:
    """工具级策略入口：写工具 + 角色/风险统一裁决。"""
    role = (user_role or "").strip().lower()
    if tool_name in WRITE_TOOLS and role not in ("owner", "resident"):
        return PolicyDecision("deny", effective_risk(tool_name, arguments), "访客不能控制设备")
    return decide_policy(role, effective_risk(tool_name, arguments))


def idempotency_key(tool_name: str, arguments: dict[str, Any]) -> str:
    """同一设备同一动作生成稳定键，用于批内去重。"""
    target = {
        "tool": tool_name,
        "room": arguments.get("room_name"),
        "device": arguments.get("device_type"),
        "scene": arguments.get("scene_name"),
        "attributes": arguments.get("attributes") or {},
    }
    payload = json.dumps(target, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
