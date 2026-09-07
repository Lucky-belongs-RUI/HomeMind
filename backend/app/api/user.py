"""用户接口：家庭成员管理、用户资料与偏好画像。"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_owner
from app.schemas.user import UserUpdate
from app.services import preference_service, user_service

router = APIRouter(prefix="/users", tags=["用户"])


def _user_dict(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "role": user.role,
        "family_id": user.family_id,
        "avatar_url": user.avatar_url,
    }


@router.get("")
async def list_users(current_user: dict = Depends(get_current_user)):
    """列出当前家庭所有用户。"""
    users = await user_service.list_users(current_user["family_id"])
    return [_user_dict(u) for u in users]


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询用户详情。"""
    user = await user_service.get_user(user_id, current_user["family_id"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _user_dict(user)


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    """更新用户资料（房主可管理成员，普通用户只能改自己）。"""
    if current_user["role"] != "owner" and current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权修改其他用户资料")
    try:
        user = await user_service.update_user(
            user_id, payload.model_dump(exclude_unset=True), current_user["family_id"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _user_dict(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_owner),
):
    """删除用户（房主不可删除）。"""
    try:
        return await user_service.delete_user(user_id, current_user["family_id"])
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{user_id}/preferences")
async def get_preferences(
    user_id: int,
    current_user: dict = Depends(get_current_user),
):
    """获取用户偏好画像。"""
    if user_id != current_user["user_id"] and current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="无权查看其他用户偏好")
    preferences = await preference_service.get_user_preferences(user_id)
    return {"user_id": user_id, "preferences": preferences}


@router.post("/{user_id}/preferences/analyze")
async def analyze_preferences(
    user_id: int,
    current_user: dict = Depends(get_current_user),
):
    """基于对话历史触发偏好画像分析。"""
    if user_id != current_user["user_id"] and current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="无权分析其他用户偏好")
    preferences = await preference_service.analyze_user_preferences(user_id)
    return preferences