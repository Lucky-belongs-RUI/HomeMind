from typing import List, Optional

from openai import AsyncOpenAI

from app.config import settings
from app.llm.qwen_client import QwenClient
from app.llm.embed_utils import local_embed_texts


class ZhipuClient(QwenClient):
    """质谱 GLM 适配器，采用 OpenAI 兼容接口。"""

    def __init__(self, model: Optional[str] = None):
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key or settings.zhipu_api_key,
            base_url=settings.llm_base_url or settings.zhipu_base_url,
        )
        self.model = model or settings.llm_model or settings.zhipu_model

    async def embed(self, texts: List[str]) -> List[List[float]]:
        try:
            resp = await self.client.embeddings.create(model="embedding-3", input=texts)
            return [item.embedding for item in resp.data]
        except Exception:
            return local_embed_texts(texts)