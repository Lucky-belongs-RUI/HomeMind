"""用户表的数据访问。"""

from __future__ import annotations

from sqlalchemy import func, select

from homemind.models.user import User
from homemind.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """用户表读写。"""

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def find(self, user_id: int, family_id: int | None = None) -> User | None:
        conditions = [User.id == user_id]
        if family_id is not None:
            conditions.append(User.family_id == family_id)
        result = await self.session.execute(select(User).where(*conditions))
        return result.scalar_one_or_none()

    async def find_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def list_by_family(self, family_id: int, ordered: bool = False) -> list[User]:
        query = select(User).where(User.family_id == family_id)
        if ordered:
            query = query.order_by(User.id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_family(self, family_id: int) -> int:
        return int(
            await self.session.scalar(select(func.count()).where(User.family_id == family_id)) or 0
        )

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
