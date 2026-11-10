"""房间接口：CRUD（按家庭隔离）。

异常处理：服务层抛出领域异常，由全局处理器统一转译，本模块不做 try/except 包装。
"""

from fastapi import APIRouter, Depends

from homemind.api.deps import get_current_user, require_owner
from homemind.core.exceptions import NotFoundError
from homemind.schemas.responses import SuccessResponse
from homemind.schemas.room import (
    RoomCreate,
    RoomDetail,
    RoomItem,
    RoomUpdate,
    RoomWithCount,
)
from homemind.services import room_service

router = APIRouter(prefix="/rooms", tags=["房间"])


def _room_dict(room) -> dict:
    return {
        "id": room.id,
        "family_id": room.family_id,
        "name": room.name,
        "description": room.description,
        "icon": room.icon,
        "sort_order": room.sort_order,
    }


@router.get("", response_model=list[RoomWithCount])
async def list_rooms(current_user: dict = Depends(get_current_user)):
    """列出当前家庭所有房间（含设备数）。"""
    return await room_service.list_rooms_with_device_count(current_user["family_id"])


@router.post("", response_model=RoomItem)
async def create_room(
    payload: RoomCreate,
    current_user: dict = Depends(require_owner),
):
    """房主创建房间。"""
    return _room_dict(
        await room_service.create_room(payload.model_dump(), current_user["family_id"])
    )


@router.get("/{room_id}", response_model=RoomDetail)
async def get_room(
    room_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询单个房间（含设备列表）。"""
    detail = await room_service.get_room_detail(room_id, current_user["family_id"])
    if not detail:
        raise NotFoundError("房间不存在（可能不属于当前家庭）")
    return detail


@router.put("/{room_id}", response_model=RoomItem)
async def update_room(
    room_id: int,
    payload: RoomUpdate,
    current_user: dict = Depends(require_owner),
):
    """房主更新房间。"""
    room = await room_service.update_room(
        room_id, payload.model_dump(exclude_unset=True), current_user["family_id"]
    )
    return _room_dict(room)


@router.delete("/{room_id}", response_model=SuccessResponse)
async def delete_room(
    room_id: int,
    current_user: dict = Depends(require_owner),
):
    """房主删除房间（软删除）。"""
    return await room_service.delete_room(room_id, current_user["family_id"])
