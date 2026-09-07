from sqlalchemy import select

from app.database import get_db_session
from app.models.device import Device
from app.models.room import Room


async def get_room_by_name(name: str, family_id: int = None) -> Room | None:
    async with get_db_session() as db:
        conditions = [Room.name == name, Room.is_active == 1]
        if family_id is not None:
            conditions.append(Room.family_id == family_id)
        result = await db.execute(select(Room).where(*conditions))
        return result.scalar_one_or_none()


async def get_room(room_id: int, family_id: int) -> Room | None:
    async with get_db_session() as db:
        result = await db.execute(
            select(Room).where(Room.id == room_id, Room.family_id == family_id, Room.is_active == 1)
        )
        return result.scalar_one_or_none()


async def list_rooms_by_family(family_id: int) -> list[Room]:
    async with get_db_session() as db:
        result = await db.execute(
            select(Room)
            .where(Room.family_id == family_id, Room.is_active == 1)
            .order_by(Room.sort_order)
        )
        return list(result.scalars().all())


async def list_rooms_with_device_count(family_id: int) -> list[dict]:
    """房间列表（含设备数），供前端房间侧边栏使用。"""
    async with get_db_session() as db:
        result = await db.execute(
            select(Room)
            .where(Room.family_id == family_id, Room.is_active == 1)
            .order_by(Room.sort_order)
        )
        rooms = list(result.scalars().all())
        device_result = await db.execute(
            select(Device.room_id, Device.id).where(
                Device.family_id == family_id, Device.is_active == 1
            )
        )
        counts: dict[int, int] = {}
        for room_id, _ in device_result.all():
            counts[room_id] = counts.get(room_id, 0) + 1
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
    room = await get_room(room_id, family_id)
    if not room:
        return None
    from app.services.device_service import list_devices_by_room
    devices = await list_devices_by_room(room_id, family_id)
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
    async with get_db_session() as db:
        room = Room(
            family_id=family_id,
            name=data["name"],
            description=data.get("description"),
            icon=data.get("icon", "home"),
            sort_order=data.get("sort_order", 0),
        )
        db.add(room)
        await db.commit()
        await db.refresh(room)
        return room


async def update_room(room_id: int, data: dict, family_id: int) -> Room:
    async with get_db_session() as db:
        room = await db.get(Room, room_id)
        if not room or room.family_id != family_id:
            raise ValueError("房间不存在")
        for key in ("name", "description", "icon", "sort_order"):
            if key in data:
                setattr(room, key, data[key])
        await db.commit()
        await db.refresh(room)
        return room


async def delete_room(room_id: int, family_id: int) -> dict:
    async with get_db_session() as db:
        room = await db.get(Room, room_id)
        if not room or room.family_id != family_id:
            raise ValueError("房间不存在")
        room.is_active = False
        await db.commit()
        return {"success": True}
