"""用户个人模型配置服务。

职责：
- 校验 provider/model/base_url；
- 使用 Fernet 加密 API Key 后落库；
- 对话时按 model_config_id 解析出本次请求要用的凭证。
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from homemind.core.config import settings
from homemind.core.exceptions import ConflictError, NotFoundError, ValidationError
from homemind.models.model_config import UserModelConfig
from homemind.repositories import unit_of_work

logger = logging.getLogger(__name__)

PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "qwen": ("qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "deepseek": ("deepseek-chat", "https://api.deepseek.com/v1"),
    "zhipu": ("glm-4", "https://open.bigmodel.cn/api/paas/v4"),
    "ollama": ("qwen2.5:7b", "http://127.0.0.1:11434/v1"),
}


def _fernet() -> Fernet:
    secret = (settings.model_config_secret or settings.jwt_secret or "").strip()
    if not secret:
        raise RuntimeError("缺少 MODEL_CONFIG_SECRET / JWT_SECRET，无法加密模型 API Key")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValidationError("模型配置密钥无法解密，请删除后重新添加") from exc


def _to_item(record: UserModelConfig) -> dict:
    return {
        "id": record.id,
        "name": record.name,
        "provider": record.provider,
        "model": record.model,
        "base_url": record.base_url,
        "has_api_key": bool(record.api_key_encrypted),
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


async def list_configs(user_id: int) -> list[dict]:
    async with unit_of_work() as uow:
        records = await uow.model_configs.list_by_user(user_id)
        return [_to_item(record) for record in records]


async def create_config(user_id: int, family_id: int, payload) -> dict:
    provider = payload.provider
    if provider not in PROVIDER_DEFAULTS:
        raise ValidationError(f"不支持的模型供应商: {provider}")

    default_model, default_base_url = PROVIDER_DEFAULTS[provider]
    name = (payload.name or "").strip()
    model = (payload.model or "").strip() or default_model
    base_url = (payload.base_url or "").strip() or default_base_url
    api_key = (payload.api_key or "").strip()
    if provider == "ollama" and not api_key:
        api_key = "ollama"
    if not api_key:
        raise ValidationError("API Key 不能为空")

    async with unit_of_work() as uow:
        if await uow.model_configs.find_by_name(user_id, name):
            raise ConflictError(f"模型配置「{name}」已存在")
        record = UserModelConfig(
            user_id=user_id,
            family_id=family_id,
            name=name,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key_encrypted=_encrypt(api_key),
        )
        await uow.model_configs.add(record)
        await uow.commit()
        await uow.refresh(record)
        return _to_item(record)


async def update_config(user_id: int, config_id: int, payload) -> dict:
    """编辑配置；api_key 为空时保留原密文。"""
    fields = payload.model_dump(exclude_unset=True)
    async with unit_of_work() as uow:
        record = await uow.model_configs.find_for_user(user_id, config_id)
        if not record:
            raise NotFoundError("模型配置不存在")

        new_name = fields.get("name")
        if new_name is not None:
            new_name = str(new_name).strip()
            if not new_name:
                raise ValidationError("配置名称不能为空")
            existing = await uow.model_configs.find_by_name(user_id, new_name)
            if existing and existing.id != record.id:
                raise ConflictError(f"模型配置「{new_name}」已存在")
            record.name = new_name

        provider = str(fields.get("provider") or record.provider)
        if provider not in PROVIDER_DEFAULTS:
            raise ValidationError(f"不支持的模型供应商: {provider}")
        provider_changed = provider != record.provider
        if "provider" in fields:
            record.provider = provider

        default_model, default_base_url = PROVIDER_DEFAULTS[provider]
        if "model" in fields or "provider" in fields:
            record.model = str(fields.get("model") or "").strip() or default_model
        if "base_url" in fields or "provider" in fields:
            record.base_url = str(fields.get("base_url") or "").strip() or default_base_url

        api_key = str(fields.get("api_key") or "").strip()
        if api_key:
            record.api_key_encrypted = _encrypt(api_key)
        elif provider == "ollama" and not record.api_key_encrypted:
            record.api_key_encrypted = _encrypt("ollama")
        elif provider_changed and provider != "ollama" and not api_key:
            raise ValidationError("切换模型供应商后请重新填写 API Key")
        elif provider != "ollama" and not record.api_key_encrypted:
            raise ValidationError("API Key 不能为空")

        await uow.commit()
        await uow.refresh(record)
        return _to_item(record)


async def delete_config(user_id: int, config_id: int) -> dict:
    async with unit_of_work() as uow:
        record = await uow.model_configs.find_for_user(user_id, config_id)
        if not record:
            raise NotFoundError("模型配置不存在")
        await uow.model_configs.delete(record)
        await uow.commit()
    return {"success": True}


async def resolve_config(user_id: int, config_id: int) -> dict:
    """解析出本次请求的供应商、模型、API Key 与 Base URL。"""
    async with unit_of_work() as uow:
        record = await uow.model_configs.find_for_user(user_id, config_id)
        if not record:
            raise NotFoundError("模型配置不存在")
        api_key = _decrypt(record.api_key_encrypted)
        if record.provider != "ollama" and not api_key:
            raise ValidationError("该模型配置缺少 API Key，请重新添加")
        return {
            "provider": record.provider,
            "model": record.model,
            "api_key": api_key,
            "base_url": record.base_url or "",
        }
