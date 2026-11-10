"""家庭表的数据访问。"""

from __future__ import annotations

from sqlalchemy import select

from homemind.models.family import Family
from homemind.repositories.base import BaseRepository


class FamilyRepository(BaseRepository):
    """家庭表读写。"""

    async def get(self, family_id: int) -> Family | None:
        return await self.session.get(Family, family_id)

    async def list_active(self) -> list[Family]:
        result = await self.session.execute(select(Family).where(Family.is_active == 1))
        return list(result.scalars().all())

    async def add(self, family: Family) -> Family:
        self.session.add(family)
        await self.session.flush()
        return family
