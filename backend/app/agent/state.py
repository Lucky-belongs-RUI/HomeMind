import operator
from typing import Annotated, Any, Dict, List, Optional

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """Agent 状态：九节点闭环之间传递，包含家庭隔离所需字段。"""

    # ===== 用户输入与身份 =====
    user_input: str
    user_id: int
    user_role: str
    family_id: int
    session_id: str
    permission_mode: str  # high / normal，前端按钮设置
    thread_id: str

    # ===== 模型选择 =====
    provider: str  # qwen / deepseek / zhipu / ollama
    model: str     # 具体模型名

    # ===== 全屋状态 =====
    house_status: Optional[Dict[str, Any]]

    # ===== RAG 检索 =====
    rag_context: Optional[str]
    rag_sources: List[Dict[str, Any]]
    is_knowledge_query: bool

    # ===== 意图识别 =====
    intents: List[Dict[str, Any]]
    intent_clarity_score: float
    needs_clarification: bool
    clarification_question: str
    clarification_options: List[str]
    user_clarification: str
    clarification_attempts: int
    clarify_source: str  # intent / plan，标记澄清来自意图识别还是任务规划

    # ===== 多链路并发 =====
    active_chains: List[str]                # chat / knowledge / control / report
    # chain_results 用并集 reducer 合并：并发链路各自写入独立 key，避免覆盖
    chain_results: Annotated[Dict[str, Any], operator.or_]

    # ===== 任务规划与审批 =====
    tasks: List[Dict[str, Any]]
    needs_approval: bool
    approval_granted: bool
    approved_task_ids: List[str]

    # ===== 执行结果与回复 =====
    tool_results: List[Dict[str, Any]]
    success_count: int
    failure_count: int
    skipped_count: int
    final_response: Optional[str]
    avatar_emotion: str

    # ===== 流程控制 =====
    messages: List[Dict[str, Any]]
    iteration: int
    # 轻量执行器内部字段：中断标记与恢复数据
    _interrupt: Optional[Dict[str, Any]]
    _resume_data: Any
