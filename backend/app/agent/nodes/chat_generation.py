"""聊天链路节点：日常寒暄与情感关怀，无需数据库与工具调用。"""
import json
import logging

from app.agent.nodes._base import build_llm_messages, log_node_run
from app.agent.nodes.house_status import build_house_status_text
from app.agent.rules.common import extract_json
from app.llm.factory import get_llm_client

logger = logging.getLogger(__name__)

CHAT_PROMPT = """你是智能家居助理，正在与用户进行日常聊天或情感关怀。

用户输入：{user_input}
识别到的意图（JSON）：{intents}
当前家庭状态：
{house_status}

回复要求：
1. 语气温暖自然，像朋友一样聊天。
2. 若用户表达不适或情绪低落，先表达关心，再给出简单可行的建议。
3. 不要输出 JSON，不要编造设备操作，长度控制在 200 字以内。"""


def build_rule_chat(state: dict) -> str:
    """规则版聊天回复（LLM 不可用或输出异常时降级）。"""
    user_input = state.get("user_input", "")
    intent_types = {item.get("type") for item in state.get("intents") or []}
    if "emotional_care" in intent_types:
        return (
            "看到您状态不太好，我有点担心。您先别急，需要我帮您做点什么，"
            "比如调整一下室温、播放舒缓的音乐，随时告诉我。"
        )
    return f"收到，我一直在呢。关于“{user_input}”，您还需要我帮您做点什么吗？"


@log_node_run
async def chat_generation_node(state: dict) -> dict:
    """聊天链路：生成日常/情感回复，写入 chain_results['chat']。"""
    state = dict(state)
    system = CHAT_PROMPT.format(
        user_input=state.get("user_input", ""),
        intents=json.dumps(state.get("intents", []), ensure_ascii=False),
        house_status=build_house_status_text(state.get("house_status") or {}),
    )

    text = ""
    try:
        client = get_llm_client()
        result = await client.chat(
            messages=build_llm_messages(state),
            system=system,
            temperature=0.8,
            max_tokens=512,
        )
        text = (result.content or "").strip()
    except Exception as exc:  # LLM 异常不影响主流程
        logger.warning("聊天链路 LLM 调用异常: %s", exc)

    if not text or extract_json(text):
        text = build_rule_chat(state)

    chain_results = dict(state.get("chain_results") or {})
    chain_results["chat"] = {"text": text, "intents": state.get("intents", [])}
    state["chain_results"] = chain_results
    state["avatar_emotion"] = "caring" if "emotional_care" in {
        item.get("type") for item in state.get("intents") or []
    } else "leisure"
    return state
