"""房间服务：查询、增删改与房间详情。

SQL 已下沉到 RoomRepository / DeviceRepository。
"""

from homemind.core.exceptions import NotFoundError, ValidationError
from homemind.models.room import Room
from homemind.repositories import unit_of_work


async def get_room_by_name(name: str, family_id: int = None) -> Room | None:
    """按名称查房间。"""
    async with unit_of_work() as uow:
        return await uow.rooms.find_active_by_name(name, family_id)


async def get_room(room_id: int, family_id: int) -> Room | None:
    """按 id 查房间（含家庭归属校验）。"""
    async with unit_of_work() as uow:
        return await uow.rooms.find_active(room_id, family_id)


async def list_rooms_by_family(family_id: int) -> list[Room]:
    """列出家庭内房间（按 sort_order 排序）。"""
    async with unit_of_work() as uow:
        return await uow.rooms.list_by_family(family_id)


async def list_rooms_with_device_count(family_id: int) -> list[dict]:
    """房间列表（含设备数），供前端房间侧边栏使用。"""
    async with unit_of_work() as uow:
        rooms = await uow.rooms.list_by_family(family_id)
        counts = await uow.rooms.count_devices_by_room(family_id)
        return [
            {
                "id": room.id,
                "family_id": room.family_id,
                "name": room.name,
                "description": room.description,
                "icon": room.icon,
                "sort_order": room.sort_order,
                "device_count": counts.get(room.id, 0),
            }
            for room in rooms
        ]


async def get_room_detail(room_id: int, family_id: int) -> dict | None:
    """房间详情（含设备列表）。"""
    async with unit_of_work() as uow:
        room = await uow.rooms.find_active(room_id, family_id)
        if not room:
            return None
        devices = await uow.devices.list_by_room(room_id, family_id)
        return {
            "id": room.id,
            "family_id": room.family_id,
            "name": room.name,
            "description": room.description,
            "icon": room.icon,
            "devices": [
                {
                    "id": d.id,
                    "name": d.name,
                    "type": d.type,
                    "brand": d.brand,
                    "model": d.model,
                    "status": d.status,
                }
                for d in devices
            ],
        }


async def create_room(data: dict, family_id: int) -> Room:
    """创建房间。"""
    async with unit_of_work() as uow:
        room = Room(
            family_id=family_id,
            name=data["name"],
            description=data.get("description"),
            icon=data.get("icon", "home"),
            sort_order=data.get("sort_order", 0),
        )
        await uow.rooms.add(room)
        await uow.commit()
        await uow.refresh(room)
        return room


async def update_room(room_id: int, data: dict, family_id: int) -> Room:
    """更新房间信息。"""
    async with unit_of_work() as uow:
        room = await uow.rooms.find_active(room_id, family_id)
        if not room:
            raise NotFoundError("房间不存在")
        for key in ("name", "description", "icon", "sort_order"):
            if key in data:
                setattr(room, key, data[key])
        await uow.commit()
        await uow.refresh(room)
        return room


async def delete_room(room_id: int, family_id: int) -> dict:
    """软删除房间；房间内仍有设备时拒绝，避免设备失去归属房间。"""
    async with unit_of_work() as uow:
        room = await uow.rooms.find_active(room_id, family_id)
        if not room:
            raise NotFoundError("房间不存在")
        devices = await uow.devices.list_by_room(room_id, family_id)
        if devices:
            raise ValidationError("房间内仍有设备，请先移除或转移设备后再删除房间")
        room.is_active = False
        await uow.commit()
        return {"success": True}
