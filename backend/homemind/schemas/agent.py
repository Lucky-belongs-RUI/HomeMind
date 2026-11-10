from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    """Agent 对话请求：权限模式由前端按钮传递，模型由前端下拉框选择。"""

    message: str
    session_id: str | None = None
    permission_mode: Literal["high", "normal"] = "normal"
    provider: str | None = None  # qwen / deepseek / zhipu / ollama
    model: str | None = None  # 具体模型名
    model_config_id: int | None = None  # 用户个人模型配置 ID


class ResumeRequest(BaseModel):
    """中断恢复请求：用户回答或审批决策。"""

    thread_id: str
    resume_data: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    model_config_id: int | None = None


class TTSRequest(BaseModel):
    """文字转语音请求。"""

    text: str


class ResetChatRequest(BaseModel):
    """重置会话请求：删除指定 session_id 的全部聊天记录。"""

    session_id: str | None = None


class OpeningRequest(BaseModel):
    """首次进入聊天界面：请求全屋状态动态开场白。"""

    session_id: str | None = None


# ============================================================
# 响应模型
# ============================================================


class AgentChatResponse(BaseModel):
    """`/agent/v2/chat` 与 `/agent/v2/resume` 的统一响应。

    两种形态：
    - 正常完成：`response` 有值，`interrupt` 为 None；
    - 中断等待用户输入（澄清/审批）：`response` 与 `avatar_emotion` 为 None，
      `interrupt` 携带问询内容。

    `interrupt` 的内部结构随中断类型（澄清 / 审批）而异，故为自由字典。
    """

    response: str | None = None
    session_id: str
    thread_id: str
    avatar_emotion: str | None = None
    interrupt: dict[str, Any] | None = None
    model_warning: str | None = None


class SttResponse(BaseModel):
    """语音识别结果。"""

    text: str


class SecurityAlarm(BaseModel):
    """家庭安防告警状态。"""

    status: str
    messages: list[str] = []


class EnvironmentResponse(BaseModel):
    """家庭中控环境指标（AI 助理顶部展示）。

    没有对应设备时字段为 None，前端展示 "--"。
    """

    indoor_temperature: float | None = None
    outdoor_temperature: float | None = None
    indoor_humidity: float | None = None
    air_quality: str | None = None
    weather: str | None = None
    network_status: str | None = None
    security_alarm: SecurityAlarm | None = None
    electricity_balance: float | None = None
    water_balance: float | None = None
    gas_balance: float | None = None
