from datetime import datetime, timedelta

import jwt
from sqlalchemy import select

from app.config import settings
from app.database import get_db_session
from app.models.family import Family
from app.models.user import User


class AuthService:
    """认证服务：登录、注册、子账户与 JWT 管理。

    演示平台按需求明文保存密码，不做哈希与安全校验。
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """演示模式：直接返回明文密码。"""
        return password

    @staticmethod
    def verify_password(password: str, saved: str) -> bool:
        """演示模式：明文比对。"""
        return password == saved

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
            raise ValueError("Token 已过期，请重新登录")
        except jwt.InvalidTokenError:
            raise ValueError("无效的 Token")

    async def register_family(
        self, family_name: str, username: str, password: str,
        nickname: str, description: str = None,
    ) -> dict:
        """房主注册家庭：创建房主用户 → 创建家庭 → 绑定 family_id。"""
        async with get_db_session() as db:
            existing = await db.execute(select(User).where(User.username == username))
            if existing.scalar_one_or_none():
                raise ValueError("用户名已存在")

            owner = User(
                username=username,
                password=self.hash_password(password),
                nickname=nickname,
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
            raise ValueError("子账户角色只能是 resident 或 guest")
        async with get_db_session() as db:
            creator = await db.get(User, creator_user_id)
            if not creator or creator.role != "owner":
                raise PermissionError("只有房主可以创建子账户")
            existing = await db.execute(select(User).where(User.username == username))
            if existing.scalar_one_or_none():
                raise ValueError("用户名已存在")
            sub_user = User(
                username=username,
                password=self.hash_password(password),
                nickname=nickname,
                role=role,
                family_id=creator.family_id,
            )
            db.add(sub_user)
            await db.commit()
            await db.refresh(sub_user)
            return sub_user

    async def login(self, username: str, password: str) -> dict:
        async with get_db_session() as db:
            user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if not user or not self.verify_password(password, user.password):
                raise ValueError("用户名或密码错误")
            family = await db.get(Family, user.family_id)
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
        async with get_db_session() as db:
            user = await db.get(User, user_id)
            if not user or not self.verify_password(old_password, user.password):
                raise ValueError("原密码错误")
            if len(new_password) < 6:
                raise ValueError("新密码至少 6 位")
            user.password = self.hash_password(new_password)
            await db.commit()


auth_service = AuthService()