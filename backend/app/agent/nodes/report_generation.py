"""报告生成链路节点：结合全屋状态与知识库生成家庭情况报告。"""
import json
import logging

from app.agent.nodes._base import build_llm_messages, log_node_run
from app.agent.nodes.house_status import build_house_status_text
from app.agent.nodes.rag_retrieval import rag_retrieval_node
from app.agent.rules.common import extract_json
from app.llm.factory import get_llm_client

logger = logging.getLogger(__name__)

REPORT_PROMPT = """你是智能家居家庭管家，请根据当前家庭状态生成一份简洁的家庭情况报告。

当前家庭状态：
{house_status}

知识库参考：
{rag_context}

用户要求：{user_input}
识别到的意图（JSON）：{intents}

报告结构：
① 环境概览（温度、湿度、空气质量、天气等）
② 设备与房间状态
③ 异常或建议（若有安全告警务必指出）
④ 结语

回复要求：
1. 使用中文，条理清晰，可读性高。
2. 长度控制在 400 字以内，不要输出 JSON。"""


def build_rule_report(state: dict) -> str:
    """规则版报告（LLM 不可用或输出异常时降级）。"""
    status = state.get("house_status") or {}
    body = build_house_status_text(status)
    return f"【家庭情况报告】\n{body}\n\n总体来看，家庭设备运行状态已汇总如上。如需进一步操作或详细分析，随时告诉我。"


@log_node_run
async def report_generation_node(state: dict) -> dict:
    """报告链路：确保全屋状态与 RAG 上下文就绪后生成报告。"""
    state = dict(state)

    # 报告需要全屋状态：缺失时补齐
    if not state.get("house_status"):
        from app.agent.nodes.house_status import house_status_retrieval_node

        state = await house_status_retrieval_node(state)

    # 报告需要知识库上下文：未检索过时触发 RAG 检索
    if not state.get("rag_context") or state.get("rag_context") in (
        "（无需检索）",
        "（无相关文档片段）",
    ):
        state = await rag_retrieval_node(state)

    system = REPORT_PROMPT.format(
        house_status=build_house_status_text(state.get("house_status") or {}),
        rag_context=state.get("rag_context") or "（无）",
        user_input=state.get("user_input", ""),
        intents=json.dumps(state.get("intents", []), ensure_ascii=False),
    )

    text = ""
    try:
        client = get_llm_client()
        result = await client.chat(
            messages=build_llm_messages(state),
            system=system,
            temperature=0.5,
            max_tokens=1024,
        )
        text = (result.content or "").strip()
    except Exception as exc:  # LLM 异常不影响主流程
        logger.warning("报告生成链路 LLM 调用异常: %s", exc)

    if not text or extract_json(text):
        text = build_rule_report(state)

    chain_results = dict(state.get("chain_results") or {})
    chain_results["report"] = {"text": text, "sources": state.get("rag_sources") or []}
    state["chain_results"] = chain_results
    state["avatar_emotion"] = "working"
    return state
