"""设备接口：CRUD、状态更新与操作日志（按家庭隔离）。

异常处理：服务层抛出领域异常（`AppError` 子类），由 `homemind/core/handlers.py`
的全局处理器统一转译成带 code 的错误响应，本模块不再做 try/except 包装。
"""

from fastapi import APIRouter, Depends

from homemind.api.deps import get_current_user, require_owner, require_owner_or_resident
from homemind.core.exceptions import NotFoundError
from homemind.schemas.device import (
    DeviceCreate,
    DeviceItem,
    DeviceLogItem,
    DeviceStatusUpdate,
    DeviceUpdate,
)
from homemind.schemas.responses import SuccessResponse
from homemind.services import device_service
from homemind.websocket.manager import broadcast_device_update

router = APIRouter(prefix="/devices", tags=["设备"])


def _device_dict(device) -> dict:
    return {
        "id": device.id,
        "family_id": device.family_id,
        "name": device.name,
        "type": device.type,
        "room_id": device.room_id,
        "brand": device.brand,
        "model": device.model,
        "status": device.status,
        "created_at": device.created_at.isoformat() if device.created_at else None,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
    }


def _log_dict(log) -> dict:
    return {
        "id": log.id,
        "device_id": log.device_id,
        "user_id": log.user_id,
        "operation": log.operation,
        "source": log.source,
        "before_status": log.before_status,
        "after_status": log.after_status,
        "description": log.description,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("/room/{room_id}", response_model=list[DeviceItem])
async def list_by_room(
    room_id: int,
    current_user: dict = Depends(get_current_user),
):
    """按房间查询设备。"""
    devices = await device_service.list_devices_by_room(room_id, current_user["family_id"])
    return [_device_dict(d) for d in devices]


@router.get("/logs/{device_id}", response_model=list[DeviceLogItem])
async def list_logs(
    device_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询设备操作日志。"""
    logs = await device_service.get_device_logs(device_id, current_user["family_id"])
    return [_log_dict(log) for log in logs]


@router.get("", response_model=list[DeviceItem])
async def list_devices(current_user: dict = Depends(get_current_user)):
    """列出当前家庭所有设备。"""
    devices = await device_service.list_devices_by_family(current_user["family_id"])
    return [_device_dict(d) for d in devices]


@router.post("", response_model=DeviceItem)
async def create_device(
    payload: DeviceCreate,
    current_user: dict = Depends(require_owner),
):
    """房主创建设备。"""
    device = await device_service.create_device(payload.model_dump(), current_user["family_id"])
    return _device_dict(device)


@router.get("/{device_id}", response_model=DeviceItem)
async def get_device(
    device_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询单个设备。"""
    device = await device_service.get_device(device_id, current_user["family_id"])
    if not device:
        raise NotFoundError("设备不存在（可能不属于当前家庭）")
    return _device_dict(device)


@router.put("/{device_id}", response_model=DeviceItem)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    current_user: dict = Depends(require_owner),
):
    """房主更新设备信息。"""
    device = await device_service.update_device_info(
        device_id, payload.model_dump(exclude_unset=True), current_user["family_id"]
    )
    return _device_dict(device)


@router.delete("/{device_id}", response_model=SuccessResponse)
async def delete_device(
    device_id: int,
    current_user: dict = Depends(require_owner),
):
    """房主删除设备（软删除）。"""
    return await device_service.delete_device(
        device_id, current_user["family_id"], user_id=current_user["user_id"]
    )


@router.patch("/{device_id}/status", response_model=DeviceItem)
async def update_device_status_api(
    device_id: int,
    payload: DeviceStatusUpdate,
    current_user: dict = Depends(require_owner_or_resident),
):
    """手动更新设备状态（前端卡片控制），含家庭隔离校验。"""
    device = await device_service.update_device_status(
        device_id=device_id,
        attributes=payload.attributes,
        user_id=current_user["user_id"],
        source="manual",
        family_id=current_user["family_id"],
    )
    await broadcast_device_update(
        {
            "type": "device_status_update",
            "device_id": device.id,
            "family_id": device.family_id,
            "room_id": device.room_id,
            "device_type": device.type,
            "status": device.status,
        }
    )
    return _device_dict(device)
