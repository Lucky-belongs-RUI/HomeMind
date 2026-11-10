"""LangChain 模型工厂与 BaseLLMClient 适配器。

- `build_chat_model` / `build_router_model` / `build_response_model`：
  统一构建 ChatOpenAI（Qwen / DeepSeek / 智谱 / Ollama 均走 OpenAI 兼容协议），
  统一超时、重试、max_tokens、结构化输出与降级链路；
- `LangChainLLMClient`：让仍使用 `BaseLLMClient` 的直连场景（开场白、画像提取）
  不改签名就跑在 LangChain ChatModel 上；
- Agent 图本身直接用 ChatModel，不经过适配器；适配器由 `LLM_ENGINE=langchain` 启用。

所有供应商的密钥与 base_url 仍来自 Settings，不引入第二套配置中心。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from homemind.core.config import settings
from homemind.llm.providers import PROVIDER_DEFAULT_MODELS, SUPPORTED_PROVIDERS
from homemind.llm.runtime import get_llm_choice
from homemind.llm.types import (
    BaseLLMClient,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class LLMNotConfiguredError(RuntimeError):
    """供应商未配置可用密钥，属于部署配置错误。"""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    api_key: str
    base_url: str


def _provider_setting(provider: str, field: str) -> str:
    return str(getattr(settings, f"{provider}_{field}", "") or "").strip()


def resolve_provider_config(provider: str | None = None, model: str | None = None) -> ProviderConfig:
    """解析供应商、模型、密钥与 base_url。

    优先使用当前请求上下文中的个人模型配置（provider/model/api_key/base_url），
    未提供时回退到 .env 的供应商配置。
    """
    context_provider, context_model, context_key, context_base_url = get_llm_choice()
    name = (provider or context_provider or settings.llm_provider or "qwen").strip().lower()
    if name not in SUPPORTED_PROVIDERS:
        raise LLMNotConfiguredError(f"不支持的 LLM provider: {name}")

    use_context = name == context_provider
    if name == "ollama":
        api_key = (context_key if use_context else "") or settings.ollama_api_key or "ollama"
    else:
        api_key = (
            (context_key if use_context else "")
            or _provider_setting(name, "api_key")
            or settings.llm_api_key
        )
    if not api_key:
        raise LLMNotConfiguredError(
            f"LLM 供应商 '{name}' 未配置 API Key，请配置 {name}_api_key 或 LLM_API_KEY"
        )

    base_url = (
        (context_base_url if use_context else "")
        or _provider_setting(name, "base_url")
        or settings.llm_base_url
        or ""
    )
    model_name = (
        (model or "").strip()
        or (context_model if use_context else "")
        or _provider_setting(name, "model")
        or settings.llm_model
        or PROVIDER_DEFAULT_MODELS[name]
    )
    return ProviderConfig(provider=name, model=model_name, api_key=api_key, base_url=base_url)


def build_chat_model(
    provider: str | None = None,
    model: str | None = None,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    streaming: bool = False,
    timeout: float | None = None,
    max_retries: int = 2,
) -> ChatOpenAI:
    """构建单个 ChatModel；配置缺失时抛 LLMNotConfiguredError。"""
    cfg = resolve_provider_config(provider, model)
    return ChatOpenAI(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url or None,
        temperature=settings.llm_temperature if temperature is None else temperature,
        max_tokens=settings.llm_max_tokens if max_tokens is None else max_tokens,
        timeout=settings.agent_llm_timeout_seconds if timeout is None else timeout,
        max_retries=max_retries,
        streaming=streaming,
    )


def build_router_model(provider: str | None = None, model: str | None = None) -> ChatOpenAI:
    """路由/规划模型：低温度、短输出、低延迟。"""
    return build_chat_model(
        provider,
        model or settings.agent_router_model or None,
        temperature=0.1,
        max_tokens=1200,
        timeout=min(settings.agent_llm_timeout_seconds, 20.0),
        max_retries=1,
    )


def build_response_model(provider: str | None = None, model: str | None = None) -> ChatOpenAI:
    """最终回复模型：允许稍高温度，保留降级链路。"""
    primary_provider = (provider or settings.llm_provider or "qwen").strip().lower()
    primary = build_chat_model(
        primary_provider,
        model or settings.agent_chat_model or None,
        temperature=0.7,
        max_tokens=settings.llm_max_tokens,
    )
    fallbacks = []
    for raw in (settings.agent_fallback_providers or "").split(","):
        name = raw.strip().lower()
        if not name or name == primary_provider:
            continue
        try:
            fallbacks.append(
                build_chat_model(
                    name,
                    None,
                    temperature=0.7,
                    max_tokens=settings.llm_max_tokens,
                )
            )
        except LLMNotConfiguredError:
            logger.info("降级模型 %s 未配置密钥，已跳过", name)
    return primary.with_fallbacks(fallbacks) if fallbacks else primary


def extract_usage(message: Any) -> dict[str, int]:
    """从 LangChain AIMessage 提取 token 用量，供成本归因。"""
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        prompt = int(usage.get("input_tokens") or 0)
        completion = int(usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or prompt + completion)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

    metadata = getattr(message, "response_metadata", None) or {}
    token_usage = metadata.get("token_usage") or {}
    prompt = int(token_usage.get("prompt_tokens") or 0)
    completion = int(token_usage.get("completion_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": int(token_usage.get("total_tokens") or prompt + completion),
    }


def message_text(message: Any) -> str:
    """把 LangChain 消息的 content 统一成字符串（兼容多段 content）。"""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content or "")


def to_langchain_messages(messages: list[Message], system: str | None = None) -> list[BaseMessage]:
    """把统一消息格式转换为 LangChain 消息。"""
    result: list[BaseMessage] = []
    if system:
        result.append(SystemMessage(content=system))

    for message in messages:
        if message.role == "system":
            result.append(SystemMessage(content=message.content or ""))
        elif message.role == "user":
            result.append(HumanMessage(content=message.content or ""))
        elif message.role == "assistant":
            if message.tool_calls:
                result.append(
                    AIMessage(
                        content=message.content or "",
                        tool_calls=[
                            {"id": call.id, "name": call.name, "args": call.arguments}
                            for call in message.tool_calls
                        ],
                    )
                )
            else:
                result.append(AIMessage(content=message.content or ""))
        elif message.role == "tool":
            result.append(
                ToolMessage(
                    content=message.content or "",
                    tool_call_id=message.tool_call_id or "",
                    name=message.name,
                )
            )
    return result


def _openai_tool_schema(definition: ToolDefinition) -> dict:
    return {
        "type": "function",
        "function": {
            "name": definition.name,
            "description": definition.description,
            "parameters": definition.parameters,
        },
    }


class LangChainLLMClient(BaseLLMClient):
    """基于 LangChain ChatModel 的 BaseLLMClient 实现。"""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        *,
        timeout: float | None = None,
        max_retries: int = 2,
    ) -> None:
        self._model = build_chat_model(
            provider,
            model,
            timeout=timeout,
            max_retries=max_retries,
        )

    def _bound(self, temperature: float, max_tokens: int):
        return self._model.bind(temperature=temperature, max_tokens=max_tokens)

    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        response = await self._bound(temperature, max_tokens).ainvoke(
            to_langchain_messages(messages, system)
        )
        return LLMResponse(
            content=message_text(response),
            finish_reason=str(
                getattr(response, "response_metadata", {}).get("finish_reason") or "stop"
            ),
            usage=extract_usage(response),
        )

    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        bound = self._bound(temperature, max_tokens).bind_tools(
            [_openai_tool_schema(tool) for tool in tools]
        )
        response = await bound.ainvoke(to_langchain_messages(messages, system))
        raw_calls = getattr(response, "tool_calls", None) or []
        tool_calls = [
            ToolCall(
                id=str(call.get("id") or f"call_{uuid.uuid4().hex[:8]}"),
                name=str(call.get("name") or ""),
                arguments=dict(call.get("args") or {}),
            )
            for call in raw_calls
        ]
        return LLMResponse(
            content=message_text(response) or None,
            tool_calls=tool_calls or None,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=extract_usage(response),
        )

    async def stream_chat(
        self,
        messages: list[Message],
        system: str | None = None,
    ) -> AsyncIterator[str]:
        lc_messages = to_langchain_messages(messages, system)
        async for chunk in self._model.astream(lc_messages):
            text = message_text(chunk)
            if text:
                yield text
