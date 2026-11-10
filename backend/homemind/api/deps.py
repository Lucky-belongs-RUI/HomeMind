"""认证依赖：从 Authorization 头解析 JWT，回查数据库获取最新身份。

为什么每次请求回查数据库：JWT 一旦签发就无法撤销，而 token 里携带的
role / family_id 是签发时刻的快照。若只信任 token 内容，房主把某住户降级
或移出家庭后，该用户手上的旧 token 在有效期内（默认 24 小时）仍可控制设备。
改为以 token 中的 user_id 作为唯一凭据、每次请求回查最新角色，
权限变更即可立即生效。

性能：加了一层 10 秒 TTL 的进程内缓存，避免前端并发请求重复查库；
代价是权限变更最多延迟 10 秒生效——远优于原先的 24 小时。
"""

import time

from fastapi import Depends, Header, Request

from homemind.core.config import settings
from homemind.core.exceptions import (
    AppError,
    AuthenticationError,
    PermissionDeniedError,
)
from homemind.services.auth_service import auth_service
from homemind.services.user_service import get_user

_CACHE_TTL_SECONDS = 10
_CACHE_MAX_KEYS = 5000
# user_id -> (过期时间, 身份字典)
_identity_cache: dict[int, tuple[float, dict]] = {}


def client_ip(request: Request) -> str:
    """取客户端 IP，用于限流与风控。

    只有显式开启 trust_proxy_headers（部署在可信反向代理之后）时才读取
    X-Forwarded-For；否则客户端可自行伪造该头，把每次请求伪装成不同 IP，
    从而完全绕过限流。
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _parse_payload(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("认证失败：缺少 Bearer token")
    token = authorization[7:].strip()
    # 解码失败时抛 AuthenticationError，由全局异常处理器统一转成 401
    return auth_service.decode_jwt_token(token)


async def _load_identity(user_id: int) -> dict | None:
    """按 user_id 回查最新身份（带 TTL 缓存）；用户不存在返回 None。"""
    now = time.monotonic()
    cached = _identity_cache.get(user_id)
    if cached and cached[0] > now:
        return cached[1]

    user = await get_user(user_id)
    if not user:
        _identity_cache.pop(user_id, None)
        return None

    identity = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "family_id": user.family_id,
    }
    if len(_identity_cache) >= _CACHE_MAX_KEYS:
        _identity_cache.clear()
    _identity_cache[user_id] = (now + _CACHE_TTL_SECONDS, identity)
    return identity


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """已登录用户：token 仅用于确认身份，角色与家庭以数据库当前值为准。"""
    payload = _parse_payload(authorization)
    user_id = payload.get("user_id")
    if not isinstance(user_id, int):
        raise AuthenticationError("无效的 Token")
    identity = await _load_identity(user_id)
    if identity is None:
        raise AuthenticationError("账号不存在或已被移除，请重新登录")
    return identity


async def require_owner(current_user: dict = Depends(get_current_user)) -> dict:
    """房主权限。"""
    if current_user["role"] != "owner":
        raise PermissionDeniedError("需要房主权限")
    return current_user


async def require_owner_or_resident(current_user: dict = Depends(get_current_user)) -> dict:
    """房主或住户权限（可控制设备）。"""
    if current_user["role"] not in ("owner", "resident"):
        raise PermissionDeniedError("需要房主或住户权限")
    return current_user


async def current_user_payload_from_query(token: str | None = None) -> dict | None:
    """WebSocket 场景：从 query 参数解析 token 并回查最新身份；无效时返回 None。"""
    if not token:
        return None
    try:
        payload = auth_service.decode_jwt_token(token)
    except AppError:
        # WebSocket 场景不抛异常，交由调用方决定如何响应
        return None
    user_id = payload.get("user_id")
    if not isinstance(user_id, int):
        return None
    return await _load_identity(user_id)
