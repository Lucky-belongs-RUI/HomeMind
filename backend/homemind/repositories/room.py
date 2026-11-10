"""房间表的数据访问。"""

from __future__ import annotations

from sqlalchemy import func, select, update

from homemind.models.device import Device
from homemind.models.room import Room
from homemind.repositories.base import BaseRepository


class RoomRepository(BaseRepository):
    """房间表读写；家庭隔离条件由调用方通过 family_id 传入。"""

    async def get(self, room_id: int) -> Room | None:
        return await self.session.get(Room, room_id)

    async def find_active(self, room_id: int, family_id: int) -> Room | None:
        result = await self.session.execute(
            select(Room).where(Room.id == room_id, Room.family_id == family_id, Room.is_active == 1)
        )
        return result.scalar_one_or_none()

    async def find_active_by_name(self, name: str, family_id: int | None = None) -> Room | None:
        conditions = [Room.name == name, Room.is_active == 1]
        if family_id is not None:
            conditions.append(Room.family_id == family_id)
        result = await self.session.execute(select(Room).where(*conditions))
        return result.scalar_one_or_none()

    async def list_by_family(self, family_id: int) -> list[Room]:
        result = await self.session.execute(
            select(Room)
            .where(Room.family_id == family_id, Room.is_active == 1)
            .order_by(Room.sort_order)
        )
        return list(result.scalars().all())

    async def count_by_family(self, family_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(Room.family_id == family_id, Room.is_active == 1)
            )
            or 0
        )

    async def count_devices_by_room(self, family_id: int) -> dict[int, int]:
        """返回 {room_id: 设备数}，用于房间列表展示（一次查询代替 N 次）。"""
        result = await self.session.execute(
            select(Device.room_id, Device.id).where(
                Device.family_id == family_id, Device.is_active == 1
            )
        )
        counts: dict[int, int] = {}
        for room_id, _ in result.all():
            counts[room_id] = counts.get(room_id, 0) + 1
        return counts

    async def add(self, room: Room) -> Room:
        self.session.add(room)
        await self.session.flush()
        return room

    async def deactivate_by_family(self, family_id: int) -> None:
        await self.session.execute(
            update(Room).where(Room.family_id == family_id).values(is_active=False)
        )
