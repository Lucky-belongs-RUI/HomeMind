"""RAG 检索入口：用户私有数据 + 家庭规章制度双集合。"""
from app.rag.embedder import get_embedder
from app.rag.vector_store import vector_store


async def retrieve_relevant_docs(
    query: str, user_id: int, family_id: int, top_k: int = 3
):
    """检索与用户输入相关的文档片段（按家庭隔离）。"""
    return await vector_store.query(
        query_text=query,
        user_id=user_id,
        family_id=family_id,
        top_k=top_k,
        embedder=get_embedder(),
    )