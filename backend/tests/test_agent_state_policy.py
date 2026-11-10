"""Agent 状态 reducer 与风险策略测试（零外部依赖）。"""

from typing import get_origin, get_type_hints

from homemind.agent.runtime.policy import (
    decide_policy,
    decide_tool,
    effective_risk,
    idempotency_key,
)
from homemind.agent.runtime.state import AgentState, BranchState, merge_dict, merge_emotion


def test_merge_dict_right_wins():
    assert merge_dict({"a": 1, "b": 2}, {"b": 3, "c": 4}) == {"a": 1, "b": 3, "c": 4}
    assert merge_dict(None, {"a": 1}) == {"a": 1}


def test_merge_emotion_keeps_non_empty():
    assert merge_emotion("caring", None) == "caring"
    assert merge_emotion("caring", "neutral") == "neutral"
    assert merge_emotion(None, None) == "idle"


def test_agent_state_parallel_channels_have_reducers():
    """并行分支写入的 channel 必须声明 reducer。"""
    hints = get_type_hints(AgentState, include_extras=True)
    for key in ("messages", "results", "tool_events", "token_usage", "avatar_emotion"):
        annotation = hints[key]
        assert get_origin(annotation) is not None or hasattr(annotation, "__metadata__"), key
        assert getattr(annotation, "__metadata__", ()), f"{key} 缺少 reducer"


def test_branch_state_is_isolated():
    """分支状态只包含 Send 注入的字段，不含主图控制字段。"""
    keys = set(BranchState.__annotations__)
    assert {"request", "query", "task", "results"} <= keys
    assert "clarification_attempts" not in keys
    assert "plan" not in keys


def test_visitor_cannot_write():
    decision = decide_tool("visitor", "set_device_state", {"device_type": "light"})
    assert decision.action == "deny"
    read = decide_tool("visitor", "get_device_state", {"device_type": "light"})
    assert read.action == "allow"


def test_resident_medium_requires_approval():
    decision = decide_policy("resident", "medium")
    assert decision.action == "approval"


def test_owner_medium_allowed_but_high_always_requires_approval():
    assert decide_policy("owner", "medium").action == "allow"
    assert decide_policy("owner", "high").action == "approval"
    assert decide_policy("resident", "high").action == "approval"


def test_door_lock_is_high_risk_regardless_of_tool_default():
    assert effective_risk("set_device_state", {"device_type": "door_lock"}) == "high"
    assert effective_risk("set_device_state", {"device_type": "light"}) == "low"


def test_idempotency_key_is_stable_and_sensitive_to_arguments():
    args = {"room_name": "客厅", "device_type": "light", "attributes": {"power": "on"}}
    assert idempotency_key("set_device_state", args) == idempotency_key(
        "set_device_state", dict(args)
    )
    changed = {"room_name": "卧室", "device_type": "light", "attributes": {"power": "on"}}
    assert idempotency_key("set_device_state", args) != idempotency_key(
        "set_device_state", changed
    )
