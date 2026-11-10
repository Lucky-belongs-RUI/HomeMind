"""认证接口：登录、注册、子账户、当前用户与修改密码。

本模块**不做异常转译**——服务层抛出的是领域异常（`AppError` 子类），
由 `homemind/core/handlers.py` 的全局处理器统一转成带 `code` 的错误响应。
这里只保留接口层自己的关注点：来源 IP 限流。
"""

from fastapi import APIRouter, Depends, Request

from homemind.api.deps import client_ip, get_current_user, require_owner
from homemind.core.exceptions import RateLimitError
from homemind.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    SubAccountCreate,
)
from homemind.schemas.responses import (
    AuthResponse,
    CurrentUserResponse,
    SubAccountResponse,
    SuccessResponse,
)
from homemind.services.auth_service import auth_service
from homemind.services.rate_limit import allow_login_attempt, allow_register_attempt

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, request: Request):

    if not allow_register_attempt(client_ip(request)):
        raise RateLimitError("注册过于频繁，请稍后再试")
    return await auth_service.register_family(
        family_name=payload.family_name,
        username=payload.username,
        password=payload.password,
        nickname=payload.nickname,
        description=payload.description,
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request):
    if not allow_login_attempt(client_ip(request)):
        raise RateLimitError("登录尝试过于频繁，请稍后再试")
    return await auth_service.login(payload.username, payload.password)


@router.post("/sub-account", response_model=SubAccountResponse)
async def create_sub_account(
    payload: SubAccountCreate,
    current_user: dict = Depends(require_owner),
):
    """房主创建住户/访客子账户，绑定到房主家庭。"""
    user = await auth_service.create_sub_account(
        username=payload.username,
        password=payload.password,
        nickname=payload.nickname,
        role=payload.role,
        creator_user_id=current_user["user_id"],
    )
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "role": user.role,
    }


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return current_user


@router.put("/password", response_model=SuccessResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """修改当前用户密码。"""
    await auth_service.change_password(
        current_user["user_id"], payload.old_password, payload.new_password
    )
    return {"success": True}
