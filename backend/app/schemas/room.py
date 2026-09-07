from typing import Optional

from pydantic import BaseModel


class RoomCreate(BaseModel):
    """创建房间请求。"""
    name: str
    description: Optional[str] = None
    icon: Optional[str] = "home"
    sort_order: Optional[int] = 0


class RoomUpdate(BaseModel):
    """更新房间请求。"""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None