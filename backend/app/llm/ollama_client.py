"""本地 Ollama 适配器：OpenAI 兼容接口，base_url 指向本地 11434。

Ollama 的 /v1 端点忽略 api_key 字段（传任意非空值即可），
模型名由本地 `ollama pull <model>` 决定，如 qwen2.5:7b、deepseek-r1:7b。
"""
from typing import List, Optional

from openai import AsyncOpenAI

from app.config import settings
from app.llm.qwen_client import QwenClient
from app.llm.embed_utils import local_embed_texts


class OllamaClient(QwenClient):
    """本地 Ollama 适配器，复用 QwenClient 的 OpenAI 兼容实现，仅配置不同。"""

    def __init__(self, model: Optional[str] = None):
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key or settings.ollama_api_key or "ollama",
            base_url=settings.llm_base_url or settings.ollama_base_url,
        )
        self.model = model or settings.ollama_model or "qwen2.5:7b"

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Ollama 未保证 embedding 接口，直接使用本地中文向量，避免请求 404。"""
        return local_embed_texts(texts)
