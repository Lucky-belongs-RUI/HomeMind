"""工作单元：把一次业务操作涉及的仓库聚合到同一个数据库会话上。

原实现里每个 service 函数各自 `async with get_db_session()`，导致：
- 一次业务操作里多次查询要开多个会话（如家庭概览要 5 次查询 = 5 个连接）；
- 事务边界散落在各个函数里，跨实体的一致性无法保证。

引入 UnitOfWork 后，一次业务操作只开一个会话，仓库共享它，
service 显式调用 `uow.commit()` 结束事务——事务控制权回到应用层。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from homemind.core.database import get_db_session
from homemind.repositories.conversation import ConversationRepository
from homemind.repositories.device import DeviceRepository
from homemind.repositories.family import FamilyRepository
from homemind.repositories.file import FileRepository
from homemind.repositories.model_config import ModelConfigRepository
from homemind.repositories.preference import PreferenceRepository
from homemind.repositories.room import RoomRepository
from homemind.repositories.scene import SceneRepository
from homemind.repositories.user import UserRepository
from collections.abc import AsyncGenerator

class UnitOfWork:
    """一次业务操作共享的会话与仓库集合。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.devices = DeviceRepository(session)
        self.rooms = RoomRepository(session)
        self.scenes = SceneRepository(session)
        self.users = UserRepository(session)
        self.families = FamilyRepository(session)
        self.files = FileRepository(session)
        self.conversations = ConversationRepository(session)
        self.preferences = PreferenceRepository(session)
        self.model_configs = ModelConfigRepository(session)

    async def commit(self) -> None:
        """提交当前事务。"""
        await self.session.commit()

    async def refresh(self, instance: Any) -> None:
        """重新读取实例（用于取回数据库生成的默认值，如 created_at）。"""
        await self.session.refresh(instance)


@asynccontextmanager
async def unit_of_work() -> AsyncGenerator[UnitOfWork, None]:
    async with get_db_session() as session:
        yield UnitOfWork(session)
