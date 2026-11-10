"""用户个人模型配置的数据访问。"""

from __future__ import annotations

from sqlalchemy import select

from homemind.models.model_config import UserModelConfig
from homemind.repositories.base import BaseRepository


class ModelConfigRepository(BaseRepository):
    """按用户隔离的模型配置读写。"""

    async def list_by_user(self, user_id: int) -> list[UserModelConfig]:
        result = await self.session.execute(
            select(UserModelConfig)
            .where(UserModelConfig.user_id == user_id)
            .order_by(UserModelConfig.id.desc())
        )
        return list(result.scalars().all())

    async def find_for_user(self, user_id: int, config_id: int) -> UserModelConfig | None:
        result = await self.session.execute(
            select(UserModelConfig).where(
                UserModelConfig.id == config_id,
                UserModelConfig.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_name(self, user_id: int, name: str) -> UserModelConfig | None:
        result = await self.session.execute(
            select(UserModelConfig).where(
                UserModelConfig.user_id == user_id,
                UserModelConfig.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, record: UserModelConfig) -> UserModelConfig:
        self.session.add(record)
        await self.session.flush()
        return record

    async def delete(self, record: UserModelConfig) -> None:
        await self.session.delete(record)
