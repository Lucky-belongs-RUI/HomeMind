from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional
from app.llm.message import LLMResponse, Message, ToolDefinition


class BaseLLMClient(ABC):
    """LLM 适配层抽象接口，所有模型客户端必须实现。"""

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """普通对话。"""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """带工具调用（Function Calling）的对话。"""

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """流式对话。"""

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """文本向量化。"""
