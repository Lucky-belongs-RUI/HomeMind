"""家庭接口：家庭概览、管理、成员与家庭内资源列表。"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_owner
from app.schemas.auth import SubAccountCreate
from app.schemas.family import FamilyCreate, FamilyUpdate
from app.services import family_service
from app.services.auth_service import auth_service

router = APIRouter(prefix="/families", tags=["家庭"])


def _ensure_family_access(family_id: int, current_user: dict) -> None:
    """家庭隔离：用户只能访问自己所属家庭的数据。"""
    if family_id != current_user["family_id"]:
        raise HTTPException(status_code=403, detail="无权访问其他家庭的数据")


@router.get("")
async def list_families(current_user: dict = Depends(get_current_user)):
    """列出所有启用家庭（模拟平台用于多家庭体验）。"""
    families = await family_service.list_families()
    return [await family_service.get_family_overview(f.id) for f in families]


@router.post("")
async def create_family(
    payload: FamilyCreate,
    current_user: dict = Depends(require_owner),
):
    """房主创建新家庭并自动生成新房主账户（默认密码 123456）。"""
    try:
        return await family_service.create_family_with_owner(
            family_name=payload.name,
            owner_username=payload.owner_username,
            owner_nickname=payload.owner_nickname,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{family_id}")
async def get_family(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询家庭详情（用户/房间/设备/场景统计）。"""
    _ensure_family_access(family_id, current_user)
    overview = await family_service.get_family_overview(family_id)
    if not overview:
        raise HTTPException(status_code=404, detail="家庭不存在")
    return overview


@router.put("/{family_id}")
async def update_family(
    family_id: int,
    payload: FamilyUpdate,
    current_user: dict = Depends(require_owner),
):
    """更新家庭信息。"""
    _ensure_family_access(family_id, current_user)
    try:
        return await family_service.update_family(
            family_id, payload.model_dump(exclude_unset=True), current_user["family_id"]
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.delete("/{family_id}")
async def delete_family(
    family_id: int,
    current_user: dict = Depends(require_owner),
):
    """删除家庭（级联清理家庭内全部数据）。"""
    _ensure_family_access(family_id, current_user)
    try:
        return await family_service.delete_family(family_id, current_user["family_id"])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{family_id}/users")
async def list_users(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """列出家庭所有用户（不含密码）。"""
    _ensure_family_access(family_id, current_user)
    users = await family_service.list_family_users(family_id)
    return [
        {
            "id": u.id,
            "username": u.username,
            "nickname": u.nickname,
            "role": u.role,
            "family_id": u.family_id,
        }
        for u in users
    ]


@router.post("/{family_id}/users")
async def create_member(
    family_id: int,
    payload: SubAccountCreate,
    current_user: dict = Depends(require_owner),
):
    """房主在家庭下创建住户/访客。"""
    _ensure_family_access(family_id, current_user)
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


@router.get("/{family_id}/rooms")
async def list_rooms(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """列出家庭所有房间（含设备数）。"""
    _ensure_family_access(family_id, current_user)
    return await family_service.list_family_rooms(family_id)


@router.get("/{family_id}/devices")
async def list_devices(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """列出家庭所有设备。"""
    _ensure_family_access(family_id, current_user)
    return await family_service.list_family_devices(family_id)


@router.get("/{family_id}/scenes")
async def list_scenes(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """列出家庭所有场景。"""
    _ensure_family_access(family_id, current_user)
    return await family_service.list_family_scenes(family_id)