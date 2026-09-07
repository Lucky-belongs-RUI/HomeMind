"""Pydantic 请求/响应模型统一导出。"""
from app.schemas.agent import AgentChatRequest, TTSRequest
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    SubAccountCreate,
)
from app.schemas.device import DeviceCreate, DeviceStatusUpdate, DeviceUpdate
from app.schemas.family import FamilyCreate, FamilyUpdate
from app.schemas.file import FileStatusResponse
from app.schemas.room import RoomCreate, RoomUpdate
from app.schemas.scene import SceneCreate, SceneUpdate
from app.schemas.user import UserUpdate

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