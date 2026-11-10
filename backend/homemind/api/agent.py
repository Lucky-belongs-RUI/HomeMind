"""Agent 基础接口：环境指标、会话历史/重置、开场白与语音能力。

对话与中断恢复由 对话接口（api/agent_chat.py）提供；这里保留聊天 UI 仍需的
非对话能力，避免前端同时维护两套历史/语音接口。
"""

import contextlib
import inspect
import logging
import os
import uuid

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from homemind.agent.house_status import generate_opening_message
from homemind.agent.runtime.graph import get_agent_app
from homemind.api.deps import get_current_user
from homemind.core.config import settings
from homemind.core.exceptions import (
    ExternalServiceError,
    PayloadTooLargeError,
    ValidationError,
)
from homemind.schemas.agent import (
    EnvironmentResponse,
    OpeningRequest,
    ResetChatRequest,
    SttResponse,
    TTSRequest,
)
from homemind.schemas.responses import (
    MessageListResponse,
    OpeningResponse,
    ResetChatResponse,
)
from homemind.services import environment_service
from homemind.services.conversation_service import (
    delete_session_conversations,
    get_session_conversations,
    save_conversation,
)
from homemind.services.user_service import get_user
from homemind.voice.stt import speech_to_text
from homemind.voice.tts import text_to_speech

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["AI 助理"])


def _ensure_session_id(session_id: str | None) -> str:
    return session_id or f"session_{uuid.uuid4().hex[:12]}"


def _thread_id(family_id: int, user_id: int, session_id: str) -> str:
    return f"v2:{family_id}:{user_id}:{session_id}"


async def _delete_thread_checkpoint(thread_id: str) -> None:
    """删除会话对应的 Agent checkpoint 线程（重置会话时调用）。

    不同 checkpointer 的删除方法不同（AsyncPostgresSaver 用 adelete_thread，
    内存版用 delete_thread），都尝试一遍；删除失败只记录日志，不影响清理聊天记录。
    """
    try:
        checkpointer = getattr(get_agent_app(), "checkpointer", None)
        if checkpointer is None:
            return
        for method_name in ("adelete_thread", "delete_thread"):
            method = getattr(checkpointer, method_name, None)
            if method is None:
                continue
            result = method(thread_id)
            if inspect.isawaitable(result):
                await result
            return
    except Exception as exc:
        logger.warning("删除会话 checkpoint 失败 thread_id=%s: %s", thread_id, exc)


@router.get("/environment", response_model=EnvironmentResponse)
async def agent_environment(current_user: dict = Depends(get_current_user)):
    """家庭中控指标：温度、湿度、空气质量、光照（AI 助理顶部展示）。"""
    return await environment_service.get_family_environment(current_user["family_id"])


@router.get("/history", response_model=MessageListResponse)
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


@router.post("/reset", response_model=ResetChatResponse)
async def agent_reset_chat(
    payload: ResetChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """重置会话：删除该 session_id 的聊天记录与 Agent checkpoint。"""
    session_id = _ensure_session_id(payload.session_id)
    deleted = await delete_session_conversations(
        current_user["family_id"],
        current_user["user_id"],
        session_id,
    )
    # 聊天记录删了但 checkpoint 还在时，中断/澄清状态会“复活”，必须一并清理
    await _delete_thread_checkpoint(
        _thread_id(current_user["family_id"], current_user["user_id"], session_id)
    )
    return {"session_id": session_id, "deleted": deleted}


@router.post("/opening", response_model=OpeningResponse)
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


@router.post("/stt", response_model=SttResponse)
async def agent_stt(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    """语音转文字：优先 Whisper 本地识别，未安装时返回演示指令文本。

    与文档上传一致：先按声明大小预检，再分块读取，避免超大 body 耗尽内存。
    """
    stt_dir = os.path.join(settings.upload_dir, "stt")
    os.makedirs(stt_dir, exist_ok=True)
    audio_path = os.path.join(stt_dir, f"{uuid.uuid4().hex}.wav")

    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > settings.max_audio_size:
        raise PayloadTooLargeError(
            f"音频文件过大（上限 {settings.max_audio_size // (1024 * 1024)}MB）"
        )

    buffer = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > settings.max_audio_size:
            raise PayloadTooLargeError(
                f"音频文件过大（上限 {settings.max_audio_size // (1024 * 1024)}MB）"
            )
    content = bytes(buffer)
    if not content:
        raise ValidationError("音频内容为空")

    with open(audio_path, "wb") as f:
        f.write(content)
    try:
        text = await speech_to_text(audio_path)
    except RuntimeError as exc:
        raise ExternalServiceError(str(exc)) from exc
    finally:
        with contextlib.suppress(OSError):
            os.remove(audio_path)
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
        raise ExternalServiceError(str(exc)) from exc
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
