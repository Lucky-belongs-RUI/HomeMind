"""LLM 客户端工厂：按供应商与模型创建客户端，支持多模型切换。

模型选择优先级：
1. 当前请求上下文（API 层通过 set_llm_choice 注入，按 asyncio 上下文隔离）；
2. 全局配置 settings.llm_provider / settings.llm_model。

供应商未配置 API Key（Ollama 除外）时降级为演示客户端（MockLLMClient）。
"""
import contextvars
from typing import Optional

from app.config import settings
from app.llm.base import BaseLLMClient
from app.llm.deepseek_client import DeepSeekClient
from app.llm.mock_client import MockLLMClient
from app.llm.ollama_client import OllamaClient
from app.llm.qwen_client import QwenClient
from app.llm.zhipu_client import ZhipuClient

# 当前请求选择的供应商与模型（contextvar 按 asyncio 上下文隔离，避免并发串扰）
_current_provider: contextvars.ContextVar = contextvars.ContextVar("llm_provider", default="")
_current_model: contextvars.ContextVar = contextvars.ContextVar("llm_model", default="")

# 各供应商的兜底模型名
PROVIDER_DEFAULT_MODELS = {
    "qwen": "qwen-plus",
    "deepseek": "deepseek-v4-pro",
    "zhipu": "glm-4",
    "ollama": "qwen2.5:7b",
}

# 前端可选模型列表（与前端 MODEL_OPTIONS 保持一致）
SUPPORTED_PROVIDERS = ("qwen", "deepseek", "zhipu", "ollama")


def set_llm_choice(provider: str = "", model: str = "") -> None:
    """记录当前请求选用的模型供应商与模型名（进程内按上下文隔离）。"""
    _current_provider.set((provider or "").strip().lower())
    _current_model.set((model or "").strip())


def reset_llm_choice() -> None:
    """清空当前上下文中的模型选择，恢复全局默认。"""
    _current_provider.set("")
    _current_model.set("")


def _resolve_choice() -> tuple:
    provider = (_current_provider.get() or settings.llm_provider).lower()
    model = (
        _current_model.get()
        or getattr(settings, f"{provider}_model", "")
        or settings.llm_model
        or PROVIDER_DEFAULT_MODELS.get(provider, "qwen-plus")
    )
    return provider, model


def _provider_api_key(provider: str) -> str:
    """返回供应商的 API Key；Ollama 本地模型始终可用。"""
    if provider == "ollama":
        return settings.ollama_api_key or "ollama"
    key = getattr(settings, f"{provider}_api_key", "")
    return key or settings.llm_api_key or ""


def _build_client(provider: str, model: str) -> BaseLLMClient:
    if provider == "qwen":
        return QwenClient(model=model)
    if provider == "deepseek":
        return DeepSeekClient(model=model)
    if provider == "zhipu":
        return ZhipuClient(model=model)
    if provider == "ollama":
        return OllamaClient(model=model)
    raise ValueError(f"不支持的 LLM provider: {provider}")


def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseLLMClient:
    """返回 LLM 客户端。

    未显式传 provider/model 时使用当前上下文（set_llm_choice 设置）或全局默认；
    供应商未配置 API Key（Ollama 除外）时降级为演示客户端。
    """
    if provider:
        p = provider.lower()
        m = (
            model
            or getattr(settings, f"{p}_model", "")
            or settings.llm_model
            or PROVIDER_DEFAULT_MODELS.get(p, "qwen-plus")
        )
    else:
        p, m = _resolve_choice()

    if p not in SUPPORTED_PROVIDERS or not _provider_api_key(p):
        return MockLLMClient()
    try:
        return _build_client(p, m)
    except Exception:
        # 构建失败（如 base_url 异常）时降级为演示客户端
        return MockLLMClient()


def reset_llm_client():
    """兼容旧调用：客户端按需创建，无需全局缓存。"""
    return None
