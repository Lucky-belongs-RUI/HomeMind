"""service 层集成测试（内存 SQLite）。

仓库层测试保证「SQL 写对了」，这里保证「业务规则仍然成立」——
尤其是家庭隔离、软删除、级联清理、密码升级这些容易在重构中被改坏的行为。

注意：用例用 `asyncio.run()` 包裹场景函数，原因见 tests/db.py 顶部说明。
"""

import asyncio

import pytest

from homemind.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from homemind.models.device import Device
from homemind.models.scene import Scene
from homemind.repositories import default_status, unit_of_work
from homemind.services import (
    conversation_service,
    device_service,
    family_service,
    room_service,
    scene_service,
    user_service,
)
from homemind.services.auth_service import auth_service
from homemind.services.password_service import is_hashed
from tests.db import memory_database, seed_household, seed_scene

# ============ 设备服务 ============


def test_update_device_status_merges_attributes_and_writes_log():
    """状态是增量合并（不是整体替换），并留下一条操作日志。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            device = await device_service.update_device_status(
                device_id=ids["device_id"],
                attributes={"temperature": 28},
                user_id=ids["user_id"],
                source="manual",
                family_id=ids["family_id"],
            )
            # 只改了 temperature，power/mode 等原有字段必须保留
            assert device.status["temperature"] == 28
            assert device.status["power"] == "off"
            assert device.status["mode"] == "cool"

            logs = await device_service.get_device_logs(ids["device_id"], ids["family_id"])
            assert len(logs) == 1
            assert logs[0].before_status["temperature"] == 26
            assert logs[0].after_status["temperature"] == 28
            assert logs[0].user_id == ids["user_id"]

    asyncio.run(scenario())


def test_update_device_status_rejects_cross_family():
    """家庭隔离：用别的 family_id 操作设备必须被拒绝。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            with pytest.raises(PermissionDeniedError):
                await device_service.update_device_status(
                    device_id=ids["device_id"],
                    attributes={"power": "on"},
                    user_id=ids["user_id"],
                    family_id=999,
                )
            # 拒绝后状态不能被改动
            device = await device_service.get_device(ids["device_id"], ids["family_id"])
            assert device.status["power"] == "off"

    asyncio.run(scenario())


def test_update_device_status_unknown_device_raises_not_found():
    async def scenario():
        async with memory_database():
            await seed_household()
            with pytest.raises(NotFoundError):
                await device_service.update_device_status(
                    device_id=123456, attributes={"power": "on"}, user_id=1
                )

    asyncio.run(scenario())


def test_device_queries_are_family_scoped():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            assert await device_service.get_device(ids["device_id"], 999) is None
            assert await device_service.list_devices_by_room(ids["room_id"], 999) == []
            assert len(await device_service.list_devices_by_family(ids["family_id"])) == 1

    asyncio.run(scenario())


def test_create_device_uses_type_default_status():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            device = await device_service.create_device(
                data={"name": "热水器", "type": "water_heater", "room_id": ids["room_id"]},
                family_id=ids["family_id"],
            )
            assert device.status == default_status("water_heater")
            assert device.status["temperature"] == 45

    asyncio.run(scenario())


def test_create_device_rejects_room_from_another_family():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            with pytest.raises(ValidationError):
                await device_service.create_device(
                    data={"name": "空调", "type": "air_conditioner", "room_id": ids["room_id"]},
                    family_id=999,
                )

    asyncio.run(scenario())


