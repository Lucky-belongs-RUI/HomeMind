import hashlib
import re
from typing import List, Optional

from openai import AsyncOpenAI

from app.config import settings
from app.llm.qwen_client import QwenClient
from app.llm.embed_utils import local_embed_texts


class DeepSeekClient(QwenClient):
    """DeepSeek 适配器，复用 OpenAI 兼容实现，仅配置不同。"""

    def __init__(self, model: Optional[str] = None):
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key or settings.deepseek_api_key,
            base_url=settings.llm_base_url or settings.deepseek_base_url,
        )
        self.model = model or settings.deepseek_model or settings.llm_model

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """DeepSeek 未提供 embedding 接口，使用本地中文向量，避免请求 404。"""
        return local_embed_texts(texts)