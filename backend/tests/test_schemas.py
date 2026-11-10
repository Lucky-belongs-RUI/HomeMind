"""请求模型校验测试。

Pydantic 模型是 API 的第一道防线：非法输入必须在进入业务逻辑之前被拒绝，
而不是靠下游代码层层判空。
"""

import pytest
from pydantic import ValidationError

from homemind.schemas.agent import AgentChatRequest, ResumeRequest
from homemind.schemas.auth import (
    ChangePasswordRequest,
    RegisterRequest,
    SubAccountCreate,
)
from homemind.schemas.device import DeviceStatusUpdate

# ============================================================
# Agent 对话请求
# ============================================================


def test_agent_chat_request_defaults():
    request = AgentChatRequest(message="你好")
    assert request.session_id is None
    assert request.permission_mode == "normal"
    assert request.provider is None
    assert request.model is None


def test_agent_chat_request_requires_message():
    with pytest.raises(ValidationError):
        AgentChatRequest()


def test_agent_chat_request_rejects_unknown_permission_mode():
    """权限模式只允许 high / normal，防止任意字符串进入图状态。"""
    with pytest.raises(ValidationError):
        AgentChatRequest(message="x", permission_mode="super")


def test_agent_chat_request_accepts_high():
    assert AgentChatRequest(message="x", permission_mode="high").permission_mode == "high"


def test_resume_request_defaults_to_empty_dict():
    request = ResumeRequest(thread_id="thread_abc")
    assert request.resume_data == {}
    assert request.thread_id == "thread_abc"


# ============================================================
# 认证请求
# ============================================================


def test_register_request_enforces_min_password_length():
    with pytest.raises(ValidationError):
        RegisterRequest(family_name="家", username="u", password="12345", nickname="n")


def test_register_request_accepts_six_char_password():
    request = RegisterRequest(family_name="家", username="u", password="123456", nickname="n")
    assert request.password == "123456"
    assert request.description is None


def test_sub_account_role_is_restricted():
    """子账户只能是 resident 或 guest——不允许通过接口创建第二个 owner。"""
    with pytest.raises(ValidationError):
        SubAccountCreate(username="u", password="123456", nickname="n", role="owner")


def test_sub_account_accepts_valid_roles():
    for role in ("resident", "guest"):
        request = SubAccountCreate(username="u", password="123456", nickname="n", role=role)
        assert request.role == role


def test_change_password_request_enforces_min_length():
    with pytest.raises(ValidationError):
        ChangePasswordRequest(old_password="123456", new_password="123")


# ============================================================
# 设备状态更新
# ============================================================


def test_device_status_accepts_scalars_and_position():
    request = DeviceStatusUpdate(
        attributes={"power": "on", "brightness": 80, "position": {"x": 1.2, "y": 3}}
    )
    assert request.attributes["position"] == {"x": 1.2, "y": 3}


def test_device_status_rejects_nested_structures():
    """状态是 JSON 列，不能接受任意嵌套对象/数组（可被塞入超大 payload）。"""
    with pytest.raises(ValidationError):
        DeviceStatusUpdate(attributes={"power": {"nested": "on"}})
    with pytest.raises(ValidationError):
        DeviceStatusUpdate(attributes={"tags": ["a", "b"]})


def test_device_status_rejects_null():
    with pytest.raises(ValidationError):
        DeviceStatusUpdate(attributes={"temperature": None})


def test_device_status_rejects_non_numeric_metric():
    """数值字段写成字符串会让环境统计与图表直接报错。"""
    with pytest.raises(ValidationError):
        DeviceStatusUpdate(attributes={"temperature": "hot"})
    with pytest.raises(ValidationError):
        DeviceStatusUpdate(attributes={"temperature": True})


def test_device_status_rejects_invalid_position():
    with pytest.raises(ValidationError):
        DeviceStatusUpdate(attributes={"position": {"x": 1, "z": 2}})


def test_device_status_rejects_too_many_keys():
    with pytest.raises(ValidationError):
        DeviceStatusUpdate(attributes={f"k{i}": i for i in range(65)})
