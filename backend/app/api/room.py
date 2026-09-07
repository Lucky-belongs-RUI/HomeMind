"""房间接口：CRUD（按家庭隔离）。"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_owner
from app.schemas.room import RoomCreate, RoomUpdate
from app.services import room_service

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


@router.get("")
async def list_rooms(current_user: dict = Depends(get_current_user)):
    """列出当前家庭所有房间（含设备数）。"""
    return await room_service.list_rooms_with_device_count(current_user["family_id"])


@router.post("")
async def create_room(
    payload: RoomCreate,
    current_user: dict = Depends(require_owner),
):
    """房主创建房间。"""
    return _room_dict(
        await room_service.create_room(payload.model_dump(), current_user["family_id"])
    )


@router.get("/{room_id}")
async def get_room(
    room_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询单个房间（含设备列表）。"""
    detail = await room_service.get_room_detail(room_id, current_user["family_id"])
    if not detail:
        raise HTTPException(status_code=404, detail="房间不存在（可能不属于当前家庭）")
    return detail


@router.put("/{room_id}")
async def update_room(
    room_id: int,
    payload: RoomUpdate,
    current_user: dict = Depends(require_owner),
):
    """房主更新房间。"""
    try:
        room = await room_service.update_room(
            room_id, payload.model_dump(exclude_unset=True), current_user["family_id"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _room_dict(room)


@router.delete("/{room_id}")
async def delete_room(
    room_id: int,
    current_user: dict = Depends(require_owner),
):
    """房主删除房间（软删除）。"""
    try:
        return await room_service.delete_room(room_id, current_user["family_id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))