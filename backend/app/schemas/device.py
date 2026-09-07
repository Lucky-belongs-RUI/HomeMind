from typing import Any, Dict, Optional

from pydantic import BaseModel


class DeviceCreate(BaseModel):
    """创建设备请求。"""
    name: str
    type: str
    room_id: int
    brand: Optional[str] = None
    model: Optional[str] = None


class DeviceUpdate(BaseModel):
    """更新设备信息请求。"""
    name: Optional[str] = None
    type: Optional[str] = None
    room_id: Optional[int] = None
    brand: Optional[str] = None
    model: Optional[str] = None


class DeviceStatusUpdate(BaseModel):
    """更新设备状态请求（前端卡片控制使用）。"""
    attributes: Dict[str, Any]