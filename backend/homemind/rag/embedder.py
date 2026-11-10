"""RAG 向量化：阿里云 DashScope text-embedding-v2。

RAG 强制使用本嵌入模型，**禁止任何本地降级**：
- 未配置 API Key / 请求失败 / 返回异常 → 直接抛出 RuntimeError，
  由调用方（文件处理标记 failed、检索报错）显式暴露问题，绝不静默回退。
- 输出 1536 维稠密向量（text-embedding-v2 固定维度）。
- 单次请求分批（settings.embed_batch_size，默认 10），单条超长先截断，
  规避接口的条数与 token 上限。
"""

import logging

from openai import AsyncOpenAI

from homemind.core.config import settings

logger = logging.getLogger(__name__)

# text-embedding-v2 单条输入的安全截断长度（字符），避免超 token 上限
MAX_TEXT_CHARS = 2000


class DashScopeEmbedder:
    """阿里云 DashScope text-embedding-v2 向量化器。"""

    def __init__(self):
        if not settings.dashscope_api_key:
            raise RuntimeError(
                "未配置 DASHSCOPE_API_KEY，RAG 向量化必须使用阿里云 text-embedding-v2，不允许本地降级"
            )
        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )
        self.model = settings.embedding_model or "text-embedding-v2"

    @staticmethod
    def _truncate(text: str) -> str:
        return (text or "")[:MAX_TEXT_CHARS]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。分批调用，任一失败直接抛错（禁降级）。"""
        if not texts:
            return []
        batch_size = max(1, settings.embed_batch_size)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            try:
                resp = await self.client.embeddings.create(
                    model=self.model,
                    input=[self._truncate(t) for t in batch],
                )
                vectors.extend(item.embedding for item in resp.data)
            except Exception as exc:
                raise RuntimeError(
                    f"DashScope text-embedding-v2 向量化失败（禁止降级）: {exc}"
                ) from exc
        return vectors


# 模块级单例（AsyncOpenAI 客户端复用连接）
_embedder = None


def get_embedder() -> DashScopeEmbedder:
    """返回 DashScope 向量化器（text-embedding-v2，失败即报错，无降级）。"""
    global _embedder
    if _embedder is None:
        _embedder = DashScopeEmbedder()
    return _embedder
