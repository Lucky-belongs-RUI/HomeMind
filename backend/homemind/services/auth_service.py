"""认证服务：登录、注册、子账户与 JWT 管理。

密码使用 bcrypt 存储（见 password_service）；
早期"演示模式"遗留的明文密码会在用户首次成功登录时就地升级为哈希。
数据访问走 UserRepository / FamilyRepository。
"""

from datetime import datetime, timedelta

import jwt

from homemind.core.config import settings
from homemind.core.exceptions import (
    AuthenticationError,
    ConflictError,
    PermissionDeniedError,
    RateLimitError,
    ValidationError,
)
from homemind.models.family import Family
from homemind.models.user import User
from homemind.repositories import unit_of_work
from homemind.services.password_service import (
    hash_password,
    is_hashed,
    verify_and_maybe_upgrade,
    verify_password,
)
from homemind.services.rate_limit import (
    clear_login_failures,
    is_account_locked,
    record_login_failure,
)


class AuthService:
    """认证服务。"""

    @staticmethod
    def hash_password(password: str) -> str:
        """生成 bcrypt 哈希。"""
        return hash_password(password)

    @staticmethod
    def verify_password(password: str, saved: str) -> bool:
        """校验密码（兼容历史明文存储，仅用于非登录场景的快速判断）。"""
        if is_hashed(saved):
            return verify_password(password, saved)
        return bool(saved) and password == saved

    @staticmethod
    def create_jwt_token(user: User) -> str:
        payload = {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "family_id": user.family_id,
            "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    @staticmethod
    def decode_jwt_token(token: str) -> dict:
        try:
            return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token 已过期，请重新登录") from None
        except jwt.InvalidTokenError:
            raise AuthenticationError("无效的 Token") from None

    async def register_family(
        self,
        family_name: str,
        username: str,
        password: str,
        nickname: str,
        description: str = None,
    ) -> dict:
        """房主注册家庭：创建房主用户 → 创建家庭 → 绑定 family_id。"""
        async with unit_of_work() as uow:
            if await uow.users.find_by_username(username):
                raise ConflictError("用户名已存在")

            owner = await uow.users.add(
                User(
                    username=username,
                    password=self.hash_password(password),
                    nickname=nickname,
                    role="owner",
                    family_id=0,
                )
            )
            family = await uow.families.add(
                Family(name=family_name, owner_user_id=owner.id, description=description)
            )
            owner.family_id = family.id
            await uow.commit()

            token = self.create_jwt_token(owner)
            return {
                "token": token,
                "user": {
                    "id": owner.id,
                    "username": owner.username,
                    "nickname": owner.nickname,
                    "role": owner.role,
                    "family_id": family.id,
                },
                "family": {"id": family.id, "name": family.name, "description": family.description},
            }



    async def create_sub_account(
        self, username: str, password: str, nickname: str, role: str, creator_user_id: int
    ) -> User:
        """房主创建住户/访客子账户，继承房主家庭。"""
        if role not in ("resident", "guest"):
            raise ValidationError("子账户角色只能是 resident 或 guest")
        async with unit_of_work() as uow:
            creator = await uow.users.get(creator_user_id)
            if not creator or creator.role != "owner":
                raise PermissionDeniedError("只有房主可以创建子账户")
            if await uow.users.find_by_username(username):
                raise ConflictError("用户名已存在")
            sub_user = await uow.users.add(
                User(
                    username=username,
                    password=self.hash_password(password),
                    nickname=nickname,
                    role=role,
                    family_id=creator.family_id,
                )
            )
            await uow.commit()
            await uow.refresh(sub_user)
            return sub_user

    async def login(self, username: str, password: str) -> dict:
        # 账号锁定检查放在最前面：被锁定的账号无需再查库与做哈希比对
        if is_account_locked(username):
            raise RateLimitError("该账号因多次登录失败已被临时锁定，请稍后再试")

        async with unit_of_work() as uow:
            user = await uow.users.find_by_username(username)
            ok, needs_upgrade = (
                verify_and_maybe_upgrade(password, user.password) if user else (False, False)
            )
            if not ok:
                # 用户名不存在时同样计入失败次数，避免通过"是否被锁定"枚举用户名
                record_login_failure(username)
                raise AuthenticationError("用户名或密码错误")

            clear_login_failures(username)
            if needs_upgrade:
                # 历史明文密码：校验通过后立即升级为 bcrypt 哈希
                user.password = hash_password(password)
                await uow.commit()

            family = await uow.families.get(user.family_id)
            token = self.create_jwt_token(user)
            return {
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "nickname": user.nickname,
                    "role": user.role,
                    "family_id": user.family_id,
                },
                "family": (
                    {"id": family.id, "name": family.name, "description": family.description}
                    if family
                    else None
                ),
            }

    async def change_password(self, user_id: int, old_password: str, new_password: str) -> None:
        async with unit_of_work() as uow:
            user = await uow.users.get(user_id)
            ok, _ = (
                verify_and_maybe_upgrade(old_password, user.password) if user else (False, False)
            )
            if not ok:
                raise AuthenticationError("原密码错误")
            if len(new_password) < 6:
                raise ValidationError("新密码至少 6 位")
            user.password = hash_password(new_password)
            await uow.commit()


auth_service = AuthService()
