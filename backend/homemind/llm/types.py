"""LLM 适配层公共类型：统一消息格式与客户端抽象接口。"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel


class ToolDefinition(BaseModel):
    """工具定义，传给 LLM 让其知道可调用哪些工具。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema 格式


class ToolCall(BaseModel):
    """LLM 返回的工具调用请求。"""

    id: str
    name: str
    arguments: dict[str, Any]


class Message(BaseModel):
    """统一消息格式，适配层内部转换到各模型专有格式。"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None  # assistant 调用工具时
    tool_call_id: str | None = None  # role=tool 时关联的调用 ID
    name: str | None = None  # role=tool 时工具名称


class LLMResponse(BaseModel):
    """LLM 统一响应。"""

    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str = "stop"
    usage: dict[str, int] = {}


class BaseLLMClient(ABC):
    """LLM 适配层抽象接口，所有模型客户端必须实现。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """普通对话。"""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """带工具调用（Function Calling）的对话。"""

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[Message],
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """流式对话。"""