def test_sensor_rejects_new_control_attribute_but_allows_existing_metrics():
    """传感器只读：不能新增控制字段，但允许修正已有的环境读数。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                sensor = await uow.devices.add(
                    Device(
                        family_id=ids["family_id"],
                        name="空气检测仪",
                        type="air_monitor",
                        room_id=ids["room_id"],
                        status=default_status("air_monitor"),
                    )
                )
                await uow.commit()

            with pytest.raises(ValidationError):
                await device_service.update_device_status(
                    device_id=sensor.id,
                    attributes={"brightness": 50},
                    user_id=ids["user_id"],
                    family_id=ids["family_id"],
                )

            updated = await device_service.update_device_status(
                device_id=sensor.id,
                attributes={"pm25": 42},
                user_id=ids["user_id"],
                family_id=ids["family_id"],
            )
            assert updated.status["pm25"] == 42

    asyncio.run(scenario())


# ============ 房间服务 ============


def test_list_rooms_with_device_count():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            rooms = await room_service.list_rooms_with_device_count(ids["family_id"])
            assert rooms == [
                {
                    "id": ids["room_id"],
                    "family_id": ids["family_id"],
                    "name": "卧室",
                    "description": None,
                    "icon": "bed",
                    "sort_order": 1,
                    "device_count": 1,
                }
            ]

    asyncio.run(scenario())


def test_get_room_detail_returns_none_for_other_family():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            detail = await room_service.get_room_detail(ids["room_id"], ids["family_id"])
            assert detail["name"] == "卧室"
            assert [d["name"] for d in detail["devices"]] == ["卧室空调"]
            assert await room_service.get_room_detail(ids["room_id"], 999) is None

    asyncio.run(scenario())


def test_delete_room_is_soft():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            # 房间内还有设备时必须先移除，否则设备会失去归属房间
            with pytest.raises(ValidationError):
                await room_service.delete_room(ids["room_id"], ids["family_id"])

            await device_service.delete_device(ids["device_id"], ids["family_id"])
            await room_service.delete_room(ids["room_id"], ids["family_id"])
            assert await room_service.get_room(ids["room_id"], ids["family_id"]) is None
            assert await room_service.list_rooms_by_family(ids["family_id"]) == []

    asyncio.run(scenario())


# ============ 场景服务 ============


def test_get_scene_by_name_matches_synonym():
    """口语「睡觉」应命中预设场景「睡眠」。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                await uow.scenes.add(
                    Scene(family_id=ids["family_id"], name="睡眠", actions={"actions": []})
                )
                await uow.commit()

            scene = await scene_service.get_scene_by_name("睡觉", ids["family_id"])
            assert scene is not None and scene.name == "睡眠"
            assert await scene_service.get_scene_by_name("不存在的场景", ids["family_id"]) is None

    asyncio.run(scenario())


def test_execute_scene_applies_device_actions():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            await seed_scene(ids["family_id"], ids["device_id"])

            result = await scene_service.execute_scene("回家模式", ids["family_id"], ids["user_id"])
            assert result["success"] is True
            assert result["success_count"] == 1
            assert result["failed_count"] == 0

            device = await device_service.get_device(ids["device_id"], ids["family_id"])
            assert device.status["power"] == "on"

    asyncio.run(scenario())


def test_execute_scene_reports_partial_failure():
    """动作里混入不存在的设备时，成功项照常执行，失败项计入 failed_count。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                await uow.scenes.add(
                    Scene(
                        family_id=ids["family_id"],
                        name="混合场景",
                        actions={
                            "actions": [
                                {"device_id": ids["device_id"], "attributes": {"power": "on"}},
                                {"device_id": 999999, "attributes": {"power": "on"}},
                            ]
                        },
                    )
                )
                await uow.commit()

            result = await scene_service.execute_scene("混合场景", ids["family_id"], ids["user_id"])
            assert result["success"] is True
            assert result["success_count"] == 1
            assert result["failed_count"] == 1
            assert "部分动作执行失败" in result["message"]

    asyncio.run(scenario())


def test_execute_scene_unknown_scene_returns_failure():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            result = await scene_service.execute_scene("不存在", ids["family_id"], ids["user_id"])
            assert result["success"] is False
            assert "未找到场景" in result["error"]

    asyncio.run(scenario())


# ============ 家庭服务 ============


def test_create_family_with_owner_creates_both_records():
    async def scenario():
        async with memory_database():
            result = await family_service.create_family_with_owner(
                family_name="李四的家",
                owner_username="owner02",
                owner_nickname="李四",
                description="测试家庭",
            )
            assert result["family_name"] == "李四的家"
            assert result["owner_username"] == "owner02"

            overview = await family_service.get_family_overview(result["family_id"])
            assert overview["name"] == "李四的家"
            assert overview["owner"]["username"] == "owner02"
            assert overview["users_count"] == 1
            # 房主的 family_id 必须已绑定到新家庭
            assert overview["owner"]["family_id"] == result["family_id"]

    asyncio.run(scenario())


def test_create_family_with_owner_rejects_duplicate_username():
    async def scenario():
        async with memory_database():
            await seed_household(username="owner01")
            with pytest.raises(ConflictError):
                await family_service.create_family_with_owner(
                    family_name="重复", owner_username="owner01", owner_nickname="重复"
                )

    asyncio.run(scenario())


def test_get_family_overview_counts_resources():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            await seed_scene(ids["family_id"], ids["device_id"], name="回家模式")
            await seed_scene(ids["family_id"], ids["device_id"], name="离家模式")

            overview = await family_service.get_family_overview(ids["family_id"])
            assert overview["users_count"] == 1
            assert overview["rooms_count"] == 1
            assert overview["devices_count"] == 1
            assert overview["scenes_count"] == 2

            assert await family_service.get_family_overview(999) is None

    asyncio.run(scenario())


def test_delete_family_cascades_but_keeps_family_row():
    """删除家庭：家庭/房间/设备/场景软删，用户/对话/文件/日志物理清空。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            await conversation_service.save_conversation(
                ids["family_id"], ids["user_id"], "s1", "user", "你好"
            )

            await family_service.delete_family(ids["family_id"], ids["family_id"])

            assert await family_service.list_families() == []
            assert await room_service.list_rooms_by_family(ids["family_id"]) == []
            assert await device_service.list_devices_by_family(ids["family_id"]) == []
            assert await scene_service.list_scenes_by_family(ids["family_id"]) == []
            assert await family_service.list_family_users(ids["family_id"]) == []
            assert await conversation_service.get_recent_conversations(ids["user_id"]) == []
            # 家庭行仍在（软删）
            assert await family_service.get_family_overview(ids["family_id"]) is not None

    asyncio.run(scenario())


