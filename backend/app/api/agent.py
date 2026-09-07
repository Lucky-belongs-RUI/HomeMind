"""Agent 接口：九节点对话（HTTP/WebSocket）、中断恢复、语音识别与语音合成。"""
import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.agent.nodes.house_status import generate_opening_message
from app.api.deps import current_user_payload_from_query, get_current_user
from app.config import settings
from app.llm.factory import set_llm_choice
from app.schemas.agent import (
    AgentChatRequest,
    OpeningRequest,
    ResetChatRequest,
    ResumeRequest,
    TTSRequest,
)
from app.services import environment_service
from app.services.conversation_service import (
    delete_session_conversations,
    get_session_conversations,
    save_conversation,
)
from app.voice.stt import speech_to_text
from app.voice.tts import text_to_speech
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["AI 助理"])

# 轻量执行器的中断恢复存储（仅未安装 LangGraph 时使用）
_resume_store: dict = {}


def _ensure_session_id(session_id: str | None) -> str:
    return session_id or f"session_{uuid.uuid4().hex[:12]}"


def _build_initial_state(
    user_input: str,
    current_user: dict,
    session_id: str,
    permission_mode: str = "normal",
    history: list | None = None,
    house_status: dict | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """构造 AgentState 初始值，thread_id 由会话派生用于中断恢复。

    house_status 默认不预查询：仅设备控制/报告链路需要时由节点懒加载，
    满足"并非所有任务都需要检索数据库"的架构要求。
    """
    history = history or []
    house_status = house_status or {}
    return {
        "user_input": user_input,
        "user_id": current_user["user_id"],
        "user_role": current_user["role"],
        "family_id": current_user["family_id"],
        "session_id": session_id,
        "permission_mode": permission_mode if permission_mode in ("high", "normal") else "normal",
        "thread_id": f"thread_{session_id}",
        "provider": provider or settings.llm_provider,
        "model": model or "",
        "house_status": house_status,
        "messages": [
            *[{"role": item["role"], "content": item["content"]} for item in history],
            {"role": "user", "content": user_input},
        ],
        "rag_context": None,
        "rag_sources": [],
        "is_knowledge_query": False,
        "intents": [],
        "intent_clarity_score": 1.0,
        "needs_clarification": False,
        "clarification_question": "",
        "clarification_options": [],
        "clarification_attempts": 0,
        "clarify_source": "intent",
        "active_chains": [],
        "chain_results": {},
        "tasks": [],
        "needs_approval": False,
        "approval_granted": False,
        "approved_task_ids": [],
        "tool_results": [],
        "success_count": 0,
        "failure_count": 0,
        "skipped_count": 0,
        "final_response": None,
        "avatar_emotion": "idle",
        "iteration": 0,
    }


def _normalize_interrupt(result: dict) -> dict:
    """将 LangGraph 的 __interrupt__ 转为统一中断结构。"""
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return result
    first = interrupts[0]
    value = getattr(first, "value", first)
    if not isinstance(value, dict):
        value = {"type": "clarification", "question": str(value), "options": []}
    result["_interrupt"] = value
    result.pop("__interrupt__", None)
    return result


def _normalize_stream_interrupt(update) -> list:
    """从 LangGraph astream 的中断更新中提取统一 payload。"""
    raw_items = update if isinstance(update, (list, tuple)) else [update]
    values = []
    for item in raw_items:
        value = getattr(item, "value", item)
        if isinstance(value, dict):
            values.append(value)
        else:
            values.append({"type": "clarification", "question": str(value), "options": []})
    return values


def _make_node_event_sender(websocket: WebSocket, session_id: str):
    """构造节点流式事件发送器，统一补充会话 ID。"""
    async def send(event: dict):
        await ws_manager.send_agent_message(
            websocket,
            {**event, "session_id": session_id},
        )

    return send


async def _run_langgraph_stream(agent_app, graph_input, config: dict, on_event) -> dict:
    """以流式模式执行 LangGraph，并逐节点推送 agent_step 事件（含链路）。"""
    from app.agent.graph import NODE_CHAIN, NODE_LABELS

    final_state = {}
    interrupt_value = None
    async for chunk in agent_app.astream(graph_input, config=config, stream_mode="updates"):
        for node_name, update in chunk.items():
            if node_name == "__interrupt__":
                interrupt_value = update
                continue
            label = NODE_LABELS.get(node_name, node_name)
            if on_event is not None:
                await on_event(
                    {
                        "type": "agent_step",
                        "node": node_name,
                        "label": label,
                        "chain": NODE_CHAIN.get(node_name, "执行链路"),
                        "status": "running",
                    }
                )
            if isinstance(update, dict):
                final_state.update(update)
            if on_event is not None:
                await on_event(
                    {
                        "type": "agent_step",
                        "node": node_name,
                        "label": label,
                        "chain": NODE_CHAIN.get(node_name, "执行链路"),
                        "status": "completed",
                    }
                )
    if interrupt_value is not None:
        final_state["__interrupt__"] = _normalize_stream_interrupt(interrupt_value)
    return final_state


def _conversation_to_message(conv) -> dict:
    """将 Conversation ORM 记录转为 AgentState 消息字典。"""
    return {"role": conv.role, "content": conv.content}


def _resume_data_to_text(resume_data: dict) -> str:
    """把中断恢复数据转成可保存的用户消息文本。"""
    if not isinstance(resume_data, dict):
        return ""
    answer = resume_data.get("answer")
    if answer:
        return str(answer)
    if "approved" in resume_data:
        task_ids = resume_data.get("task_ids") or []
        if resume_data.get("approved"):
            return f"已确认执行任务（{len(task_ids)} 个）"
        return "已取消本次操作"
    return ""


async def _save_agent_result(
    family_id: int,
    user_id: int,
    final_state: dict,
    session_id: str,
):
    """统一保存 assistant 消息：正常回复或中断提问，供刷新后恢复。"""
    interrupt = final_state.get("_interrupt")
    content = ""
    if interrupt:
        content = interrupt.get("question") or ""
    else:
        content = final_state.get("final_response") or ""
    if content:
        await save_conversation(
            family_id=family_id,
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=content,
        )


async def _run_agent(state: dict, on_event=None) -> dict:
    """执行 Agent 状态图；LangGraph 使用 MemorySaver + thread_id。"""
    from app.agent.graph import HAS_LANGGRAPH, agent_app

    # 注入当前请求选用的模型（contextvar 传递，节点内 get_llm_client 读取）
    set_llm_choice(state.get("provider"), state.get("model"))

    if HAS_LANGGRAPH:
        config = {"configurable": {"thread_id": state["thread_id"]}}
        if on_event is None:
            result = await agent_app.ainvoke(state, config=config)
        else:
            result = await _run_langgraph_stream(agent_app, state, config, on_event)
        return _normalize_interrupt(result)

    result = await agent_app.ainvoke(state, on_node_event=on_event)
    if result.get("_interrupt"):
        # 保存轻量执行器的中断现场，供 resume 重放
        _resume_store[state["thread_id"]] = {
            key: value for key, value in result.items() if key != "_interrupt"
        }
    return result


async def _resume_agent(
    thread_id: str,
    resume_data: dict,
    on_event=None,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """恢复中断的 Agent 执行。"""
    from app.agent.graph import HAS_LANGGRAPH, agent_app

    # 恢复时同样注入模型选择，保证与初始请求一致
    set_llm_choice(provider or "", model or "")

    if HAS_LANGGRAPH:
        from langgraph.types import Command

        config = {"configurable": {"thread_id": thread_id}}
        if on_event is None:
            result = await agent_app.ainvoke(Command(resume=resume_data), config=config)
        else:
            result = await _run_langgraph_stream(
                agent_app,
                Command(resume=resume_data),
                config,
                on_event,
            )
        return _normalize_interrupt(result)

    snapshot = _resume_store.get(thread_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="中断会话不存在或已过期")
    state = dict(snapshot)
    state["_resume_data"] = resume_data
    state.pop("_interrupt", None)
    # 轻量执行器无状态快照时，用请求携带的模型选择兜底
    if provider or model:
        state["provider"] = provider or state.get("provider", "")
        state["model"] = model or state.get("model", "")
    set_llm_choice(state.get("provider"), state.get("model"))
    result = await agent_app.ainvoke(state, on_node_event=on_event)
    if result.get("_interrupt"):
        _resume_store[thread_id] = {
            key: value for key, value in result.items() if key != "_interrupt"
        }
    else:
        _resume_store.pop(thread_id, None)
    return result


def _build_chat_response(state: dict, session_id: str) -> dict:
    """统一响应：正常返回 final_response，中断返回 interrupt 信息。"""
    interrupt = state.get("_interrupt")
    thread_id = state.get("thread_id", "")
    if interrupt:
        return {
            "response": None,
            "session_id": session_id,
            "thread_id": thread_id,
            "avatar_emotion": None,
            "interrupt": {**interrupt, "thread_id": thread_id},
        }
    return {
        "response": state.get("final_response") or "",
        "session_id": session_id,
        "thread_id": thread_id,
        "avatar_emotion": state.get("avatar_emotion", "idle"),
        "interrupt": None,
    }


@router.post("/chat")
async def agent_chat(
    payload: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """文字对话：意图优先 + 多链路 Agent 闭环，支持权限模式与中断返回。

    不再预查全屋状态——仅设备控制/报告链路按需懒加载，降低非必要数据库检索。
    """
    session_id = _ensure_session_id(payload.session_id)
    history = await get_session_conversations(
        current_user["family_id"],
        current_user["user_id"],
        session_id,
        limit=10,
    )
    state = _build_initial_state(
        payload.message,
        current_user,
        session_id,
        payload.permission_mode,
        history=[_conversation_to_message(item) for item in history],
        house_status=None,
        provider=payload.provider,
        model=payload.model,
    )
    await save_conversation(
        family_id=current_user["family_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role="user",
        content=payload.message,
    )
    final_state = await _run_agent(state)
    await _save_agent_result(
        current_user["family_id"],
        current_user["user_id"],
        final_state,
        session_id,
    )
    return _build_chat_response(final_state, session_id)


@router.post("/resume")
async def agent_resume(
    payload: ResumeRequest,
    current_user: dict = Depends(get_current_user),
):
    """中断恢复：传入用户回答（clarification）或审批决策（approval）。"""
    final_state = await _resume_agent(
        payload.thread_id,
        payload.resume_data,
        provider=payload.provider,
        model=payload.model,
    )
    session_id = final_state.get("session_id") or ""
    resume_text = _resume_data_to_text(payload.resume_data)
    if resume_text:
        await save_conversation(
            family_id=current_user["family_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="user",
            content=resume_text,
        )
    await _save_agent_result(
        current_user["family_id"],
        current_user["user_id"],
        final_state,
        session_id,
    )
    return _build_chat_response(final_state, session_id)


@router.get("/environment")
async def agent_environment(current_user: dict = Depends(get_current_user)):
    """家庭中控指标：温度、湿度、空气质量、光照（AI 助理顶部展示）。"""
    return await environment_service.get_family_environment(current_user["family_id"])


@router.get("/history")
async def agent_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取会话历史，前端刷新后用于恢复聊天记录。"""
    session_id = _ensure_session_id(session_id)
    history = await get_session_conversations(
        current_user["family_id"],
        current_user["user_id"],
        session_id,
        limit=200,
    )
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": item.role,
                "content": item.content,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in history
        ],
    }


@router.post("/reset")
async def agent_reset_chat(
    payload: ResetChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """重置会话：删除该 session_id 的全部聊天记录。"""
    session_id = _ensure_session_id(payload.session_id)
    deleted = await delete_session_conversations(
        current_user["family_id"],
        current_user["user_id"],
        session_id,
    )
    return {"session_id": session_id, "deleted": deleted}


@router.post("/opening")
async def agent_opening(
    payload: OpeningRequest,
    current_user: dict = Depends(get_current_user),
):
    """首次进入聊天界面：全屋状态节点生成动态开场白并保存为会话首条消息。"""
    session_id = _ensure_session_id(payload.session_id)
    existing = await get_session_conversations(
        current_user["family_id"],
        current_user["user_id"],
        session_id,
        limit=1,
    )
    if existing:
        return {"session_id": session_id, "opening": None}

    from app.services.user_service import get_user

    user = await get_user(current_user["user_id"], current_user["family_id"])
    nickname = (
        (user.nickname if user else "")
        or current_user.get("username")
        or f"用户{current_user['user_id']}"
    )
    opening = await generate_opening_message(current_user["family_id"], nickname)
    await save_conversation(
        family_id=current_user["family_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role="assistant",
        content=opening,
    )
    return {"session_id": session_id, "opening": opening}


@router.post("/stt")
async def agent_stt(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    """语音转文字：优先 Whisper 本地识别，未安装时返回演示指令文本。"""
    stt_dir = os.path.join(settings.upload_dir, "stt")
    os.makedirs(stt_dir, exist_ok=True)
    audio_path = os.path.join(stt_dir, f"{uuid.uuid4().hex}.wav")
    content = await file.read()
    with open(audio_path, "wb") as f:
        f.write(content)
    try:
        text = await speech_to_text(audio_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass
    return {"text": text}


@router.post("/tts")
async def agent_tts(
    payload: TTSRequest,
    current_user: dict = Depends(get_current_user),
):
    """文字转语音（edge-tts），返回音频流。"""
    tts_dir = os.path.join(settings.upload_dir, "tts")
    os.makedirs(tts_dir, exist_ok=True)
    output_path = os.path.join(tts_dir, f"{uuid.uuid4().hex}.mp3")
    try:
        audio_path = await text_to_speech(payload.text, output_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    media_type = "audio/wav" if audio_path.lower().endswith(".wav") else "audio/mpeg"
    return FileResponse(
        audio_path,
        media_type=media_type,
        background=BackgroundTask(_cleanup_temp_file, audio_path),
    )


def _cleanup_temp_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


async def _stream_agent_state(websocket: WebSocket, final_state: dict, session_id: str):
    """流式推送最终回复；中断时推送 agent_interrupt。"""
    interrupt = final_state.get("_interrupt")
    if interrupt:
        thread_id = (
            final_state.get("thread_id")
            or interrupt.get("thread_id")
            or f"thread_{session_id}"
        )
        await ws_manager.send_agent_message(
            websocket,
            {
                "type": "agent_interrupt",
                "interrupt": {**interrupt, "thread_id": thread_id},
                "session_id": session_id,
            },
        )
        await ws_manager.send_agent_message(websocket, {"type": "avatar_state", "state": "idle"})
        return

    response = final_state.get("final_response", "") or ""
    avatar = final_state.get("avatar_emotion", "idle")
    await ws_manager.send_agent_message(websocket, {"type": "avatar_state", "state": "speaking"})
    step = 3
    for index in range(0, len(response), step):
        await ws_manager.send_agent_message(
            websocket,
            {
                "type": "agent_token",
                "content": response[index : index + step],
                "session_id": session_id,
            },
        )
        await asyncio.sleep(0.02)
    await ws_manager.send_agent_message(
        websocket,
        {
            "type": "agent_done",
            "content": response,
            "session_id": session_id,
            "avatar_emotion": avatar,
        },
    )


async def _stream_agent_response(websocket: WebSocket, state: dict, session_id: str):
    """WebSocket 对话：保存用户消息并执行 Agent。"""
    await save_conversation(
        family_id=state["family_id"],
        user_id=state["user_id"],
        session_id=session_id,
        role="user",
        content=state["user_input"],
    )
    await ws_manager.send_agent_message(websocket, {"type": "avatar_state", "state": "thinking"})
    final_state = await _run_agent(
        state,
        on_event=_make_node_event_sender(websocket, session_id),
    )
    await _save_agent_result(
        state["family_id"],
        state["user_id"],
        final_state,
        session_id,
    )
    await _stream_agent_state(websocket, final_state, session_id)


@router.websocket("/ws")
async def agent_ws(websocket: WebSocket):
    """WebSocket 对话：chat 消息开始执行，resume 消息恢复中断。"""
    await ws_manager.connect(websocket)
    token = websocket.query_params.get("token")
    current_user = current_user_payload_from_query(token)
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
                        "type": "agent_done",
                        "content": "WebSocket 未认证：请在连接地址中携带 token 参数",
                        "session_id": data.get("session_id", ""),
                    },
                )
                continue
            if message_type == "chat":
                session_id = _ensure_session_id(data.get("session_id"))
                permission_mode = data.get("permission_mode") or "normal"
                history = await get_session_conversations(
                    current_user["family_id"],
                    current_user["user_id"],
                    session_id,
                    limit=10,
                )
                state = _build_initial_state(
                    data.get("message", ""),
                    current_user,
                    session_id,
                    permission_mode,
                    history=[_conversation_to_message(item) for item in history],
                    house_status=None,
                    provider=data.get("provider"),
                    model=data.get("model"),
                )
                await _stream_agent_response(websocket, state, session_id)
            elif message_type == "resume":
                try:
                    final_state = await _resume_agent(
                        data.get("thread_id", ""),
                        data.get("resume_data") or {},
                        on_event=_make_node_event_sender(
                            websocket,
                            data.get("session_id", ""),
                        ),
                        provider=data.get("provider"),
                        model=data.get("model"),
                    )
                except HTTPException as exc:
                    await ws_manager.send_agent_message(
                        websocket, {"type": "agent_error", "content": exc.detail}
                    )
                    continue
                session_id = final_state.get("session_id") or data.get("session_id", "")
                resume_text = _resume_data_to_text(data.get("resume_data") or {})
                if resume_text:
                    await save_conversation(
                        family_id=current_user["family_id"],
                        user_id=current_user["user_id"],
                        session_id=session_id,
                        role="user",
                        content=resume_text,
                    )
                await _save_agent_result(
                    current_user["family_id"],
                    current_user["user_id"],
                    final_state,
                    session_id,
                )
                await _stream_agent_state(websocket, final_state, session_id)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:  # 单连接异常不影响其他连接
        logger.warning("WebSocket 处理异常: %s", exc)
        ws_manager.disconnect(websocket)
