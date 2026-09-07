"""意图识别节点：结合 RAG 上下文分析显式意图与隐式意图。"""
import json
import logging

from app.agent.rules.common import extract_json
from app.agent.rules.intent import (
    build_rule_intents,
    compute_active_chains,
    looks_like_pure_chat,
)
from app.llm.factory import get_llm_client
from app.agent.nodes._base import build_llm_messages, log_node_run
from app.agent.nodes.house_status import build_house_status_text

logger = logging.getLogger(__name__)

INTENT_TYPES = (
    "device_control",
    "device_query",
    "scene_trigger",
    "knowledge_query",
    "emotional_care",
    "chat",
    "report",
    "clarification",
)

INTENT_PROMPT = """你是智能家居助理的意图识别引擎，负责深度理解用户输入。

任务说明：
1. 识别用户的显式意图与隐式意图，隐式意图必须结合当前家庭状态动态判断，不套用固定操作。
2. 知识查询必须识别为 knowledge_query，后续节点会按需检索 RAG，本阶段不依赖检索结果。
3. 只输出 JSON，不要输出任何解释或代码块标记。

显式意图识别规则：
- 设备控制（device_control）：用户直接要求操作设备，输出 device_type、room_name（若指定）、attributes（如 temperature/brightness/power/position/volume/mode/locked）。
- 设备查询（device_query）：用户询问设备状态或设备列表。
- 场景触发（scene_trigger）：用户表达回家/睡觉/离家等场景化指令，输出 scene_name。
- 知识查询（knowledge_query）：用户询问规定、制度、偏好、规则等，基于 RAG 上下文回答。
- 报告生成（report）：用户要求生成家庭情况报告/总结/汇总/统计，需要结合全屋状态与知识库。
- 情感关怀（emotional_care）：用户表达不适、疲劳、情绪低落等，需要安慰与建议。
- 日常聊天（chat）：用户仅为寒暄、闲聊、表达心情，无需任何设备操作或知识检索。

隐式意图决策原则（动态判断）：
- 身体不适、冷热、睡觉、出门、天黑、吵闹等场景不要套用固定操作模板。
- 必须结合下方“当前家庭状态”中的时间、季节、天气、家庭实际设备与当前状态，自主判断最合适的设备和参数。
- 只输出家庭中真实存在的设备类型，房间名必须与家庭实际房间一致；信息不足时降低明确度并生成澄清问题。

意图明确度评分（intent_clarity_score，0-1）：
- >=0.8：非常明确，直接执行
- 0.6-0.8：较明确，可执行但可能需审批
- <0.6：不明确，需要中断询问（生成 clarification_question）
- 若未指定房间但家庭中该设备在多个房间存在，或未指定参数值，应降低评分并生成澄清问题。

家庭设备上下文：
{device_context}

RAG 知识上下文：
{rag_context}

当前家庭状态：
{house_status}

输出 JSON 格式（严格）：
{{
  "intents": [
    {{
      "type": "device_control",
      "description": "调整卧室空调温度",
      "clarity": 0.9,
      "room_name": "卧室",
      "device_type": "air_conditioner",
      "attributes": {{"temperature": 27, "power": "on"}},
      "scene_name": null
    }}
  ],
  "intent_clarity_score": 0.9,
  "needs_clarification": false,
  "clarification_question": "",
  "clarification_options": []
}}
"""


async def _load_family_context(family_id: int):
    """查询家庭房间与设备，供意图识别与澄清选项使用。"""
    from app.services.device_service import list_devices_by_family
    from app.services.room_service import list_rooms_by_family

    rooms = await list_rooms_by_family(family_id)
    devices = await list_devices_by_family(family_id)
    room_map = {room.id: room.name for room in rooms}
    device_context = [
        {"room_name": room_map.get(device.room_id, ""), "type": device.type}
        for device in devices
    ]
    return rooms, device_context


