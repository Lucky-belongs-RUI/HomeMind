"""组织语言回复节点：结合多链路结果、RAG、意图与执行结果生成自然语言回复。"""
import json
import logging

from app.agent.rules.common import extract_json
from app.agent.rules.planning import build_rule_avatar_emotion, build_rule_response
from app.llm.factory import get_llm_client
from app.agent.nodes._base import build_llm_messages, log_node_run

logger = logging.getLogger(__name__)

RESPONSE_PROMPT = """你是智能家居助理，请把各条执行链路的结果组织成一段自然、温暖的中文回复。

用户输入：{user_input}
识别意图：{intents}
各链路结果：
{chain_texts}
工具执行统计：成功 {success_count}，失败 {failure_count}，跳过 {skipped_count}
工具执行明细：
{tool_results}

回复要求：
1. 知识问答：直接引用知识库结果并标注来源。
2. 设备控制：汇报执行结果；失败时说明原因并给出建议。
3. 情感关怀：先表达关怀，再说明已执行的措施。
4. 报告生成：直接采用报告内容。
5. 多链路并存时（如关怀 + 设备调整），把各结果自然衔接成一段连贯回复。
6. 简洁自然，不要输出 JSON，不要重复工具内部字段。
"""


def _chain_texts(state: dict) -> str:
    """把各链路结果汇总成文本，供回复生成 LLM 与规则回退使用。"""
    chain_results = state.get("chain_results") or {}
    lines = []
    if chain_results.get("chat"):
        lines.append(f"[情感/闲聊] {chain_results['chat']['text']}")
    if chain_results.get("knowledge"):
        lines.append(f"[知识问答] {chain_results['knowledge']['text']}")
    if chain_results.get("report"):
        lines.append(f"[报告] {chain_results['report']['text']}")
    control = chain_results.get("control") or {}
    if control.get("cancelled"):
        lines.append(f"[操作] {control.get('message') or '已取消本次操作。'}")
    return "\n".join(lines) if lines else "（无链路结果）"


def _tool_summary(state: dict) -> str:
    lines = []
    for item in state.get("tool_results") or []:
        description = item.get("description", "")
        if item.get("status") == "success":
            message = item.get("message") or ""
            data = item.get("data") or {}
            detail = message
            if data:
                payload = json.dumps(data, ensure_ascii=False)
                if len(payload) > 1500:
                    payload = payload[:1500] + "..."
                detail = f"{message} 数据：{payload}" if message else f"数据：{payload}"
            lines.append(f"[成功] {description}：{detail}")
        elif item.get("status") == "failed":
            lines.append(f"[失败] {description}：{item.get('error', '')}")
        else:
            lines.append(f"[跳过] {description}")
    return "\n".join(lines) if lines else "（无工具执行）"


def _merge_chain_response(state: dict) -> str:
    """规则版多链路合并：优先使用各链路的自然语言文本，工具结果走规则汇总。"""
    chain_results = state.get("chain_results") or {}
    tool_results = state.get("tool_results") or []
    control = chain_results.get("control") or {}
    parts = []

    if chain_results.get("knowledge"):
        parts.append(chain_results["knowledge"]["text"])
    if chain_results.get("report"):
        parts.append(chain_results["report"]["text"])
    if chain_results.get("chat"):
        parts.append(chain_results["chat"]["text"])
    if control.get("cancelled"):
        parts.append(control.get("message") or "好的，已取消本次操作。")
    elif tool_results:
        summary = build_rule_response(state)
        if summary and summary not in ("操作已完成。", "好的。"):
            parts.append(summary)

    if not parts:
        parts.append(build_rule_response(state))
    return "\n\n".join(part for part in parts if part and part.strip())


@log_node_run
async def response_generation_node(state: dict) -> dict:
    """生成最终回复与虚拟形象情感状态。"""
    state = dict(state)
    chain_results = state.get("chain_results") or {}
    active = state.get("active_chains") or []

    # 纯闲聊链路：直接使用聊天文本，避免二次生成造成啰嗦
    if len(active) == 1 and active[0] == "chat":
        text = (chain_results.get("chat") or {}).get("text") or ""
        if text:
            state["final_response"] = text
            state["avatar_emotion"] = build_rule_avatar_emotion(state)
            return state

    system = RESPONSE_PROMPT.format(
        user_input=state.get("user_input", ""),
        intents=json.dumps(state.get("intents", []), ensure_ascii=False),
        chain_texts=_chain_texts(state),
        success_count=state.get("success_count", 0),
        failure_count=state.get("failure_count", 0),
        skipped_count=state.get("skipped_count", 0),
        tool_results=_tool_summary(state),
    )

    response_text = ""
    try:
        client = get_llm_client()
        result = await client.chat(
            messages=build_llm_messages(state),
            system=system,
            temperature=0.5,
            max_tokens=1024,
        )
        response_text = (result.content or "").strip()
    except Exception as exc:  # LLM 异常回退规则回复
        logger.warning("回复生成 LLM 调用异常: %s", exc)

    # 防止 LLM 误输出 JSON 结构
    if not response_text or extract_json(response_text):
        response_text = _merge_chain_response(state)

    state["final_response"] = response_text or _merge_chain_response(state)
    state["avatar_emotion"] = build_rule_avatar_emotion(state)
    return state
