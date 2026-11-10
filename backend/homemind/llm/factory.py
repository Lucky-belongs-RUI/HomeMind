"""LLM 客户端工厂：按供应商与模型创建客户端，支持多模型切换。

模型选择优先级：
1. 当前请求上下文（API 层通过 set_llm_choice 注入，按 asyncio 上下文隔离）；
2. 全局配置 settings.llm_provider / settings.llm_model。

未配置 API Key 或客户端构建失败时直接抛出明确错误，不使用演示客户端。
"""

from homemind.core.config import settings
from homemind.llm.errors import record_llm_error
from homemind.llm.providers import (
    PROVIDER_DEFAULT_MODELS,
    SUPPORTED_PROVIDERS,
    DeepSeekClient,
    OllamaClient,
    QwenClient,
    ZhipuClient,
)
from homemind.llm.runtime import get_llm_choice, set_llm_choice
from homemind.llm.types import BaseLLMClient

# 兼容旧导入：set_llm_choice 现在由 runtime 统一维护
__all__ = ["SUPPORTED_PROVIDERS", "get_llm_client", "set_llm_choice"]


def _resolve_choice() -> tuple[str, str]:
    context_provider, context_model, _api_key, _base_url = get_llm_choice()
    provider = (context_provider or settings.llm_provider).lower()
    model = (
        context_model
        or getattr(settings, f"{provider}_model", "")
        or settings.llm_model
        or PROVIDER_DEFAULT_MODELS.get(provider, "qwen-plus")
    )
    return provider, model


def _provider_api_key(provider: str) -> str:
    """返回供应商的 API Key；Ollama 本地模型始终可用。"""
    context_provider, _model, context_key, _base_url = get_llm_choice()
    if context_key and provider == context_provider:
        return context_key
    if provider == "ollama":
        return settings.ollama_api_key or "ollama"
    key = getattr(settings, f"{provider}_api_key", "")
    return key or settings.llm_api_key or ""


def _build_client(
    provider: str,
    model: str,
    api_key: str = "",
    base_url: str = "",
) -> BaseLLMClient:
    if provider == "qwen":
        return QwenClient(model=model, api_key=api_key, base_url=base_url)
    if provider == "deepseek":
        return DeepSeekClient(model=model, api_key=api_key, base_url=base_url)
    if provider == "zhipu":
        return ZhipuClient(model=model, api_key=api_key, base_url=base_url)
    if provider == "ollama":
        return OllamaClient(model=model, api_key=api_key, base_url=base_url)
    raise ValueError(f"不支持的 LLM provider: {provider}")


def get_llm_client(
    provider: str | None = None,
    model: str | None = None,
) -> BaseLLMClient:
    """返回 LLM 客户端。

    未显式传 provider/model 时使用当前上下文（set_llm_choice 设置）或全局默认；
    供应商未配置 API Key（Ollama 除外）或客户端构建失败时抛出明确错误。
    """
    context_provider, context_model, context_key, context_base_url = get_llm_choice()

    if provider:
        p = provider.lower()
        m = (
            model
            or (context_model if p == context_provider else "")
            or getattr(settings, f"{p}_model", "")
            or settings.llm_model
            or PROVIDER_DEFAULT_MODELS.get(p, "qwen-plus")
        )
        api_key = context_key if p == context_provider else ""
        base_url = context_base_url if p == context_provider else ""
    else:
        p, m = _resolve_choice()
        api_key = context_key if p == context_provider else ""
        base_url = context_base_url if p == context_provider else ""

    if p not in SUPPORTED_PROVIDERS or not (api_key or _provider_api_key(p)):
        exc = RuntimeError(f"LLM 供应商 '{p}' 未配置 API Key，请在模型配置中填写 Key 后重试")
        record_llm_error(exc)
        raise exc
    try:
        if (settings.llm_engine or "").strip().lower() == "langchain":
            from homemind.llm.langchain import LangChainLLMClient

            return LangChainLLMClient(provider=p, model=m)
        return _build_client(p, m, api_key=api_key, base_url=base_url)
    except Exception as exc:
        # 客户端构建失败（如 base_url 异常）直接抛出，由调用方决定如何回退
        exc = RuntimeError(f"LLM 客户端构建失败: {exc}")
        record_llm_error(exc)
        raise exc

