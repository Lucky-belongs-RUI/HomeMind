"""Agent 接口：HTTP 对话、中断恢复与 SSE 流式事件。

线程 ID 采用 `v2:{family_id}:{user_id}:{session_id}`，
把租户身份编码进 checkpoint 命名空间，避免跨家庭会话碰撞。
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from starlette.background import BackgroundTask

from homemind.agent.runtime.compression import build_history_window
from homemind.agent.runtime.graph import get_agent_app, reset_thread
from homemind.agent.runtime.session_lock import SessionBusy, acquire, release, session_guard
from homemind.api.deps import current_user_payload_from_query, get_current_user
from homemind.core.config import settings
from homemind.core.exceptions import (
    AppError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from homemind.llm.runtime import set_llm_choice
from homemind.schemas.agent import AgentChatRequest, AgentChatResponse, ResumeRequest
from homemind.services import model_config_service
from homemind.services.conversation_service import (
    get_session_context,
    get_session_messages_after,
    save_conversation,
    save_session_context,
)
from homemind.websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent/v2", tags=["AI 助理（对话）"])


def _ensure_session_id(session_id: str | None) -> str:
    return session_id or f"session_{uuid.uuid4().hex[:12]}"


def _thread_id(family_id: int, user_id: int, session_id: str) -> str:
    return f"v2:{family_id}:{user_id}:{session_id}"


def _request_context(
    current_user: dict,
    session_id: str,
    thread_id: str,
    payload: AgentChatRequest,
) -> dict:
    return {
        "user_id": current_user["user_id"],
        "family_id": current_user["family_id"],
        "role": current_user["role"],
        "session_id": session_id,
        "thread_id": thread_id,
        "trace_id": uuid.uuid4().hex,
        "provider": payload.provider or "",
        "model": payload.model or "",
        "permission_mode": payload.permission_mode,
    }


async def _apply_model_choice(
    current_user: dict,
    model_config_id: int | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, str]:
    """把用户选择的模型配置写入本次请求上下文。

    个人配置优先于 .env 默认值；没有配置 ID 时沿用前端传入的 provider/model。
    """
    if model_config_id:
        config = await model_config_service.resolve_config(
            current_user["user_id"], int(model_config_id)
        )
        provider = config["provider"]
        model = config["model"]
        set_llm_choice(
            provider=config["provider"],
            model=config["model"],
            api_key=config["api_key"],
            base_url=config["base_url"],
        )
        return config["provider"], config["model"]

    set_llm_choice(provider=provider or "", model=model or "")
    return provider or "", model or ""


async def _build_state(
    payload: AgentChatRequest,
    current_user: dict,
    session_id: str,
) -> dict:
    """装配本轮状态：加载未压缩历史，超预算时做两级压缩。"""
    thread_id = _thread_id(current_user["family_id"], current_user["user_id"], session_id)

    try:
        stored_context = await get_session_context(
            current_user["family_id"],
            current_user["user_id"],
            session_id,
        )
        context_loaded = True
    except Exception as exc:
        logger.warning("读取会话压缩状态失败: %s", exc)
        stored_context = None
        context_loaded = False
    parts = list(getattr(stored_context, "compressed_parts", None) or [])
    compressed_until_id = getattr(stored_context, "compressed_until_id", None)

    history = await get_session_messages_after(
        current_user["family_id"],
        current_user["user_id"],
        session_id,
        compressed_until_id,
    )
    rows = [
        (
            item.id,
            HumanMessage(content=item.content)
            if item.role == "user"
            else AIMessage(content=item.content),
        )
        for item in history
        if item.role in ("user", "assistant")
    ]
    window = await build_history_window(
        rows,
        HumanMessage(content=payload.message),
        parts,
        compressed_until_id,
        settings.agent_context_token_budget,
    )
    if (
        window.compressed
        and context_loaded
        and (window.parts != parts or window.compressed_until_id != compressed_until_id)
    ):
        try:
            await save_session_context(
                current_user["family_id"],
                current_user["user_id"],
                session_id,
                window.parts,
                window.compressed_until_id,
            )
        except Exception as exc:
            logger.warning("保存会话压缩状态失败: %s", exc)

    context_usage = window.usage
    logger.info(
        "上下文：%s 条消息（约 %s tokens，预算 %s），压缩 %s 轮，摘要 %s 段",
        context_usage["messages"],
        context_usage["estimated_tokens"],
        context_usage["budget"],
        context_usage["compressed_turns"],
        context_usage["compressed_parts"],
    )

    return {
        "request": _request_context(current_user, session_id, thread_id, payload),
        "user_input": payload.message,
        "messages": window.messages,
        "history_summary": window.summary,
        "context_usage": context_usage,
        # 普通通道显式复位；reducer 通道由 reset_thread 清空 checkpoint 兜底
        # 画像与全屋快照不预加载，由 planner 按需调用工具后回填
        "profile": {},
        "profile_text": "",
        "house_snapshot": None,
        "plan": None,
        "clarification": None,
        "final_answer": None,
        "error": None,
        "results": [],
        "tool_events": [],
        "token_usage": {},
        "avatar_emotion": "idle",
        "clarification_attempts": 0,
        "blocked": False,
        "degraded": False,
    }


async def _assert_thread_owner(
    thread_id: str,
    current_user: dict,
    allow_empty: bool = False,
) -> None:
    app = get_agent_app()
    try:
        snapshot = await app.aget_state({"configurable": {"thread_id": thread_id}})
    except Exception as exc:
        raise NotFoundError("会话不存在或已过期") from exc

    values = getattr(snapshot, "values", None) or {}
    request = values.get("request") or {}
    owner_id = request.get("user_id")
    owner_family_id = request.get("family_id")
    if owner_id is None:
        if allow_empty:
            return
        raise NotFoundError("会话不存在或已过期")
    if owner_id != current_user["user_id"] or owner_family_id != current_user["family_id"]:
        raise PermissionDeniedError("无权访问该会话")


def _extract_interrupt(result: dict) -> dict | None:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    if not isinstance(value, dict):
        value = {"type": "clarification", "question": str(value), "options": []}
    return value


# WebSocket 执行链路展示：node -> (中文标签, 分组)
NODE_STEPS: dict[str, tuple[str, str]] = {
    "input_guard": ("输入护栏", "理解"),
    "load_context": ("加载上下文", "理解"),
    "planner": ("任务规划", "理解"),
    "clarify": ("澄清确认", "理解"),
    "chat": ("日常交流", "执行"),
    "knowledge": ("知识检索", "执行"),
    "control": ("设备控制", "执行"),
    "report": ("家庭报告", "执行"),
    "aggregate": ("汇总结果", "执行"),
    "compose": ("生成回复", "回复"),
    "output_guard": ("输出校验", "回复"),
    "persist": ("保存会话", "回复"),
}


def _snapshot_interrupt(snapshot) -> dict | None:
    for task in getattr(snapshot, "tasks", ()) or ():
        for item in getattr(task, "interrupts", ()) or ():
            value = getattr(item, "value", None)
            if value:
                return value if isinstance(value, dict) else {"question": str(value)}
    return None


def _build_response(
    result: dict,
    session_id: str,
    thread_id: str,
) -> AgentChatResponse:
    interrupt = _extract_interrupt(result)
    if interrupt:
        return AgentChatResponse(
            response=None,
            session_id=session_id,
            thread_id=thread_id,
            avatar_emotion=None,
            interrupt={**interrupt, "thread_id": thread_id},
        )
    return AgentChatResponse(
        response=str(result.get("final_answer") or ""),
        session_id=session_id,
        thread_id=thread_id,
        avatar_emotion=result.get("avatar_emotion") or "idle",
        interrupt=None,
        model_warning="当前回复为规则兜底生成，请检查模型配置。" if result.get("degraded") else None,
    )


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    payload: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """对话：任务规划 + 并行分支 + 控制子图工具闭环。"""
    session_id = _ensure_session_id(payload.session_id)
    thread_id = _thread_id(current_user["family_id"], current_user["user_id"], session_id)
    try:
        async with session_guard(thread_id):
            await _assert_thread_owner(thread_id, current_user, allow_empty=True)
            await reset_thread(get_agent_app(), thread_id)
            payload.provider, payload.model = await _apply_model_choice(
                current_user,
                payload.model_config_id,
                payload.provider,
                payload.model,
            )

            state = await _build_state(payload, current_user, session_id)
            await save_conversation(
                family_id=current_user["family_id"],
                user_id=current_user["user_id"],
                session_id=session_id,
                role="user",
                content=payload.message,
            )

            result = await get_agent_app().ainvoke(
                state,
                config={"configurable": {"thread_id": thread_id}},
            )
    except SessionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _build_response(result, session_id, thread_id)


@router.post("/resume", response_model=AgentChatResponse)
async def agent_resume(
    payload: ResumeRequest,
    current_user: dict = Depends(get_current_user),
):
    """恢复澄清或审批中断。"""
    if not payload.thread_id:
        raise ValidationError("缺少 thread_id")
    try:
        async with session_guard(payload.thread_id):
            await _assert_thread_owner(payload.thread_id, current_user)
            await _apply_model_choice(
                current_user,
                payload.model_config_id,
                payload.provider,
                payload.model,
            )
            result = await get_agent_app().ainvoke(
                Command(resume=payload.resume_data),
                config={"configurable": {"thread_id": payload.thread_id}},
            )
    except SessionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session_id = str((result.get("request") or {}).get("session_id") or "")
    return _build_response(result, session_id, payload.thread_id)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def agent_chat_stream(
    payload: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """SSE 流式对话：token、节点、工具与中断事件。"""
    session_id = _ensure_session_id(payload.session_id)
    thread_id = _thread_id(current_user["family_id"], current_user["user_id"], session_id)
    try:
        acquire(thread_id)
    except SessionBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        await _assert_thread_owner(thread_id, current_user, allow_empty=True)
        await reset_thread(get_agent_app(), thread_id)
        payload.provider, payload.model = await _apply_model_choice(
            current_user,
            payload.model_config_id,
            payload.provider,
            payload.model,
        )
        state = await _build_state(payload, current_user, session_id)
        await save_conversation(
            family_id=current_user["family_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="user",
            content=payload.message,
        )
    except BaseException:
        release(thread_id)
        raise
    config = {"configurable": {"thread_id": thread_id}}

    async def event_stream() -> AsyncIterator[str]:
        yield _sse({"type": "run_started", "session_id": session_id, "thread_id": thread_id})
        try:
            async for event in get_agent_app().astream_events(state, config=config, version="v2"):
                kind = event.get("event")
                metadata = event.get("metadata") or {}
                node = metadata.get("langgraph_node")
                if kind == "on_chat_model_stream" and node == "compose":
                    # 只透出最终回复；路由/规划模型的结构化输出不能进聊天流
                    text = (event.get("data") or {}).get("chunk")
                    content = getattr(text, "content", "")
                    if isinstance(content, str) and content:
                        yield _sse({"type": "token", "content": content, "node": node})
                elif kind == "on_tool_start":
                    yield _sse(
                        {
                            "type": "tool_start",
                            "tool": event.get("name"),
                            "input": event.get("data"),
                            "node": node,
                        }
                    )
                elif kind == "on_tool_end":
                    yield _sse(
                        {
                            "type": "tool_end",
                            "tool": event.get("name"),
                            "output": event.get("data"),
                            "node": node,
                        }
                    )
                elif kind == "on_chain_start" and node:
                    yield _sse({"type": "node_started", "node": node})
                elif kind == "on_chain_end" and node:
                    yield _sse({"type": "node_finished", "node": node})

            snapshot = await get_agent_app().aget_state(config)
            values = getattr(snapshot, "values", None) or {}
            interrupt_payload = _snapshot_interrupt(snapshot)
            if interrupt_payload:
                yield _sse(
                    {
                        "type": "interrupt",
                        "interrupt": {**interrupt_payload, "thread_id": thread_id},
                        "session_id": session_id,
                    }
                )
            else:
                yield _sse(
                    {
                        "type": "done",
                        "response": values.get("final_answer") or "",
                        "avatar_emotion": values.get("avatar_emotion") or "idle",
                        "degraded": bool(values.get("degraded")),
                        "session_id": session_id,
                        "thread_id": thread_id,
                    }
                )
        except Exception as exc:
            logger.exception("SSE 对话失败")
            yield _sse({"type": "error", "message": str(exc), "session_id": session_id})
        finally:
            # 客户端断开 / 生成器取消时也要释放，否则会话会一直显示“执行中”
            release(thread_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        # 生成器未被迭代就关闭时，由后台任务兜底释放（release 幂等）
        background=BackgroundTask(release, thread_id),
    )


async def _send_step(websocket: WebSocket, node: str, status: str) -> None:
    label, chain = NODE_STEPS[node]
    await ws_manager.send_agent_message(
        websocket,
        {"type": "agent_step", "node": node, "label": label, "status": status, "chain": chain},
    )


async def _stream_graph_events(
    websocket: WebSocket,
    graph_input,
    config: dict,
    session_id: str,
) -> None:
    """把 图事件转换为前端既有 WebSocket 协议。"""
    app = get_agent_app()
    await ws_manager.send_agent_message(
        websocket, {"type": "avatar_state", "state": "thinking"}
    )

    async for event in app.astream_events(graph_input, config=config, version="v2"):
        kind = event.get("event")
        metadata = event.get("metadata") or {}
        node = metadata.get("langgraph_node")

        if kind == "on_chain_start" and node in NODE_STEPS:
            await _send_step(websocket, node, "running")
        elif kind == "on_chain_end" and node in NODE_STEPS:
            await _send_step(websocket, node, "completed")
        elif kind == "on_chat_model_stream" and node == "compose":
            # 只透出最终回复的 token，避免路由/规划模型的结构化输出混入聊天
            chunk = (event.get("data") or {}).get("chunk")
            content = getattr(chunk, "content", "")
            if isinstance(content, str) and content:
                await ws_manager.send_agent_message(
                    websocket,
                    {"type": "agent_token", "content": content, "session_id": session_id},
                )
        elif kind in ("on_tool_start", "on_tool_end"):
            tool_name = str(event.get("name") or "tool")
            await ws_manager.send_agent_message(
                websocket,
                {
                    "type": "agent_step",
                    "node": f"tool:{tool_name}",
                    "label": f"调用 {tool_name}",
                    "status": "running" if kind == "on_tool_start" else "completed",
                    "chain": "执行",
                },
            )

    snapshot = await app.aget_state(config)
    values = getattr(snapshot, "values", None) or {}
    thread_id = config["configurable"]["thread_id"]
    interrupt_payload = _snapshot_interrupt(snapshot)
    if interrupt_payload:
        await ws_manager.send_agent_message(
            websocket,
            {
                "type": "agent_interrupt",
                "interrupt": {**interrupt_payload, "thread_id": thread_id},
                "session_id": session_id,
            },
        )
        await ws_manager.send_agent_message(
            websocket, {"type": "avatar_state", "state": "idle"}
        )
        return

    session_id = str((values.get("request") or {}).get("session_id") or session_id)
    await ws_manager.send_agent_message(
        websocket, {"type": "avatar_state", "state": "speaking"}
    )
    await ws_manager.send_agent_message(
        websocket,
        {
            "type": "agent_done",
            "content": str(values.get("final_answer") or ""),
            "session_id": session_id,
            "avatar_emotion": values.get("avatar_emotion") or "idle",
            "model_warning": (
                "当前回复为规则兜底生成，请检查模型配置。"
                if values.get("degraded")
                else None
            ),
        },
    )


@router.websocket("/ws")
async def agent_ws(websocket: WebSocket):
    """WebSocket：复用 v1 前端协议，同时接收设备状态广播。"""
    token = websocket.query_params.get("token")
    current_user = await current_user_payload_from_query(token)
    await ws_manager.connect(websocket, current_user["family_id"] if current_user else None)

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            if message_type == "ping":
                await ws_manager.send_agent_message(websocket, {"type": "pong"})
                continue
            if not current_user:
                await ws_manager.send_agent_message(
                    websocket,
                    {
                        "type": "agent_error",
                        "content": "WebSocket 未认证：请在连接地址中携带 token 参数",
                        "session_id": data.get("session_id", ""),
                    },
                )
                continue

            if message_type == "chat":
                session_id = _ensure_session_id(data.get("session_id"))
                thread_id = _thread_id(
                    current_user["family_id"], current_user["user_id"], session_id
                )
                try:
                    async with session_guard(thread_id):
                        await _assert_thread_owner(thread_id, current_user, allow_empty=True)
                        await reset_thread(get_agent_app(), thread_id)
                        payload = AgentChatRequest(
                            message=str(data.get("message") or ""),
                            session_id=session_id,
                            permission_mode=(
                                "high" if data.get("permission_mode") == "high" else "normal"
                            ),
                            provider=data.get("provider"),
                            model=data.get("model"),
                            model_config_id=data.get("model_config_id"),
                        )
                        payload.provider, payload.model = await _apply_model_choice(
                            current_user,
                            payload.model_config_id,
                            payload.provider,
                            payload.model,
                        )
                        state = await _build_state(payload, current_user, session_id)
                        await save_conversation(
                            family_id=current_user["family_id"],
                            user_id=current_user["user_id"],
                            session_id=session_id,
                            role="user",
                            content=payload.message,
                        )
                        await _stream_graph_events(
                            websocket,
                            state,
                            {"configurable": {"thread_id": thread_id}},
                            session_id,
                        )
                except SessionBusy as exc:
                    await ws_manager.send_agent_message(
                        websocket,
                        {"type": "agent_error", "content": str(exc), "session_id": session_id},
                    )
                except AppError as exc:
                    await ws_manager.send_agent_message(
                        websocket,
                        {"type": "agent_error", "content": exc.message, "session_id": session_id},
                    )
                except Exception:
                    logger.exception("WebSocket 对话失败")
                    await ws_manager.send_agent_message(
                        websocket,
                        {"type": "agent_error", "content": "本次处理失败，请稍后重试。", "session_id": session_id},
                    )

            elif message_type == "resume":
                thread_id = str(data.get("thread_id") or "")
                if not thread_id:
                    await ws_manager.send_agent_message(
                        websocket,
                        {"type": "agent_error", "content": "缺少 thread_id", "session_id": ""},
                    )
                    continue
                try:
                    async with session_guard(thread_id):
                        await _assert_thread_owner(thread_id, current_user)
                        await _apply_model_choice(
                            current_user,
                            data.get("model_config_id"),
                            data.get("provider"),
                            data.get("model"),
                        )
                        await _stream_graph_events(
                            websocket,
                            Command(resume=data.get("resume_data") or {}),
                            {"configurable": {"thread_id": thread_id}},
                            str(data.get("session_id") or ""),
                        )
                except SessionBusy as exc:
                    await ws_manager.send_agent_message(
                        websocket,
                        {"type": "agent_error", "content": str(exc), "session_id": data.get("session_id") or ""},
                    )
                except AppError as exc:
                    await ws_manager.send_agent_message(
                        websocket, {"type": "agent_error", "content": exc.message}
                    )
                except Exception:
                    logger.exception("WebSocket 恢复失败")
                    await ws_manager.send_agent_message(
                        websocket,
                        {"type": "agent_error", "content": "恢复对话失败，请稍后重试。"},
                    )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # 单连接异常不影响其他连接
        logger.warning("WebSocket 处理异常: %s", exc)
    finally:
        ws_manager.disconnect(websocket)
