"""场景表的数据访问。"""

from __future__ import annotations

from sqlalchemy import func, select, update

from homemind.models.scene import Scene
from homemind.repositories.base import BaseRepository


class SceneRepository(BaseRepository):
    """场景表读写；名称模糊匹配属于业务规则，留在 service 层。"""

    async def get(self, scene_id: int) -> Scene | None:
        return await self.session.get(Scene, scene_id)

    async def find_active(self, scene_id: int, family_id: int | None = None) -> Scene | None:
        conditions = [Scene.id == scene_id, Scene.is_active == 1]
        if family_id is not None:
            conditions.append(Scene.family_id == family_id)
        result = await self.session.execute(select(Scene).where(*conditions))
        return result.scalar_one_or_none()

    async def list_active(self, family_id: int) -> list[Scene]:
        result = await self.session.execute(
            select(Scene)
            .where(Scene.family_id == family_id, Scene.is_active == 1)
            .order_by(Scene.id)
        )
        return list(result.scalars().all())

    async def find_active_by_name(self, name: str, family_id: int) -> Scene | None:
        result = await self.session.execute(
            select(Scene).where(
                Scene.family_id == family_id,
                Scene.name == name,
                Scene.is_active == 1,
            )
        )
        return result.scalar_one_or_none()

    async def count_by_family(self, family_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(Scene.family_id == family_id, Scene.is_active == 1)
            )
            or 0
        )

    async def add(self, scene: Scene) -> Scene:
        self.session.add(scene)
        await self.session.flush()
        return scene

    async def deactivate_by_family(self, family_id: int) -> None:
        await self.session.execute(
            update(Scene).where(Scene.family_id == family_id).values(is_active=False)
        )
