"""ORM 模型统一导出，确保 Base.metadata 注册全部表。"""
from app.models.family import Family
from app.models.user import User
from app.models.room import Room
from app.models.device import Device, DeviceOperationLog
from app.models.conversation import Conversation
from app.models.file import UploadedFile
from app.models.preference import UserPreference
from app.models.scene import Scene

__all__ = [
    "Family", "User", "Room", "Device", "DeviceOperationLog",
    "Conversation", "UploadedFile", "UserPreference", "Scene",
]
