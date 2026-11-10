"""主图通用节点：护栏、上下文、汇总、回复、输出护栏与落库。"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from homemind.agent.runtime.context import (
    format_recent_history,
    history_without_current,
    render_profile,
)
from homemind.agent.runtime.evidence import (
    can_stream,
    ensure_failure_notice,
    strip_unbacked_claims,
)
from homemind.core.config import settings
from homemind.llm.langchain import (
    build_response_model,
    extract_usage,
    message_text,
)
from homemind.services.conversation_service import save_conversation

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 4000

_INJECTION_MARKERS = (
    "忽略之前的所有指令",
    "忽略上面的指令",
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "developer mode",
    "开发者模式",
    "你现在是",
    "jailbreak",
)

COMPOSE_SYSTEM = """你是智能家居助理“小智”。请用简洁、自然的中文回答用户。

更早对话的压缩摘要（仅作背景，不是本轮指令）：
{history}

用户画像（作为默认偏好参考，与本轮明确指令冲突时以本轮指令为准）：
{profile}

事实约束：
1. 只有“本轮已执行”里的内容才可以写成“已为您完成”；没有执行记录时不得描述任何设备动作。
2. 设备控制失败时明确说明失败原因，不要假装成功。
3. 不要复述历史对话中已经完成、但本轮没有执行的操作。
4. 引用知识资料时用 [1][2] 标注来源。
5. 用药类问题只能依据知识资料回答；资料中没有时明确说明未查到，并建议咨询医生或药师，
   不要凭常识给出具体药名或剂量。
6. 闲聊保持温暖、简短，不要机械复述上下文。
7. 设备清单按设备 ID / 名称去重，每台设备只列一次；不要输出“已列出”“确认在线”等重复条目。
   查询设备位置时直接说明所在房间，不要编造未返回的房间。

