"""OpenAI 兼容供应商客户端。

Qwen / DeepSeek / 智谱 / Ollama 都走 OpenAI 兼容协议，共用一套请求与
消息转换实现，差异仅在密钥、base_url 与模型名。
"""

import json
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from homemind.core.config import settings
from homemind.llm.errors import record_llm_error
from homemind.llm.types import (
    BaseLLMClient,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
)

# 各供应商的兜底模型名
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "qwen": "qwen-plus",
    "deepseek": "deepseek-v4-flash",
    "zhipu": "glm-4",
    "ollama": "qwen2.5:7b",
}

# 前端可选模型列表（与前端 MODEL_OPTIONS 保持一致）
SUPPORTED_PROVIDERS = tuple(PROVIDER_DEFAULT_MODELS)


class QwenClient(BaseLLMClient):
    """通义千问适配器，兼容 OpenAI 格式。"""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.llm_api_key or settings.qwen_api_key,
            base_url=base_url or settings.llm_base_url or settings.qwen_base_url,
        )
        self.model = model or settings.llm_model or settings.qwen_model

    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        openai_messages = self._to_openai_messages(messages, system)
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            record_llm_error(exc)
            raise
        choice = resp.choices[0]
        return LLMResponse(
            content=choice.message.content,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            },
        )

    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        openai_messages = self._to_openai_messages(messages, system)
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                tools=openai_tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            record_llm_error(exc)
            raise
        choice = resp.choices[0]
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments or "{}"),
                )
                for tc in choice.message.tool_calls
            ]
        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            },
        )

    async def stream_chat(
        self,
        messages: list[Message],
        system: str | None = None,
    ) -> AsyncIterator[str]:
        openai_messages = self._to_openai_messages(messages, system)
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            record_llm_error(exc)
            raise

    def _to_openai_messages(self, messages: list[Message], system: str | None):
        result = []
        if system:
            result.append({"role": "system", "content": system})
        for msg in messages:
            if msg.role == "tool":
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content or "",
                    }
                )
            elif msg.role == "assistant" and msg.tool_calls:
                result.append(
                    {
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
            else:
                result.append({"role": msg.role, "content": msg.content})
        return result


class DeepSeekClient(QwenClient):
    """DeepSeek 适配器，复用 OpenAI 兼容实现，仅配置不同。"""

    # 兼容历史版本误用的模型名（官方仅 deepseek-chat / deepseek-reasoner）
    _MODEL_ALIASES = {
        "deepseek-v4-pro": "deepseek-chat",
        "deepseek-v4-flash": "deepseek-chat",
    }

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.llm_api_key or settings.deepseek_api_key,
            base_url=base_url or settings.llm_base_url or settings.deepseek_base_url,
        )
        self.model = model or settings.deepseek_model or settings.llm_model
        self.model = self._MODEL_ALIASES.get(self.model, self.model)


class ZhipuClient(QwenClient):
    """智谱 GLM 适配器，采用 OpenAI 兼容接口。"""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.llm_api_key or settings.zhipu_api_key,
            base_url=base_url or settings.llm_base_url or settings.zhipu_base_url,
        )
        self.model = model or settings.llm_model or settings.zhipu_model


class OllamaClient(QwenClient):
    """本地 Ollama 适配器，复用 QwenClient 的 OpenAI 兼容实现，仅配置不同。

    Ollama 的 /v1 端点忽略 api_key 字段（传任意非空值即可），
    模型名由本地 `ollama pull <model>` 决定，如 qwen2.5:7b、deepseek-r1:7b。
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.llm_api_key or settings.ollama_api_key or "ollama",
            base_url=base_url or settings.llm_base_url or settings.ollama_base_url,
        )
        self.model = model or settings.ollama_model or "qwen2.5:7b"
