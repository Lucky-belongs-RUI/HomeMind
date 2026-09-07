from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    """Agent 对话请求：权限模式由前端按钮传递，模型由前端下拉框选择。"""
    message: str
    session_id: Optional[str] = None
    permission_mode: Literal["high", "normal"] = "normal"
    provider: Optional[str] = None  # qwen / deepseek / zhipu / ollama
    model: Optional[str] = None     # 具体模型名


class ResumeRequest(BaseModel):
    """中断恢复请求：用户回答或审批决策。"""
    thread_id: str
    resume_data: Dict[str, Any] = Field(default_factory=dict)
    provider: Optional[str] = None
    model: Optional[str] = None


class TTSRequest(BaseModel):
    """文字转语音请求。"""
    text: str


class ResetChatRequest(BaseModel):
    """重置会话请求：删除指定 session_id 的全部聊天记录。"""
    session_id: Optional[str] = None


class OpeningRequest(BaseModel):
    """首次进入聊天界面：请求全屋状态动态开场白。"""
    session_id: Optional[str] = None