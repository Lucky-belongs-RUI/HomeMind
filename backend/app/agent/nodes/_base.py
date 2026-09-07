"""节点公共工具：LangGraph interrupt 适配、恢复数据解析与运行日志。

优先使用 LangGraph 原生 interrupt；轻量执行器下将中断信息写入
state["_interrupt"]，并在 state["_resume_data"] 中读取恢复数据。
log_node_run 统一记录每个 LangGraph 节点的运行前后日志。
"""
import functools
import inspect
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("app.agent.nodes")

try:
    from langgraph.types import interrupt as _langgraph_interrupt

    HAS_LANGGRAPH = True
except Exception:  # langgraph 未安装或版本不兼容
    _langgraph_interrupt = None
    HAS_LANGGRAPH = False


def wait_user(state: Dict[str, Any], payload: Dict[str, Any]) -> Any:
    """触发中断并返回用户恢复数据；轻量执行器不抛中断。"""
    if _langgraph_interrupt is not None:
        return _langgraph_interrupt(payload)
    resume = state.get("_resume_data")
    if resume is not None:
        state.pop("_resume_data", None)
        return resume
    state["_interrupt"] = payload
    return None


def is_interrupted(state: Dict[str, Any]) -> bool:
    """轻量执行器判断当前是否处于中断状态。"""
    return state.get("_interrupt") is not None


def extract_answer(resume_data: Any, field: str = "answer") -> str:
    """从恢复数据中提取澄清回答文本。"""
    if isinstance(resume_data, str):
        return resume_data
    if isinstance(resume_data, dict):
        return resume_data.get(field) or resume_data.get("text") or ""
    return ""


def extract_decision(resume_data: Any) -> Dict[str, Any]:
    """从恢复数据中提取审批决策。"""
    if isinstance(resume_data, dict):
        return resume_data
    return {}


def build_thread_id(session_id: str) -> str:
    """基于会话生成稳定的 LangGraph 线程 ID。"""
    return f"thread_{session_id}"


def build_llm_messages(state: Dict[str, Any], extra_text: str = "") -> list:
    """从 state 中提取最近对话历史并追加当前用户输入，供 LLM 调用。"""
    from app.llm.message import Message

    history = []
    for item in state.get("messages") or []:
        if item.get("role") in ("user", "assistant"):
            history.append(Message(role=item["role"], content=item.get("content") or ""))
    history = history[-12:]
    text = (state.get("user_input") or "").strip()
    if extra_text:
        text = f"{text} {extra_text}".strip()
    if history and history[-1].role == "user":
        history[-1] = Message(role="user", content=text)
    else:
        history.append(Message(role="user", content=text))
    return history

NODE_LABELS = {
    "rag_retrieval_node": "RAG检索",
    "intent_recognition_node": "意图识别",
    "clarification_node": "澄清询问",
    "house_status_retrieval_node": "全屋状态",
    "chat_generation_node": "情感聊天",
    "rag_answer_node": "智能问答",
    "report_generation_node": "报告生成",
    "task_planning_node": "任务规划",
    "approval_node": "审批",
    "tool_execution_node": "工具调用",
    "result_aggregation_node": "结果汇总",
    "response_generation_node": "回复生成",
    "task_execution_node": "任务执行",
}


def log_node_run(func):
    """记录节点运行日志，兼容同步与异步节点函数。"""
    label = NODE_LABELS.get(func.__name__, func.__name__)

    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.info("%s节点正在运行", label)
            result = await func(*args, **kwargs)
            logger.info("%s节点运行结果：%s", label, result)
            return result

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        logger.info("%s节点正在运行", label)
        result = func(*args, **kwargs)
        logger.info("%s节点运行结果：%s", label, result)
        return result

    return sync_wrapper
