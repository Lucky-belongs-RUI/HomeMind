from sqlalchemy import select

from app.database import get_db_session
from app.models.user import User


async def list_users(family_id: int) -> list[User]:
    """列出家庭内所有用户（家庭隔离）。"""
    async with get_db_session() as db:
        result = await db.execute(
            select(User).where(User.family_id == family_id).order_by(User.id)
        )
        return list(result.scalars().all())


async def get_user(user_id: int, family_id: int = None) -> User | None:
    """查询用户；传入 family_id 时校验归属，防止跨家庭访问。"""
    async with get_db_session() as db:
        conditions = [User.id == user_id]
        if family_id is not None:
            conditions.append(User.family_id == family_id)
        result = await db.execute(select(User).where(*conditions))
        return result.scalar_one_or_none()


async def update_user(user_id: int, data: dict, family_id: int) -> User:
    """更新用户资料（昵称、头像），不允许修改角色与用户名。"""
    async with get_db_session() as db:
        user = await db.get(User, user_id)
        if not user or user.family_id != family_id:
            raise ValueError("用户不存在")
        for key in ("nickname", "avatar_url"):
            if key in data and data[key] is not None:
                setattr(user, key, data[key])
        await db.commit()
        await db.refresh(user)
        return user


async def delete_user(user_id: int, family_id: int) -> dict:
    """删除家庭内用户；房主不可删除（权限在路由层校验）。"""
    async with get_db_session() as db:
        user = await db.get(User, user_id)
        if not user or user.family_id != family_id:
            raise ValueError("用户不存在")
        if user.role == "owner":
            raise PermissionError("房主不可删除")
        await db.delete(user)
        await db.commit()
        return {"success": True}