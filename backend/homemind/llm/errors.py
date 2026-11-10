"""LLM 调用错误收集（按 asyncio 请求上下文隔离）。

用途：模型服务不可用（如 402 余额不足）时，节点层会捕获异常走规则兜底，
但用户不知道发生了什么。本模块在 LLM 客户端抛出异常时记录错误，
API 层在返回响应/推送 WebSocket 时带上 model_warning，前端据此明确告知用户。

独立成模块避免 factory / providers 与错误收集之间形成循环导入。
"""

import contextvars
import logging
import re

logger = logging.getLogger(__name__)

# 当前请求收集到的 LLM 错误（contextvar 按请求隔离，避免并发串扰）。
# 默认值用不可变元组：ContextVar 的默认值在多个上下文间共享，
# 若用 list，某一处 append 会污染所有未显式 set 过的上下文。
_llm_errors: contextvars.ContextVar = contextvars.ContextVar("llm_errors", default=())

_ERROR_CODE_MESSAGES = {
    401: "API Key 无效或无权限",
    402: "余额不足，请充值后重试",
    403: "无访问权限",
    404: "模型不存在或接口地址错误",
    429: "请求过于频繁，请稍后再试",
    500: "模型服务内部错误",
    502: "模型网关错误",
    503: "模型服务不可用",
}


def _extract_status_code(exc: Exception) -> int | None:
    """从异常中提取 HTTP 状态码（openai.APIStatusError 等）。"""
    status = getattr(exc, "status_code", None)
    if status:
        return int(status)
    m = re.search(r"Error code: (\d+)", str(exc))
    if m:
        return int(m.group(1))
    m = re.search(r"status[:\s]+(\d{3})", str(exc), re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def format_llm_warning(exc: Exception, fallback: str = "模型服务调用失败") -> str:
    """把异常格式化为给用户看的短提示（含状态码与原因）。"""
    code = _extract_status_code(exc)
    if code is not None:
        reason = _ERROR_CODE_MESSAGES.get(code, "服务异常")
        return f"模型服务不可用（{code} {reason}）"
    message = str(exc) or ""
    if len(message) > 80:
        message = message[:80] + "..."
    return f"模型服务不可用（{fallback}）" if not message else f"模型服务不可用：{message}"


def record_llm_error(exc: Exception) -> None:
    """记录一次 LLM 调用错误（当前请求上下文内累积，最多保留 3 条）。"""
    try:
        errs = list(_llm_errors.get())
        errs.append(exc)
        _llm_errors.set(errs[-3:])
        logger.warning("记录 LLM 调用错误: %s", str(exc)[:200])
    except Exception:
        # 记录失败不影响主流程
        pass


def clear_llm_errors() -> None:
    """清空当前请求的 LLM 错误（每次 Agent 执行前调用）。"""
    _llm_errors.set([])


def get_llm_warning() -> str | None:
    """返回最近一次 LLM 错误的用户可读提示；无错误返回 None。"""
    errs = _llm_errors.get()
    if not errs:
        return None
    return format_llm_warning(errs[-1])
