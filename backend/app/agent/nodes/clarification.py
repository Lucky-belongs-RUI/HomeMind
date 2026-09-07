"""中断询问节点：LangGraph interrupt 暂停并向用户提问澄清。"""
from app.agent.nodes._base import extract_answer, is_interrupted, log_node_run, wait_user

MAX_CLARIFICATION_ATTEMPTS = 2


@log_node_run
async def clarification_node(state: dict) -> dict:
    """等待用户回答；超过最大重试次数后直接结束。"""
    if not state.get("needs_clarification"):
        return state
    if state.get("clarification_attempts", 0) >= MAX_CLARIFICATION_ATTEMPTS:
        state["final_response"] = "抱歉，我还是没能完全理解您的需求，请换个说法试试。"
        state["avatar_emotion"] = "sad"
        state["needs_clarification"] = False
        return state

    question = state.get("clarification_question") or "请补充说明您的需求。"
    payload = {
        "type": "clarification",
        "question": question,
        "options": state.get("clarification_options") or [],
        "thread_id": state.get("thread_id", ""),
    }
    resume_data = wait_user(state, payload)
    if is_interrupted(state):
        return state

    answer = extract_answer(resume_data)
    previous = (state.get("user_clarification") or "").strip()
    state["user_clarification"] = f"{previous} {answer}".strip() if previous else answer
    state["clarification_attempts"] = state.get("clarification_attempts", 0) + 1
    state["needs_clarification"] = False
    return state