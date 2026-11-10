"""仓库层集成测试（内存 SQLite）。

这些用例首次给数据访问层建立了运行验证：
仓库跑在真实 SQL 引擎上，而不是靠读代码推断。

注意：用例用 `asyncio.run()` 包裹场景函数，原因见 tests/db.py 顶部说明。
"""

import asyncio
from datetime import datetime

from homemind.models.conversation import Conversation
from homemind.models.device import DeviceOperationLog
from homemind.models.file import UploadedFile
from homemind.rag.vector_store import FAMILY_COLLECTION, USER_COLLECTION
from homemind.repositories import default_status, unit_of_work
from tests.db import memory_database, seed_household

# ============ 设备仓库 ============


def test_device_find_active_respects_family_scope():
    """家庭隔离：family_id 不匹配时必须查不到设备。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                assert await uow.devices.find_active(ids["device_id"], ids["family_id"]) is not None
                assert await uow.devices.find_active(ids["device_id"], 999) is None
                # 不传 family_id 表示不做归属过滤（内部调用场景）
                assert await uow.devices.find_active(ids["device_id"]) is not None

    asyncio.run(scenario())


def test_device_soft_delete_excludes_from_active_queries():
    """软删除后不再出现在任何 active 查询里，但记录本身还在。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                device = await uow.devices.get(ids["device_id"])
                device.is_active = False
                await uow.commit()

            async with unit_of_work() as uow:
                assert await uow.devices.find_active(ids["device_id"], ids["family_id"]) is None
                assert await uow.devices.list_by_family(ids["family_id"]) == []
                assert await uow.devices.count_by_family(ids["family_id"]) == 0
                # 记录未被物理删除
                assert await uow.devices.get(ids["device_id"]) is not None

    asyncio.run(scenario())


def test_device_logs_are_newest_first():
    """操作日志按创建时间倒序返回。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                for index in range(3):
                    await uow.devices.add_log(
                        DeviceOperationLog(
                            family_id=ids["family_id"],
                            device_id=ids["device_id"],
                            user_id=ids["user_id"],
                            operation="update",
                            source="manual",
                            description=f"第 {index} 次",
                            created_at=datetime(2026, 1, 1, index),
                        )
                    )
                await uow.commit()

            async with unit_of_work() as uow:
                logs = await uow.devices.list_logs(ids["device_id"], ids["family_id"])
                assert [log.description for log in logs] == ["第 2 次", "第 1 次", "第 0 次"]

    asyncio.run(scenario())


def test_device_repository_list_by_room_and_type():
    """按房间 + 类型定位设备，类型不符时返回 None。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                found = await uow.devices.find_by_room_and_type(
                    ids["room_id"], "air_conditioner", ids["family_id"]
                )
                assert found is not None and found.id == ids["device_id"]
                assert (
                    await uow.devices.find_by_room_and_type(
                        ids["room_id"], "water_heater", ids["family_id"]
                    )
                    is None
                )
                assert len(await uow.devices.list_by_room(ids["room_id"], ids["family_id"])) == 1

    asyncio.run(scenario())


# ============ 房间仓库 ============


def test_room_count_devices_by_room_ignores_inactive():
    """设备计数只统计启用设备。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                counts = await uow.rooms.count_devices_by_room(ids["family_id"])
                assert counts == {ids["room_id"]: 1}

                device = await uow.devices.get(ids["device_id"])
                device.is_active = False
                await uow.commit()

            async with unit_of_work() as uow:
                assert await uow.rooms.count_devices_by_room(ids["family_id"]) == {}

    asyncio.run(scenario())


def test_room_find_active_by_name_scoped_to_family():
    """按名称查房间时 family_id 生效。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                room = await uow.rooms.find_active_by_name("卧室", ids["family_id"])
                assert room is not None and room.id == ids["room_id"]
                assert await uow.rooms.find_active_by_name("卧室", 999) is None

    asyncio.run(scenario())


# ============ 用户 / 家庭仓库 ============


def test_user_find_by_username_and_family_scope():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                assert await uow.users.find_by_username("owner01") is not None
                assert await uow.users.find_by_username("nobody") is None
                assert await uow.users.find(ids["user_id"], ids["family_id"]) is not None
                assert await uow.users.find(ids["user_id"], 999) is None
                assert await uow.users.count_by_family(ids["family_id"]) == 1

    asyncio.run(scenario())


def test_family_list_active_excludes_inactive():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                assert len(await uow.families.list_active()) == 1
                family = await uow.families.get(ids["family_id"])
                family.is_active = False
                await uow.commit()

            async with unit_of_work() as uow:
                assert await uow.families.list_active() == []

    asyncio.run(scenario())


# ============ 对话仓库 ============


