"""测试用内存数据库工具。

为什么用 `asyncio.run()` 而不是 pytest-asyncio：
本环境未安装该插件，若直接写 `async def test_*` 会被 pytest 静默跳过，
产生"全绿但没跑"的假象。用 asyncio.run() 包裹场景函数可以立即执行，
且不引入额外依赖。

用法::

    def test_something():
        async def scenario():
            async with memory_database():
                ids = await seed_household()
                assert await get_room(ids["room_id"], ids["family_id"])
        asyncio.run(scenario())

`memory_database()` 会把全局会话工厂临时指向内存 SQLite，
因此被调用的 service / 仓库代码无需任何改动即可跑在测试库上。
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import homemind.core.database as database
from homemind import models  # noqa: F401  导入以把全部表注册到 Base.metadata
from homemind.models.device import Device
from homemind.models.family import Family
from homemind.models.room import Room
from homemind.models.scene import Scene
from homemind.models.user import User
from homemind.repositories import default_status, unit_of_work


@asynccontextmanager
async def memory_database():
    """打开一个空的内存 SQLite 库，并把全局会话工厂临时指向它。

    StaticPool 让所有会话共用同一条连接——`:memory:` 库是按连接隔离的，
    不这样做每次新会话都会看到一个空库。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    with patch.object(database, "SessionLocal", factory):
        yield factory
    await engine.dispose()


async def seed_household(
    family_name: str = "张三的家",
    username: str = "owner01",
    room_name: str = "卧室",
) -> dict:
    """写入一套最小家庭数据（家庭 + 房主 + 房间 + 一台空调），返回各实体 id。"""
    async with unit_of_work() as uow:
        family = await uow.families.add(Family(name=family_name, owner_user_id=0))
        owner = await uow.users.add(
            User(
                username=username,
                password="plaintext-for-test",
                nickname="张三",
                role="owner",
                family_id=family.id,
            )
        )
        family.owner_user_id = owner.id
        room = await uow.rooms.add(
            Room(family_id=family.id, name=room_name, icon="bed", sort_order=1)
        )
        device = await uow.devices.add(
            Device(
                family_id=family.id,
                name=f"{room_name}空调",
                type="air_conditioner",
                room_id=room.id,
                status=default_status("air_conditioner"),
            )
        )
        await uow.commit()
        return {
            "family_id": family.id,
            "user_id": owner.id,
            "room_id": room.id,
            "device_id": device.id,
        }


async def seed_scene(family_id: int, device_id: int, name: str = "回家模式") -> int:
    """写入一个包含单条动作的场景，返回场景 id。"""
    async with unit_of_work() as uow:
        scene = await uow.scenes.add(
            Scene(
                family_id=family_id,
                name=name,
                actions={"actions": [{"device_id": device_id, "attributes": {"power": "on"}}]},
            )
        )
        await uow.commit()
        return scene.id
