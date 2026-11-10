"""Pydantic 请求/响应模型统一导出。"""

from homemind.schemas.agent import AgentChatRequest, TTSRequest
from homemind.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    SubAccountCreate,
)
from homemind.schemas.device import DeviceCreate, DeviceStatusUpdate, DeviceUpdate
from homemind.schemas.family import FamilyCreate, FamilyUpdate
from homemind.schemas.file import FileStatusResponse
from homemind.schemas.room import RoomCreate, RoomUpdate
from homemind.schemas.scene import SceneCreate, SceneUpdate
from homemind.schemas.user import UserUpdate

__all__ = [
    "AgentChatRequest",
    "TTSRequest",
    "ChangePasswordRequest",
    "LoginRequest",
    "RegisterRequest",
    "SubAccountCreate",
    "DeviceCreate",
    "DeviceStatusUpdate",
    "DeviceUpdate",
    "FamilyCreate",
    "FamilyUpdate",
    "FileStatusResponse",
    "RoomCreate",
    "RoomUpdate",
    "SceneCreate",
    "SceneUpdate",
    "UserUpdate",
]
