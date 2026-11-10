"""用户接口：家庭成员管理、用户资料与偏好画像。

异常处理：服务层抛出领域异常，由全局处理器统一转译，本模块不做 try/except 包装。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from homemind.agent.runtime.persistence import get_store
from homemind.api.deps import get_current_user, require_owner
from homemind.core.exceptions import NotFoundError, PermissionDeniedError
from homemind.schemas.responses import SuccessResponse
from homemind.schemas.user import UserItem, UserPreferencesResponse, UserUpdate
from homemind.services import preference_service, user_service

logger = logging.getLogger(__name__)

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


@router.get("", response_model=list[UserItem])
async def list_users(current_user: dict = Depends(get_current_user)):
    """列出当前家庭所有用户。"""
    users = await user_service.list_users(current_user["family_id"])
    return [_user_dict(u) for u in users]


@router.get("/{user_id}", response_model=UserItem)
async def get_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
):
    """查询用户详情。"""
    user = await user_service.get_user(user_id, current_user["family_id"])
    if not user:
        raise NotFoundError("用户不存在")
    return _user_dict(user)


@router.put("/{user_id}", response_model=UserItem)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    """更新用户资料（房主可管理成员，普通用户只能改自己）。"""
    if current_user["role"] != "owner" and current_user["user_id"] != user_id:
        raise PermissionDeniedError("无权修改其他用户资料")
    user = await user_service.update_user(
        user_id, payload.model_dump(exclude_unset=True), current_user["family_id"]
    )
    return _user_dict(user)


@router.delete("/{user_id}", response_model=SuccessResponse)
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_owner),
):
    """删除用户（房主不可删除）。"""
    return await user_service.delete_user(user_id, current_user["family_id"])


@router.get("/{user_id}/preferences", response_model=UserPreferencesResponse)
async def get_preferences(
    user_id: int,
    current_user: dict = Depends(get_current_user),
):
    """获取用户偏好画像。"""
    # 先做家庭隔离：房主也只能查看本家庭成员，避免跨家庭越权
    user = await user_service.get_user(user_id, current_user["family_id"])
    if not user:
        raise NotFoundError("用户不存在")
    if user_id != current_user["user_id"] and current_user["role"] != "owner":
        raise PermissionDeniedError("无权查看其他用户偏好")
    preferences = await preference_service.get_user_preferences(user_id)
    return {"user_id": user_id, "preferences": preferences}


@router.post("/{user_id}/preferences/analyze", response_model=dict[str, Any])
async def analyze_preferences(
    user_id: int,
    current_user: dict = Depends(get_current_user),
):
    """基于对话历史触发偏好画像分析。

    返回的是模型根据对话内容自主生成的自由字典（键不固定），
    因此这里只能声明为 `Dict[str, Any]`，无法进一步约束结构。
    """
    user = await user_service.get_user(user_id, current_user["family_id"])
    if not user:
        raise NotFoundError("用户不存在")
    if user_id != current_user["user_id"] and current_user["role"] != "owner":
        raise PermissionDeniedError("无权分析其他用户偏好")
    preferences = await preference_service.analyze_user_preferences(user_id)

    # 画像变更后同步刷新 Store 缓存，避免对话链路一直读到旧画像
    store = get_store()
    if store is not None:
        namespace = (
            "family",
            str(current_user["family_id"]),
            "user",
            str(user_id),
            "profile",
        )
        try:
            await store.aput(namespace, "profile", preferences)
        except Exception as exc:
            logger.warning("偏好画像写入 Store 失败: %s", exc)
    return preferences
