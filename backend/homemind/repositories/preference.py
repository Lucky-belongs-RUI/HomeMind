"""用户偏好画像表的数据访问。"""

from __future__ import annotations

from homemind.models.preference import UserPreference
from homemind.repositories.base import BaseRepository


class PreferenceRepository(BaseRepository):
    """用户偏好画像读写（按 user_id 主键 upsert）。"""

    async def get(self, user_id: int) -> UserPreference | None:
        return await self.session.get(UserPreference, user_id)

    async def upsert(self, user_id: int, preferences: dict) -> UserPreference:
        record = await self.session.get(UserPreference, user_id)
        if record:
            record.preferences = preferences
        else:
            record = UserPreference(user_id=user_id, preferences=preferences)
            self.session.add(record)
        await self.session.flush()
        return record
