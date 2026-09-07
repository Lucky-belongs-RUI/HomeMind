from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel


class ToolDefinition(BaseModel):
    """工具定义，传给 LLM 让其知道可调用哪些工具。"""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema 格式


class ToolCall(BaseModel):
    """LLM 返回的工具调用请求。"""

    id: str
    name: str
    arguments: Dict[str, Any]


class Message(BaseModel):
    """统一消息格式，适配层内部转换到各模型专有格式。"""

    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None  # assistant 调用工具时
    tool_call_id: Optional[str] = None  # role=tool 时关联的调用 ID
    name: Optional[str] = None  # role=tool 时工具名称


class LLMResponse(BaseModel):
    """LLM 统一响应。"""

    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"
    usage: Dict[str, int] = {}
