"""家庭服务：概览聚合、创建、更新与级联删除。

SQL 已下沉到各仓库；本层负责聚合与权限判断。
"""

from homemind.core.exceptions import ConflictError, PermissionDeniedError
from homemind.models.family import Family
from homemind.models.user import User
from homemind.repositories import unit_of_work
from homemind.services.auth_service import auth_service
from homemind.services.device_service import list_devices_by_family
from homemind.services.room_service import list_rooms_by_family
from homemind.services.scene_service import list_scenes_by_family


async def get_family_overview(family_id: int) -> dict | None:
    """家庭概览：家庭信息 + 房主 + 用户/房间/设备/场景统计（前端平铺使用）。

    5 次统计查询共用同一个会话，改造前会开 5 个连接。
    """
    async with unit_of_work() as uow:
        family = await uow.families.get(family_id)
        if not family:
            return None
        users_count = await uow.users.count_by_family(family_id)
        rooms_count = await uow.rooms.count_by_family(family_id)
        devices_count = await uow.devices.count_by_family(family_id)
        scenes_count = await uow.scenes.count_by_family(family_id)
        owner = await uow.users.get(family.owner_user_id)
        return {
            "id": family.id,
            "name": family.name,
            "owner_user_id": family.owner_user_id,
            "owner": (
                {
                    "id": owner.id,
                    "username": owner.username,
                    "nickname": owner.nickname,
                    "role": owner.role,
                    "family_id": owner.family_id,
                }
                if owner
                else None
            ),
            "description": family.description,
            "users_count": users_count,
            "rooms_count": rooms_count,
            "devices_count": devices_count,
            "scenes_count": scenes_count,
        }


async def list_families() -> list[Family]:
    """列出所有启用家庭。"""
    async with unit_of_work() as uow:
        return await uow.families.list_active()


async def create_family_with_owner(
    family_name: str, owner_username: str, owner_nickname: str, description: str = None
) -> dict:
    """创建家庭 + 房主用户并一步绑定（模拟平台默认密码 123456）。"""
    async with unit_of_work() as uow:
        existing = await uow.users.find_by_username(owner_username)
        if existing:
            raise ConflictError("用户名已存在")

        owner = await uow.users.add(
            User(
                username=owner_username,
                password=auth_service.hash_password("123456"),
                nickname=owner_nickname,
                role="owner",
                family_id=0,
            )
        )
        family = await uow.families.add(
            Family(name=family_name, owner_user_id=owner.id, description=description)
        )
        owner.family_id = family.id
        await uow.commit()
        return {
            "family_id": family.id,
            "family_name": family.name,
            "owner_user_id": owner.id,
            "owner_username": owner.username,
        }


async def update_family(family_id: int, data: dict, operator_family_id: int) -> Family:
    """更新家庭信息；仅允许操作自己所属的家庭。"""
    async with unit_of_work() as uow:
        family = await uow.families.get(family_id)
        if not family or family.id != operator_family_id:
            raise PermissionDeniedError("无权操作其他家庭")
        for key in ("name", "description"):
            if key in data and data[key] is not None:
                setattr(family, key, data[key])
        await uow.commit()
        await uow.refresh(family)
        return family


async def delete_family(family_id: int, operator_family_id: int) -> dict:
    """删除家庭：软删家庭/房间/设备/场景，并清空用户、对话、文件、日志。

    全部操作在同一个事务内完成（改造前也是单会话，此处保持一致）。
    """
    async with unit_of_work() as uow:
        family = await uow.families.get(family_id)
        if not family or family.id != operator_family_id:
            raise PermissionDeniedError("无权操作其他家庭")
        family.is_active = False
        await uow.rooms.deactivate_by_family(family_id)
        await uow.devices.deactivate_by_family(family_id)
        await uow.scenes.deactivate_by_family(family_id)
        for user in await uow.users.list_by_family(family_id):
            await uow.users.delete(user)
        await uow.conversations.delete_by_family(family_id)
        await uow.files.delete_by_family(family_id)
        await uow.devices.purge_logs_by_family(family_id)
        await uow.commit()
        return {"success": True}


async def list_family_users(family_id: int) -> list[User]:
    """家庭内用户列表。"""
    async with unit_of_work() as uow:
        return await uow.users.list_by_family(family_id)


async def list_family_rooms(family_id: int):
    return await list_rooms_by_family(family_id)


async def list_family_devices(family_id: int):
    return await list_devices_by_family(family_id)


async def list_family_scenes(family_id: int):
    return await list_scenes_by_family(family_id)
