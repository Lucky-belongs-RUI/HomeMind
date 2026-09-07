from app.llm.factory import get_llm_client


def get_embedder():
    """返回 LLM 客户端作为向量化器（实现 embed 接口）。"""
    return get_llm_client()
