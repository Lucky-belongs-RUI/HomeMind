"""个人模型配置接口：只允许操作当前登录用户自己的配置。"""

from fastapi import APIRouter, Depends

from homemind.api.deps import get_current_user
from homemind.schemas.model_config import (
    ModelConfigCreate,
    ModelConfigItem,
    ModelConfigUpdate,
)
from homemind.schemas.responses import SuccessResponse
from homemind.services import model_config_service

router = APIRouter(prefix="/model-configs", tags=["模型配置"])


@router.get("", response_model=list[ModelConfigItem])
async def list_model_configs(current_user: dict = Depends(get_current_user)):
    """列出当前用户的模型配置。"""
    return await model_config_service.list_configs(current_user["user_id"])


@router.post("", response_model=ModelConfigItem)
async def create_model_config(
    payload: ModelConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    """新增模型配置；API Key 加密存储，不返回明文。"""
    return await model_config_service.create_config(
        current_user["user_id"],
        current_user["family_id"],
        payload,
    )


@router.put("/{config_id}", response_model=ModelConfigItem)
async def update_model_config(
    config_id: int,
    payload: ModelConfigUpdate,
    current_user: dict = Depends(get_current_user),
):
    """编辑模型配置；API Key 留空时保持原值。"""
    return await model_config_service.update_config(
        current_user["user_id"],
        config_id,
        payload,
    )


@router.delete("/{config_id}", response_model=SuccessResponse)
async def delete_model_config(
    config_id: int,
    current_user: dict = Depends(get_current_user),
):
    """删除当前用户自己的模型配置。"""
    return await model_config_service.delete_config(current_user["user_id"], config_id)