def test_conversation_session_query_filters_and_orders():
    """只返回 user/assistant 消息，且按时间正序（供模型上下文使用）。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            rows = [
                ("user", "第一句", 0),
                ("assistant", "第二句", 1),
                ("tool", "工具结果", 2),
                ("user", "第三句", 3),
            ]
            async with unit_of_work() as uow:
                for role, content, minute in rows:
                    await uow.conversations.add(
                        Conversation(
                            family_id=ids["family_id"],
                            user_id=ids["user_id"],
                            session_id="s1",
                            role=role,
                            content=content,
                            created_at=datetime(2026, 1, 1, 0, minute),
                        )
                    )
                await uow.commit()

            async with unit_of_work() as uow:
                messages = await uow.conversations.list_by_session(
                    ids["family_id"], ids["user_id"], "s1"
                )
                assert [m.content for m in messages] == ["第一句", "第二句", "第三句"]

                deleted = await uow.conversations.delete_by_session(
                    ids["family_id"], ids["user_id"], "s1"
                )
                await uow.commit()
                assert deleted == 4

            async with unit_of_work() as uow:
                assert (
                    await uow.conversations.list_by_session(ids["family_id"], ids["user_id"], "s1")
                    == []
                )

    asyncio.run(scenario())


def test_conversation_delete_by_session_is_scoped_to_user():
    """重置会话不能删掉其他用户/其他会话的消息。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                await uow.conversations.add(
                    Conversation(
                        family_id=ids["family_id"],
                        user_id=ids["user_id"],
                        session_id="other-session",
                        role="user",
                        content="别的会话",
                    )
                )
                await uow.commit()

            async with unit_of_work() as uow:
                deleted = await uow.conversations.delete_by_session(
                    ids["family_id"], ids["user_id"], "s1"
                )
                await uow.commit()
                assert deleted == 0

            async with unit_of_work() as uow:
                assert len(await uow.conversations.list_recent(ids["user_id"])) == 1

    asyncio.run(scenario())


# ============ 文件仓库 ============


def test_file_visibility_family_regulation_vs_private():
    """家庭规章制度全家庭可见；私人文件仅上传者可见。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                await uow.files.add(
                    UploadedFile(
                        family_id=ids["family_id"],
                        user_id=ids["user_id"],
                        filename="规章制度.pdf",
                        file_path="/tmp/a.pdf",
                        file_type="pdf",
                        collection=FAMILY_COLLECTION,
                    )
                )
                await uow.files.add(
                    UploadedFile(
                        family_id=ids["family_id"],
                        user_id=ids["user_id"],
                        filename="我的简历.pdf",
                        file_path="/tmp/b.pdf",
                        file_type="pdf",
                        collection=USER_COLLECTION,
                    )
                )
                await uow.commit()

            async with unit_of_work() as uow:
                # 本人可见两份
                assert len(await uow.files.list_visible(ids["family_id"], ids["user_id"])) == 2
                # 同家庭其他住户只可见家庭规章制度
                others = await uow.files.list_visible(ids["family_id"], user_id=777)
                assert [f.filename for f in others] == ["规章制度.pdf"]

    asyncio.run(scenario())


def test_file_list_for_rebuild_only_pending_excluded():
    """重建索引只取 ready/failed 且路径非空的记录。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                for name, status in (("a.pdf", "ready"), ("b.pdf", "pending"), ("c.pdf", "failed")):
                    await uow.files.add(
                        UploadedFile(
                            family_id=ids["family_id"],
                            user_id=ids["user_id"],
                            filename=name,
                            file_path=f"/tmp/{name}",
                            file_type="pdf",
                            status=status,
                        )
                    )
                await uow.commit()

            async with unit_of_work() as uow:
                names = sorted(r.filename for r in await uow.files.list_for_rebuild())
                assert names == ["a.pdf", "c.pdf"]

    asyncio.run(scenario())


# ============ 偏好仓库 ============


def test_preference_upsert_insert_then_update():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                await uow.preferences.upsert(ids["user_id"], {"temperature": 26})
                await uow.commit()

            async with unit_of_work() as uow:
                assert (await uow.preferences.get(ids["user_id"])).preferences == {
                    "temperature": 26
                }
                await uow.preferences.upsert(ids["user_id"], {"temperature": 24, "mode": "cool"})
                await uow.commit()

            async with unit_of_work() as uow:
                record = await uow.preferences.get(ids["user_id"])
                assert record.preferences == {"temperature": 24, "mode": "cool"}
                assert record.user_id == ids["user_id"]

    asyncio.run(scenario())


# ============ 设备默认状态 ============


def test_default_status_returns_independent_copy():
    """默认状态必须返回副本，否则一处修改会污染全部新设备。"""
    first = default_status("air_conditioner")
    first["temperature"] = 999
    assert default_status("air_conditioner")["temperature"] == 26
    assert default_status("不存在的类型") == {"power": "off"}
