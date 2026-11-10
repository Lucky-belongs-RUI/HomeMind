"""RAG 检索入口：用户私有数据 + 家庭规章制度双集合。"""

from homemind.rag.embedder import get_embedder
from homemind.rag.vector_store import get_vector_store


async def retrieve_relevant_docs(
    query: str,
    user_id: int,
    family_id: int,
    top_k: int = 3,
    include_private: bool = True,
):
    """检索与用户输入相关的文档片段（按家庭隔离）。

    include_private=False 时仅检索家庭规章制度（用于家庭报告等家庭级场景）。
    """
    return await get_vector_store().query(
        query_text=query,
        user_id=user_id,
        family_id=family_id,
        top_k=top_k,
        embedder=get_embedder(),
        include_private=include_private,
    )
