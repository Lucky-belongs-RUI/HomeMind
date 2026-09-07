"""认证接口：登录、注册、子账户、当前用户与修改密码。"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_owner
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    SubAccountCreate,
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register")
async def register(payload: RegisterRequest):
    """房主注册家庭（创建家庭 + 房主账户，自动登录）。"""
    try:
        return await auth_service.register_family(
            family_name=payload.family_name,
            username=payload.username,
            password=payload.password,
            nickname=payload.nickname,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/login")
async def login(payload: LoginRequest):
    """用户登录（房主/住户/访客均可）。"""
    try:
        return await auth_service.login(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/sub-account")
async def create_sub_account(
    payload: SubAccountCreate,
    current_user: dict = Depends(require_owner),
):
    """房主创建住户/访客子账户，绑定到房主家庭。"""
    try:
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
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return current_user


@router.put("/password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """修改当前用户密码。"""
    try:
        await auth_service.change_password(
            current_user["user_id"], payload.old_password, payload.new_password
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True}