def test_delete_family_rejects_other_family_operator():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            with pytest.raises(PermissionDeniedError):
                await family_service.delete_family(ids["family_id"], operator_family_id=999)

    asyncio.run(scenario())


# ============ 用户服务 ============


def test_delete_user_rejects_owner():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            with pytest.raises(PermissionDeniedError):
                await user_service.delete_user(ids["user_id"], ids["family_id"])

    asyncio.run(scenario())


def test_update_user_only_allows_profile_fields():
    """昵称/头像可改，role 与 username 不可通过该接口修改。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            user = await user_service.update_user(
                ids["user_id"],
                {"nickname": "新昵称", "role": "guest", "username": "hacked"},
                ids["family_id"],
            )
            assert user.nickname == "新昵称"
            assert user.role == "owner"
            assert user.username == "owner01"

    asyncio.run(scenario())


# ============ 认证服务 ============


def test_login_upgrades_legacy_plaintext_password():
    """历史明文密码登录成功后应就地升级为 bcrypt 哈希。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            result = await auth_service.login("owner01", "plaintext-for-test")
            assert result["token"]
            assert result["family"]["id"] == ids["family_id"]

            async with unit_of_work() as uow:
                user = await uow.users.get(ids["user_id"])
                assert is_hashed(user.password)

            # 升级后仍能用同一密码登录（走哈希校验分支）
            again = await auth_service.login("owner01", "plaintext-for-test")
            assert again["user"]["id"] == ids["user_id"]

    asyncio.run(scenario())


def test_login_wrong_password_raises_authentication_error():
    async def scenario():
        async with memory_database():
            await seed_household(username="login-fail-user")
            with pytest.raises(AuthenticationError):
                await auth_service.login("login-fail-user", "wrong-password")
            # 用户名不存在时同样报认证失败，不泄漏"用户是否存在"
            with pytest.raises(AuthenticationError):
                await auth_service.login("no-such-user-xyz", "whatever")

    asyncio.run(scenario())


def test_create_sub_account_inherits_family_and_validates_role():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            sub = await auth_service.create_sub_account(
                username="resident01",
                password="pw123456",
                nickname="住户",
                role="resident",
                creator_user_id=ids["user_id"],
            )
            assert sub.family_id == ids["family_id"]
            assert is_hashed(sub.password)

            with pytest.raises(ValidationError):
                await auth_service.create_sub_account(
                    username="bad-role",
                    password="pw123456",
                    nickname="错误角色",
                    role="owner",
                    creator_user_id=ids["user_id"],
                )
            with pytest.raises(ConflictError):
                await auth_service.create_sub_account(
                    username="resident01",
                    password="pw123456",
                    nickname="重名",
                    role="resident",
                    creator_user_id=ids["user_id"],
                )

    asyncio.run(scenario())


