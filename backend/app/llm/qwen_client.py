import json
from typing import AsyncIterator, List, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.llm.base import BaseLLMClient
from app.llm.message import LLMResponse, Message, ToolCall, ToolDefinition
from app.llm.embed_utils import local_embed_texts


class QwenClient(BaseLLMClient):
    """通义千问适配器，兼容 OpenAI 格式。"""

    def __init__(self, model: Optional[str] = None):
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key or settings.qwen_api_key,
            base_url=settings.llm_base_url or settings.qwen_base_url,
        )
        self.model = model or settings.llm_model or settings.qwen_model

    async def chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        openai_messages = self._to_openai_messages(messages, system)
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
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
        messages: List[Message],
        tools: List[ToolDefinition],
        system: Optional[str] = None,
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
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            tools=openai_tools,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=max_tokens,
        )
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
        messages: List[Message],
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        openai_messages = self._to_openai_messages(messages, system)
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, texts: List[str]) -> List[List[float]]:
        try:
            resp = await self.client.embeddings.create(
                model=settings.embedding_model,
                input=texts,
            )
            return [item.embedding for item in resp.data]
        except Exception:
            # 云端 embedding 不可用时使用本地中文向量，保证 RAG 仍可检索
            return local_embed_texts(texts)

    def _to_openai_messages(self, messages: List[Message], system: Optional[str]):
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
