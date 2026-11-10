"""家庭接口：家庭概览、管理、成员与家庭内资源列表。

异常处理：服务层抛出领域异常，由全局处理器统一转译，本模块不做 try/except 包装。

说明：`/families/{id}/rooms|devices|scenes` 原先直接返回 ORM 对象（把 is_active、
created_at 等内部字段一并暴露），现在统一声明响应模型，输出形状与
`/rooms`、`/devices`、`/scenes` 保持一致。
"""

from fastapi import APIRouter, Depends

from homemind.api.deps import get_current_user, require_owner
from homemind.core.exceptions import NotFoundError, PermissionDeniedError
from homemind.schemas.auth import SubAccountCreate
from homemind.schemas.device import DeviceItem
from homemind.schemas.family import (
    CreatedFamilyResponse,
    FamilyCreate,
    FamilyItem,
    FamilyMemberItem,
    FamilyOverview,
    FamilyUpdate,
)
from homemind.schemas.responses import SubAccountResponse, SuccessResponse
from homemind.schemas.room import RoomItem
from homemind.schemas.scene import SceneItem
from homemind.services import family_service
from homemind.services.auth_service import auth_service

router = APIRouter(prefix="/families", tags=["家庭"])


def _ensure_family_access(family_id: int, current_user: dict) -> None:
    """家庭隔离：用户只能访问自己所属家庭的数据。"""
    if family_id != current_user["family_id"]:
        raise PermissionDeniedError("无权访问其他家庭的数据")


@router.get("", response_model=list[FamilyOverview])
async def list_families(current_user: dict = Depends(get_current_user)):
    """列出当前用户所属家庭的概览（家庭数据隔离：不返回其他家庭信息）。"""
    family_id = current_user.get("family_id")
    if not family_id:
        return []
    overview = await family_service.get_family_overview(family_id)
    return [overview] if overview else []


@router.post("", response_model=CreatedFamilyResponse)
async def create_family(
    payload: FamilyCreate,
    current_user: dict = Depends(require_owner),
):
    """房主创建新家庭并自动生成新房主账户（默认密码 123456）。"""
    return await family_service.create_family_with_owner(
        family_name=payload.name,
        owner_username=payload.owner_username,
        owner_nickname=payload.owner_nickname,
        description=payload.description,
    )


@router.get("/{family_id}", response_model=FamilyOverview)
async def get_family(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询家庭详情（用户/房间/设备/场景统计）。"""
    _ensure_family_access(family_id, current_user)
    overview = await family_service.get_family_overview(family_id)
    if not overview:
        raise NotFoundError("家庭不存在")
    return overview


@router.put("/{family_id}", response_model=FamilyItem)
async def update_family(
    family_id: int,
    payload: FamilyUpdate,
    current_user: dict = Depends(require_owner),
):
    """更新家庭信息。"""
    _ensure_family_access(family_id, current_user)
    return await family_service.update_family(
        family_id, payload.model_dump(exclude_unset=True), current_user["family_id"]
    )


@router.delete("/{family_id}", response_model=SuccessResponse)
async def delete_family(
    family_id: int,
    current_user: dict = Depends(require_owner),
):
    """删除家庭（级联清理家庭内全部数据）。"""
    _ensure_family_access(family_id, current_user)
    return await family_service.delete_family(family_id, current_user["family_id"])


@router.get("/{family_id}/users", response_model=list[FamilyMemberItem])
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


@router.post("/{family_id}/users", response_model=SubAccountResponse)
async def create_member(
    family_id: int,
    payload: SubAccountCreate,
    current_user: dict = Depends(require_owner),
):
    """房主在家庭下创建住户/访客。"""
    _ensure_family_access(family_id, current_user)
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


@router.get("/{family_id}/rooms", response_model=list[RoomItem])
async def list_rooms(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """列出家庭所有房间。"""
    _ensure_family_access(family_id, current_user)
    return await family_service.list_family_rooms(family_id)


@router.get("/{family_id}/devices", response_model=list[DeviceItem])
async def list_devices(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """列出家庭所有设备。"""
    _ensure_family_access(family_id, current_user)
    return await family_service.list_family_devices(family_id)


@router.get("/{family_id}/scenes", response_model=list[SceneItem])
async def list_scenes(
    family_id: int,
    current_user: dict = Depends(get_current_user),
):
    """列出家庭所有场景。"""
    _ensure_family_access(family_id, current_user)
    return await family_service.list_family_scenes(family_id)
