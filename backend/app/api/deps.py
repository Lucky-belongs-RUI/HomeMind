"""认证依赖：从 Authorization 头解析 JWT，提供权限分级校验。"""
from fastapi import Depends, Header, HTTPException

from app.services.auth_service import auth_service


def _parse_payload(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="认证失败：缺少 Bearer token")
    token = authorization[7:].strip()
    try:
        payload = auth_service.decode_jwt_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return payload


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """已登录用户：解析 token 获取 user_id、role、family_id。"""
    payload = _parse_payload(authorization)
    return {
        "user_id": payload["user_id"],
        "username": payload["username"],
        "role": payload["role"],
        "family_id": payload["family_id"],
    }


async def require_owner(current_user: dict = Depends(get_current_user)) -> dict:
    """房主权限。"""
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="需要房主权限")
    return current_user


async def require_owner_or_resident(current_user: dict = Depends(get_current_user)) -> dict:
    """房主或住户权限（可控制设备）。"""
    if current_user["role"] not in ("owner", "resident"):
        raise HTTPException(status_code=403, detail="需要房主或住户权限")
    return current_user


def current_user_payload_from_query(token: str | None = None) -> dict | None:
    """WebSocket 场景：从 query 参数解析 token，未提供时返回 None。"""
    if not token:
        return None
    try:
        payload = auth_service.decode_jwt_token(token)
        return {
            "user_id": payload["user_id"],
            "username": payload["username"],
            "role": payload["role"],
            "family_id": payload["family_id"],
        }
    except ValueError:
        return None