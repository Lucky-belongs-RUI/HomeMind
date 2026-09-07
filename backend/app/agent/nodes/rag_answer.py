"""智能问答链路节点：基于 RAG 检索结果生成回答。"""
import json
import logging

from app.agent.nodes._base import build_llm_messages, log_node_run
from app.agent.rules.common import extract_json
from app.llm.factory import get_llm_client

logger = logging.getLogger(__name__)

RAG_ANSWER_PROMPT = """你是智能家居知识助手，请基于检索到的知识库内容回答用户问题。

用户输入：{user_input}
检索到的知识片段：
{rag_context}

回复要求：
1. 直接基于知识片段回答，并标注来源（如《文件名》）。
2. 知识片段不足时如实说明"暂未找到相关内容"，不要编造。
3. 简洁自然，不要输出 JSON。"""


def build_rule_rag_answer(state: dict) -> str:
    """规则版知识回答（LLM 不可用或输出异常时降级）。"""
    sources = state.get("rag_sources") or []
    context = state.get("rag_context") or ""
    if sources:
        source_names = "、".join(dict.fromkeys(s.get("source") or "知识库" for s in sources))
        return f"根据《{source_names}》：{context}"
    if context and context not in ("（无需检索）", "（无相关文档片段）"):
        return f"根据知识库：{context}"
    return "暂未找到相关规定或偏好内容，您可以上传规章制度或偏好文档供我学习。"


@log_node_run
async def rag_answer_node(state: dict) -> dict:
    """知识问答链路：根据 rag_context 生成回答，写入 chain_results['knowledge']。"""
    state = dict(state)
    system = RAG_ANSWER_PROMPT.format(
        user_input=state.get("user_input", ""),
        rag_context=state.get("rag_context") or "（无检索结果）",
    )

    text = ""
    try:
        client = get_llm_client()
        result = await client.chat(
            messages=build_llm_messages(state),
            system=system,
            temperature=0.3,
            max_tokens=800,
        )
        text = (result.content or "").strip()
    except Exception as exc:  # LLM 异常不影响主流程
        logger.warning("智能问答链路 LLM 调用异常: %s", exc)

    if not text or extract_json(text):
        text = build_rule_rag_answer(state)

    chain_results = dict(state.get("chain_results") or {})
    chain_results["knowledge"] = {
        "text": text,
        "sources": state.get("rag_sources") or [],
    }
    state["chain_results"] = chain_results
    state["avatar_emotion"] = "neutral"
    return state
