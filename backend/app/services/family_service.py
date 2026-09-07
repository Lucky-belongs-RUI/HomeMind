from sqlalchemy import delete, func, select, update

from app.database import get_db_session
from app.models.conversation import Conversation
from app.models.device import Device, DeviceOperationLog
from app.models.family import Family
from app.models.file import UploadedFile
from app.models.room import Room
from app.models.scene import Scene
from app.models.user import User
from app.services.auth_service import auth_service


async def get_family_overview(family_id: int) -> dict | None:
    """家庭概览：家庭信息 + 房主 + 用户/房间/设备/场景统计（前端平铺使用）。"""
    async with get_db_session() as db:
        family = await db.get(Family, family_id)
        if not family:
            return None
        users_count = await db.scalar(select(func.count()).where(User.family_id == family_id))
        rooms_count = await db.scalar(
            select(func.count()).where(Room.family_id == family_id, Room.is_active == 1)
        )
        devices_count = await db.scalar(
            select(func.count()).where(Device.family_id == family_id, Device.is_active == 1)
        )
        scenes_count = await db.scalar(
            select(func.count()).where(Scene.family_id == family_id, Scene.is_active == 1)
        )
        owner = await db.get(User, family.owner_user_id)
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
            "users_count": users_count or 0,
            "rooms_count": rooms_count or 0,
            "devices_count": devices_count or 0,
            "scenes_count": scenes_count or 0,
        }


async def list_families() -> list[Family]:
    async with get_db_session() as db:
        result = await db.execute(select(Family).where(Family.is_active == 1))
        return list(result.scalars().all())


async def create_family_with_owner(
    family_name: str, owner_username: str, owner_nickname: str, description: str = None
) -> dict:
    """创建家庭 + 房主用户并一步绑定（模拟平台默认密码 123456）。"""
    async with get_db_session() as db:
        existing = await db.execute(select(User).where(User.username == owner_username))
        if existing.scalar_one_or_none():
            raise ValueError("用户名已存在")

        owner = User(
            username=owner_username,
            password=auth_service.hash_password("123456"),
            nickname=owner_nickname,
            role="owner",
            family_id=0,
        )
        db.add(owner)
        await db.flush()

        family = Family(name=family_name, owner_user_id=owner.id, description=description)
        db.add(family)
        await db.flush()

        owner.family_id = family.id
        await db.commit()
        return {
            "family_id": family.id,
            "family_name": family.name,
            "owner_user_id": owner.id,
            "owner_username": owner.username,
        }


async def update_family(family_id: int, data: dict, operator_family_id: int) -> Family:
    """更新家庭信息；仅允许操作自己所属的家庭。"""
    async with get_db_session() as db:
        family = await db.get(Family, family_id)
        if not family or family.id != operator_family_id:
            raise PermissionError("无权操作其他家庭")
        for key in ("name", "description"):
            if key in data and data[key] is not None:
                setattr(family, key, data[key])
        await db.commit()
        await db.refresh(family)
        return family


async def delete_family(family_id: int, operator_family_id: int) -> dict:
    """删除家庭：软删家庭/房间/设备/场景，并清空用户、对话、文件、日志。"""
    async with get_db_session() as db:
        family = await db.get(Family, family_id)
        if not family or family.id != operator_family_id:
            raise PermissionError("无权操作其他家庭")
        family.is_active = False
        await db.execute(update(Room).where(Room.family_id == family_id).values(is_active=False))
        await db.execute(update(Device).where(Device.family_id == family_id).values(is_active=False))
        await db.execute(update(Scene).where(Scene.family_id == family_id).values(is_active=False))
        users = (await db.execute(select(User).where(User.family_id == family_id))).scalars().all()
        for user in users:
            await db.delete(user)
        await db.execute(delete(Conversation).where(Conversation.family_id == family_id))
        await db.execute(delete(UploadedFile).where(UploadedFile.family_id == family_id))
        await db.execute(delete(DeviceOperationLog).where(DeviceOperationLog.family_id == family_id))
        await db.commit()
        return {"success": True}


async def list_family_users(family_id: int) -> list[User]:
    async with get_db_session() as db:
        result = await db.execute(select(User).where(User.family_id == family_id))
        return list(result.scalars().all())


async def list_family_rooms(family_id: int):
    from app.services.room_service import list_rooms_by_family
    return await list_rooms_by_family(family_id)


async def list_family_devices(family_id: int):
    from app.services.device_service import list_devices_by_family
    return await list_devices_by_family(family_id)


async def list_family_scenes(family_id: int):
    from app.services.scene_service import list_scenes_by_family
    return await list_scenes_by_family(family_id)