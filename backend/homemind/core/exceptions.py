from typing import Any

class AppError(Exception):
    code: str = "internal_error"
    http_status: int = 500
    default_message: str = "服务内部错误"

    def __init__(
        self,
        message: str = "",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """转成响应体。

        `detail` 与 FastAPI 默认错误结构保持一致，前端无需改造即可读取；
        `code` 是新增的机器可读标识。
        """
        payload: dict[str, Any] = {"detail": self.message, "code": self.code}
        if self.details:
            payload["details"] = self.details
        return payload


# ============================================================
# 语义子类
# ============================================================


class ValidationError(AppError):
    """请求参数不合法（与 pydantic 的 ValidationError 区分：这里是业务校验）。"""

    code = "validation_error"
    http_status = 422
    default_message = "请求参数不合法"


class PayloadTooLargeError(AppError):
    """请求体超过允许大小（文件上传、音频上传）。"""

    code = "payload_too_large"
    http_status = 413
    default_message = "请求内容过大"


class AuthenticationError(AppError):
    """认证失败：凭据错误、Token 无效或过期。"""

    code = "authentication_failed"
    http_status = 401
    default_message = "认证失败"


class PermissionDeniedError(AppError):
    """已认证但无权执行：角色不足、跨家庭访问。"""

    code = "permission_denied"
    http_status = 403
    default_message = "无权执行此操作"


class NotFoundError(AppError):
    """目标资源不存在，或不属于当前用户可见范围。

    注意：跨家庭访问同样返回 404 而非 403——避免通过状态码差异
    探测出"某个 ID 确实存在但不属于我"。
    """

    code = "not_found"
    http_status = 404
    default_message = "资源不存在"


class ConflictError(AppError):
    """资源冲突：唯一键重复、状态不允许当前操作。"""

    code = "conflict"
    http_status = 409
    default_message = "资源冲突"


class RateLimitError(AppError):
    """触发限流或账号锁定。"""

    code = "rate_limited"
    http_status = 429
    default_message = "请求过于频繁，请稍后再试"


class ExternalServiceError(AppError):
    """依赖的外部服务不可用（LLM、向量化、语音等）。"""

    code = "external_service_error"
    http_status = 503
    default_message = "外部服务暂时不可用"


#: 服务层抛出后应被当作"业务错误"处理的异常元组。
#: 工具层等需要宽口径捕获的地方可以直接用它，避免遗漏新增的子类。
DOMAIN_ERRORS = (
    AppError,
    ValueError,
    PermissionError,
)