def test_create_sub_account_requires_owner_creator():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            guest = await auth_service.create_sub_account(
                username="guest01",
                password="pw123456",
                nickname="访客",
                role="guest",
                creator_user_id=ids["user_id"],
            )
            # 住户/访客不能再创建子账户
            with pytest.raises(PermissionDeniedError):
                await auth_service.create_sub_account(
                    username="nested",
                    password="pw123456",
                    nickname="嵌套",
                    role="resident",
                    creator_user_id=guest.id,
                )

    asyncio.run(scenario())


def test_change_password_verifies_old_password():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            with pytest.raises(AuthenticationError):
                await auth_service.change_password(ids["user_id"], "wrong", "newpass123")
            with pytest.raises(ValidationError):
                await auth_service.change_password(ids["user_id"], "plaintext-for-test", "short")

            await auth_service.change_password(ids["user_id"], "plaintext-for-test", "newpass123")
            result = await auth_service.login("owner01", "newpass123")
            assert result["user"]["id"] == ids["user_id"]

    asyncio.run(scenario())


# ============ 对话服务 ============


def test_save_and_reset_session_conversations():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            await conversation_service.save_conversation(
                ids["family_id"], ids["user_id"], "s1", "user", "开灯"
            )
            await conversation_service.save_conversation(
                ids["family_id"], ids["user_id"], "s1", "assistant", "已开灯"
            )
            await conversation_service.save_conversation(
                ids["family_id"], ids["user_id"], "s2", "user", "别的会话"
            )

            messages = await conversation_service.get_session_conversations(
                ids["family_id"], ids["user_id"], "s1"
            )
            assert [m.content for m in messages] == ["开灯", "已开灯"]

            deleted = await conversation_service.delete_session_conversations(
                ids["family_id"], ids["user_id"], "s1"
            )
            assert deleted == 2
            # 其他会话不受影响
            assert (
                await conversation_service.get_session_conversations(
                    ids["family_id"], ids["user_id"], "s2"
                )
            ) != []

    asyncio.run(scenario())


def test_session_context_is_saved_and_reset_with_session():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            await conversation_service.save_conversation(
                ids["family_id"], ids["user_id"], "s-ctx", "user", "旧问题"
            )
            await conversation_service.save_session_context(
                ids["family_id"], ids["user_id"], "s-ctx", ["一级摘要"], 1
            )
            context = await conversation_service.get_session_context(
                ids["family_id"], ids["user_id"], "s-ctx"
            )
            assert context.compressed_parts == ["一级摘要"]
            assert context.compressed_until_id == 1

            await conversation_service.save_session_context(
                ids["family_id"], ids["user_id"], "s-ctx", ["二级强摘要", "新增摘要"], 3
            )
            context = await conversation_service.get_session_context(
                ids["family_id"], ids["user_id"], "s-ctx"
            )
            assert context.compressed_parts == ["二级强摘要", "新增摘要"]
            assert context.compressed_until_id == 3

            await conversation_service.delete_session_conversations(
                ids["family_id"], ids["user_id"], "s-ctx"
            )
            assert (
                await conversation_service.get_session_context(
                    ids["family_id"], ids["user_id"], "s-ctx"
                )
                is None
            )
            assert (
                await conversation_service.get_session_messages_after(
                    ids["family_id"], ids["user_id"], "s-ctx", None
                )
                == []
            )

    asyncio.run(scenario())


def test_device_service_and_repository_share_session_factory():
    """冒烟：确认测试库确实生效（否则上面的断言都是假绿）。"""

    async def scenario():
        async with memory_database():
            ids = await seed_household()
            async with unit_of_work() as uow:
                assert await uow.devices.get(ids["device_id"]) is not None
            assert await device_service.get_device(ids["device_id"]) is not None
            # 未使用的模型也应已建表，避免"表不存在"被误判为业务错误
            async with unit_of_work() as uow:
                assert await uow.files.list_for_rebuild() == []

    asyncio.run(scenario())
