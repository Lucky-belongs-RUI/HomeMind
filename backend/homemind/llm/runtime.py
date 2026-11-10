"""当前请求的 LLM 运行时覆盖。

API 层解析用户个人模型配置后，把 provider/model/API Key/base_url 写入
contextvar；工厂与 LangChain 适配层在本次 asyncio 上下文中读取，
避免并发请求互相串用凭证。
"""

from __future__ import annotations

import contextvars

_provider: contextvars.ContextVar[str] = contextvars.ContextVar("llm_provider", default="")
_model: contextvars.ContextVar[str] = contextvars.ContextVar("llm_model", default="")
_api_key: contextvars.ContextVar[str] = contextvars.ContextVar("llm_api_key", default="")
_base_url: contextvars.ContextVar[str] = contextvars.ContextVar("llm_base_url", default="")


def set_llm_choice(
    provider: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
) -> None:
    _provider.set((provider or "").strip().lower())
    _model.set((model or "").strip())
    _api_key.set((api_key or "").strip())
    _base_url.set((base_url or "").strip())


def get_llm_choice() -> tuple[str, str, str, str]:
    return _provider.get(), _model.get(), _api_key.get(), _base_url.get()
