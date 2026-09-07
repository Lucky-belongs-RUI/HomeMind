"""RAG 检索节点：双集合检索（用户私有数据 + 家庭规章制度）。"""
import logging

from app.agent.rules.common import KNOWLEDGE_QUERY_KEYWORDS
from app.agent.nodes._base import log_node_run

logger = logging.getLogger(__name__)

KNOWLEDGE_MARKERS = KNOWLEDGE_QUERY_KEYWORDS + ["有什么规定", "是什么政策"]


def _is_knowledge_query(user_input: str) -> bool:
    return any(marker in user_input for marker in KNOWLEDGE_MARKERS)


@log_node_run
async def rag_retrieval_node(state: dict) -> dict:
    """根据用户输入检索私有知识库与规章制度，组装上下文与来源。"""
    from app.rag.retriever import retrieve_relevant_docs

    state = dict(state)
    user_input = state.get("user_input", "")
    intent_types = {item.get("type") for item in state.get("intents") or []}
    if not state.get("is_knowledge_query") and "knowledge_query" not in intent_types:
        state["rag_context"] = "（无需检索）"
        state["rag_sources"] = []
        return state

    try:
        docs = await retrieve_relevant_docs(
            query=user_input,
            user_id=state["user_id"],
            family_id=state["family_id"],
            top_k=3,
        )
    except Exception as exc:  # RAG 异常不影响主流程
        logger.warning("RAG 检索异常: %s", exc)
        docs = []

    sources = [
        {
            "source": doc.get("source") or doc.get("metadata", {}).get("filename", "知识库"),
            "file_id": doc.get("metadata", {}).get("file_id"),
            "collection": doc.get("metadata", {}).get("collection", "user_documents"),
            "score": doc.get("score"),
            "content": doc.get("content", ""),
        }
        for doc in docs
    ]

    if docs:
        context_lines = []
        for doc in docs:
            source_name = doc.get("source") or doc.get("metadata", {}).get("filename", "知识库")
            content = doc.get("content", "")
            context_lines.append(f"[{source_name}] {content}")
        state["rag_context"] = "\n".join(context_lines)
    else:
        state["rag_context"] = "（无相关文档片段）"

    state["rag_sources"] = sources
    state["is_knowledge_query"] = _is_knowledge_query(user_input) or bool(sources)
    return state