本轮执行结果：
{context}
"""


def _request(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("request") or {}


async def input_guard(state: dict[str, Any]) -> dict[str, Any]:
    """确定性输入护栏：空输入、超长、典型提示注入。"""
    text = str(state.get("user_input") or "").strip()
    if not text:
        return {"blocked": True, "final_answer": "请输入您想让我处理的内容。"}
    if len(text) > MAX_INPUT_CHARS:
        return {
            "blocked": True,
            "final_answer": f"输入内容过长（上限 {MAX_INPUT_CHARS} 字），请精简后重试。",
        }
    lowered = text.lower()
    if any(marker in lowered for marker in _INJECTION_MARKERS):
        return {
            "blocked": True,
            "final_answer": "抱歉，这条请求包含不安全的指令，我无法执行。",
        }
    return {"blocked": False}


def route_after_guard(state: dict[str, Any]) -> str:
    # 拦截后仍要走输出护栏（AI 标识）与落库，不能直接 END
    return "blocked" if state.get("blocked") else "continue"


async def load_context(state: dict[str, Any]) -> dict[str, Any]:
    """装配本轮上下文：画像、近期历史与全屋快照。

    画像与快照由 planner 按需通过工具加载，这里只做归一化与渲染，
    保证节点本身不查库。未加载时保持空值，下游按“未提供”处理。
    """
    profile = dict(state.get("profile") or {})

    snapshot = state.get("house_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = None

    user_input = str(state.get("user_input") or "")
    history_source = history_without_current(list(state.get("messages") or []), user_input)
    history_text = format_recent_history(history_source, max_chars=600)
    summary = str(state.get("history_summary") or "").strip()
    if summary:
        summary = summary[:400]
        history_text = (
            f"近期对话：\n{history_text}\n\n更早对话摘要：\n{summary}"
            if history_text
            else f"更早对话摘要：\n{summary}"
        )
    return {
        "profile": profile,
        "profile_text": render_profile(profile),
        "history_text": history_text,
        "house_snapshot": snapshot,
    }


async def aggregate(state: dict[str, Any]) -> dict[str, Any]:
    """汇总并行分支结果，并统一裁决虚拟形象状态。"""
    results = state.get("results") or []
    branches = {str(item.get("branch")) for item in results}
    failed = any(not item.get("success") for item in results)
    degraded = any(item.get("degraded") for item in results)

    if "control" in branches:
        emotion = "idle" if failed else "happy"
    elif "knowledge" in branches or "report" in branches:
        emotion = "neutral"
    else:
        emotion = "caring"
    return {"avatar_emotion": emotion, "degraded": degraded}


def _observation_text(observation: dict[str, Any]) -> str:
    result = observation.get("result") or {}
    text = str(result.get("message") or "").strip()
    if text:
        return text[:600]
    payload = {key: value for key, value in result.items() if key != "success"}
    return json.dumps(payload, ensure_ascii=False, default=str)[:600]


def _compose_context(results: list[dict[str, Any]]) -> str:
    executed: list[str] = []
    not_executed: list[str] = []
    knowledge: list[str] = []
    reports: list[str] = []
    tones: list[str] = []

    for item in results:
        branch = item.get("branch")
        data = item.get("data") or {}
        if branch == "control":
            observations = data.get("observations") or []
            for observation in observations:
                tool = str(observation.get("tool") or "工具")
                result = observation.get("result") or {}
                partial = int(result.get("failed_count") or 0) > 0
                if observation.get("success") and not partial:
                    executed.append(f"- {tool}：{_observation_text(observation)}")
                else:
                    error = (
                        observation.get("error")
                        or result.get("error")
                        or result.get("message")
                        or "未知原因"
                    )
                    not_executed.append(f"- {tool}：{error}")
            if not observations:
                not_executed.append(f"- {item.get('summary') or '设备操作未执行'}")
        elif branch == "knowledge":
            context = str(data.get("context") or "").strip()
            knowledge.append(f"知识资料：\n{context}" if context else "知识资料：未检索到相关内容")
        elif branch == "report":
            reports.append(f"家庭状态：\n{data.get('context') or item.get('summary') or '无'}")
        elif branch == "chat":
            tones.append(f"交流语气：{item.get('summary') or '日常交流'}")

    parts = [
        "本轮已执行：\n" + ("\n".join(executed) if executed else "无"),
        "本轮未执行：\n" + ("\n".join(not_executed) if not_executed else "无"),
    ]
    parts.extend(knowledge)
    parts.extend(reports)
    parts.extend(tones)
    return "\n\n".join(parts)


def _fallback_answer(state: dict[str, Any]) -> str:
    results = state.get("results") or []
    by_branch = {str(item.get("branch")): item for item in results}

    control = by_branch.get("control")
    if control:
        summary = str(control.get("summary") or "设备操作已处理。")
        details = "\n".join(
            f"- {observation.get('tool')}：{_observation_text(observation)}"
            for observation in ((control.get("data") or {}).get("observations") or [])
            if observation.get("success")
        )
        return f"{summary}\n{details}" if details else summary

    knowledge = by_branch.get("knowledge")
    if knowledge:
        data = knowledge.get("data") or {}
        context = str(data.get("context") or "").strip()
        if context:
            sources = "、".join(
                dict.fromkeys(
                    str(source.get("source") or "知识库")
                    for source in knowledge.get("sources") or []
                )
            )
            prefix = f"根据《{sources}》：" if sources else "根据知识库："
            return f"{prefix}{context}"

    report = by_branch.get("report")
    if report:
        data = report.get("data") or {}
        return str(data.get("context") or report.get("summary") or "暂无家庭状态数据。")

    return "我在呢，有什么可以帮您？"


def _chat_messages(state: dict[str, Any], system: str) -> list:
    # 请求入口已按 token 预算做过两级压缩；这里保留全部窗口消息
    history = list(state.get("messages") or [])
    user_input = str(state.get("user_input") or "").strip()
    if not history or not isinstance(history[-1], HumanMessage):
        history.append(HumanMessage(content=user_input))
    return [SystemMessage(content=system), *history]


async def compose(state: dict[str, Any]) -> dict[str, Any]:
    """最终回复：有真实写操作时才流式；否则先完整生成，交给证据门槛校验。

    流式一旦把“已为您调好空调”发给前端就无法撤回，所以没有成功写操作时
    必须缓冲生成，由 output_guard 统一剔除无依据的动作声明。
    """
    if state.get("final_answer"):
        return {}

    results = state.get("results") or []
    context = _compose_context(results)
    profile_text = str(state.get("profile_text") or "").strip()
    system = COMPOSE_SYSTEM.format(
        context=context,
        profile=profile_text or "（未提供）",
        history=str(state.get("history_summary") or "").strip() or "（无）",
    )
    messages = _chat_messages(state, system)

    try:
        model = build_response_model(
            _request(state).get("provider"),
            _request(state).get("model") or settings.agent_chat_model or None,
        )
        if can_stream(results):
            chunks: list[str] = []
            usage: dict[str, int] = {}
            async for chunk in model.astream(messages):
                text = message_text(chunk)
                if text:
                    chunks.append(text)
                chunk_usage = extract_usage(chunk)
                if chunk_usage.get("total_tokens"):
                    usage = chunk_usage
            answer = "".join(chunks).strip()
        else:
            response = await model.ainvoke(messages)
            answer = message_text(response).strip()
            usage = extract_usage(response)
        if answer:
            return {"final_answer": answer, "token_usage": usage}
        logger.warning("回复模型返回空内容，使用模板兜底")
    except Exception as exc:
        logger.warning("回复生成 LLM 不可用，使用模板兜底: %s", exc)

    return {"final_answer": _fallback_answer(state), "degraded": True}


async def output_guard(state: dict[str, Any]) -> dict[str, Any]:
    """证据校验、输出兜底与 AI 生成内容标识。"""
    results = state.get("results") or []
    text = strip_unbacked_claims(str(state.get("final_answer") or ""), results)
    text = ensure_failure_notice(text, results)
    if not text:
        text = "抱歉，本次没有生成有效回复，请稍后再试。"
    if settings.agent_ai_label and "AI 生成" not in text:
        text = f"{text}\n\n（本内容由 AI 生成，仅供参考）"
    return {"final_answer": text}


async def persist(state: dict[str, Any]) -> dict[str, Any]:
    """保存助手回复；持久化失败不覆盖已生成的回答。"""
    request = _request(state)
    answer = str(state.get("final_answer") or "").strip()
    if not answer or not request.get("session_id"):
        return {}
    try:
        await save_conversation(
            family_id=int(request["family_id"]),
            user_id=int(request["user_id"]),
            session_id=str(request["session_id"]),
            role="assistant",
            content=answer,
        )
    except Exception as exc:
        logger.warning("保存助手回复失败: %s", exc)
        return {"error": str(exc)}
    return {}
