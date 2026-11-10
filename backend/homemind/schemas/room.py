from typing import Any

from pydantic import BaseModel, ConfigDict

# ============================================================
# 请求模型
# ============================================================


class RoomCreate(BaseModel):
    """创建房间请求。"""

    name: str
    description: str | None = None
    icon: str | None = "home"
    sort_order: int | None = 0


class RoomUpdate(BaseModel):
    """更新房间请求。"""

    name: str | None = None
    description: str | None = None
    icon: str | None = None
    sort_order: int | None = None


# ============================================================
# 响应模型
# ============================================================


class RoomItem(BaseModel):
    """房间基础信息（对应 api/room.py 的 _room_dict）。

    from_attributes=True：`/families/{id}/rooms` 直接返回 ORM 列表，
    同一个模型需要同时支持 dict 与 ORM 对象。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    name: str
    description: str | None = None
    icon: str | None = None
    sort_order: int | None = None


class RoomWithCount(RoomItem):
    """房间列表项：额外带设备数（`GET /rooms` 用于侧边栏）。"""

    device_count: int = 0


class RoomDeviceItem(BaseModel):
    """房间详情内的设备摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    brand: str | None = None
    model: str | None = None
    status: dict[str, Any] | None = None


class RoomDetail(BaseModel):
    """房间详情：基础信息 + 设备列表。

    注意：该接口不返回 `sort_order`（与 `/rooms` 列表项不同），
    这里与既有行为保持一致，不做"顺手补齐"——那属于接口变更。
    """

    id: int
    family_id: int
    name: str
    description: str | None = None
    icon: str | None = None
    devices: list[RoomDeviceItem] = []