def _normalize_intents(data: dict) -> list:
    """清洗 LLM 输出的意图列表。"""
    intents = []
    for raw in data.get("intents") or []:
        if not isinstance(raw, dict):
            continue
        intent_type = raw.get("type")
        if intent_type not in INTENT_TYPES:
            continue
        intent = {
            "type": intent_type,
            "description": raw.get("description", ""),
            "clarity": float(raw.get("clarity", 0.9)),
        }
        if raw.get("room_name"):
            intent["room_name"] = str(raw["room_name"])
        if raw.get("device_type"):
            intent["device_type"] = str(raw["device_type"])
        if isinstance(raw.get("attributes"), dict):
            intent["attributes"] = raw["attributes"]
        if raw.get("scene_name"):
            intent["scene_name"] = str(raw["scene_name"])
        intents.append(intent)
    return intents


@log_node_run
async def intent_recognition_node(state: dict) -> dict:
    """调用 LLM 识别意图；输出异常时回退规则引擎。

    纯闲聊（寒暄/情感陪伴）走快速路径，不查询数据库、不加载设备上下文。
    """
    state = dict(state)
    user_input = state.get("user_input", "")
    # 澄清回答与原输入合并后重新识别意图（设计文档 3.3.3）
    effective_input = f"{user_input} {state.get('user_clarification', '')}".strip()
    permission_mode = state.get("permission_mode", "normal")

    # 纯闲聊快速路径：无需设备/房间/知识库上下文，直接进入聊天链路
    if looks_like_pure_chat(effective_input):
        state["intents"] = [
            {"type": "chat", "description": "日常聊天或情感陪伴", "clarity": 1.0}
        ]
        state["intent_clarity_score"] = 1.0
        state["needs_clarification"] = False
        state["clarification_question"] = ""
        state["clarification_options"] = []
        state["clarify_source"] = "intent"
        state["active_chains"] = compute_active_chains(state["intents"])
        return state

    rooms, device_context = await _load_family_context(state["family_id"])

    system = INTENT_PROMPT.format(
        device_context=(
            json.dumps(device_context, ensure_ascii=False)
            if device_context
            else "（暂无设备）"
        ),
        rag_context=state.get("rag_context") or "（此阶段不预检索，按需处理）",
        house_status=build_house_status_text(state.get("house_status") or {}),
    )

    parsed = None
    try:
        client = get_llm_client()
        response = await client.chat(
            messages=build_llm_messages(state, state.get("user_clarification", "")),
            system=system,
            temperature=0.2,
            max_tokens=1200,
        )
        parsed = extract_json(response.content)
    except Exception as exc:  # LLM 异常不影响主流程
        logger.warning("意图识别 LLM 调用异常: %s", exc)

    if parsed and parsed.get("intents"):
        intents = _normalize_intents(parsed)
        score = float(parsed.get("intent_clarity_score", 0.9))
        question = str(parsed.get("clarification_question") or "")
        options = [
            str(item)
            for item in (parsed.get("clarification_options") or [])
            if str(item).strip()
        ]
    else:
        rule_result = build_rule_intents(
            effective_input,
            state.get("rag_context") or "",
            [room.name for room in rooms],
            device_context,
            season=(state.get("house_status") or {}).get("season", ""),
        )
        intents = rule_result.get("intents") or []
        score = float(rule_result.get("intent_clarity_score", 1.0))
        question = str(rule_result.get("clarification_question") or "")
        options = rule_result.get("clarification_options") or []

    threshold = 0.4 if permission_mode == "high" else 0.6
    needs_clarification = score < threshold
    if needs_clarification and not question:
        question = "您的指令还不够明确，请补充一下：您想调整哪个房间、哪个设备，以及具体要做什么？"

    state["intents"] = intents
    state["intent_clarity_score"] = score
    state["needs_clarification"] = needs_clarification
    state["clarification_question"] = question
    state["clarification_options"] = options
    state["clarify_source"] = "intent"
    state["active_chains"] = compute_active_chains(intents)
    return state
