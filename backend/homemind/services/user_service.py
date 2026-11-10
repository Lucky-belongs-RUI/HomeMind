"""用户服务：家庭内用户的查询、更新与删除。"""

from homemind.core.exceptions import NotFoundError, PermissionDeniedError
from homemind.models.user import User
from homemind.repositories import unit_of_work


async def list_users(family_id: int) -> list[User]:
    """列出家庭内所有用户（家庭隔离）。"""
    async with unit_of_work() as uow:
        return await uow.users.list_by_family(family_id, ordered=True)


async def get_user(user_id: int, family_id: int = None) -> User | None:
    """查询用户；传入 family_id 时校验归属，防止跨家庭访问。"""
    async with unit_of_work() as uow:
        return await uow.users.find(user_id, family_id)


async def update_user(user_id: int, data: dict, family_id: int) -> User:
    """更新用户资料（昵称、头像），不允许修改角色与用户名。"""
    async with unit_of_work() as uow:
        user = await uow.users.get(user_id)
        if not user or user.family_id != family_id:
            raise NotFoundError("用户不存在")
        for key in ("nickname", "avatar_url"):
            if key in data and data[key] is not None:
                setattr(user, key, data[key])
        await uow.commit()
        await uow.refresh(user)
        return user


async def delete_user(user_id: int, family_id: int) -> dict:
    """删除家庭内用户；房主不可删除（权限在路由层校验）。"""
    async with unit_of_work() as uow:
        user = await uow.users.get(user_id)
        if not user or user.family_id != family_id:
            raise NotFoundError("用户不存在")
        if user.role == "owner":
            raise PermissionDeniedError("房主不可删除")
        await uow.users.delete(user)
        await uow.commit()
        return {"success": True}
