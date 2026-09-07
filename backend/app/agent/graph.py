"""Agent 状态图：意图识别优先 + 多链路并发执行（LangGraph 优先，缺失时轻量回退）。

流程：
1. 意图识别（先于任何数据库检索；纯闲聊直接走聊天链路，不查库）。
2. 需要澄清时中断询问，澄清后重新识别。
3. 依据意图集合路由到一条或多条链路（并发执行）：
   - 情感聊天 / 闲聊       → 聊天链路（chat_generation）
   - 智能问答（知识查询）   → RAG 链路（rag_retrieval → rag_answer）
   - 设备控制 / 场景 / 查询 → 设备链路（house_status → task_planning → approval → tool_execution）
   - 报告生成              → 报告链路（report_generation，内部补齐全屋状态与 RAG）
4. 结果汇总 → 组织回复 → END。
"""
import asyncio

from app.agent.nodes.approval import approval_node
from app.agent.nodes.chat_generation import chat_generation_node
from app.agent.nodes.clarification import clarification_node
from app.agent.nodes.house_status import house_status_retrieval_node
from app.agent.nodes.intent_recognition import intent_recognition_node
from app.agent.nodes.rag_answer import rag_answer_node
from app.agent.nodes.rag_retrieval import rag_retrieval_node
from app.agent.nodes.report_generation import report_generation_node
from app.agent.nodes.response_generation import response_generation_node
from app.agent.nodes.result_aggregation import result_aggregation_node
from app.agent.nodes.task_execution import task_execution_node
from app.agent.nodes.task_planning import task_planning_node
from app.agent.nodes.tool_execution import tool_execution_node
from app.agent.rules.intent import compute_active_chains
from app.agent.state import AgentState

MAX_ITERATIONS = 5

NODE_INTENT = "intent_recognition"
NODE_CLARIFY = "clarification"
NODE_HOUSE_STATUS = "house_status_retrieval"
NODE_CHAT = "chat_generation"
NODE_RAG = "rag_retrieval"
NODE_RAG_ANSWER = "rag_answer"
NODE_REPORT = "report_generation"
NODE_PLAN = "task_planning"
NODE_APPROVAL = "approval"
NODE_TOOLS = "tool_execution"
NODE_AGGREGATE = "result_aggregation"
NODE_RESPONSE = "response_generation"
NODE_TASK = "task_execution"

NODE_LABELS = {
    NODE_INTENT: "意图识别",
    NODE_CLARIFY: "澄清询问",
    NODE_HOUSE_STATUS: "全屋状态",
    NODE_CHAT: "情感聊天",
    NODE_RAG: "知识检索",
    NODE_RAG_ANSWER: "智能问答",
    NODE_REPORT: "报告生成",
    NODE_PLAN: "任务规划",
    NODE_APPROVAL: "审批",
    NODE_TOOLS: "工具调用",
    NODE_AGGREGATE: "结果汇总",
    NODE_RESPONSE: "回复生成",
    NODE_TASK: "任务执行",
}

# 节点所属链路（用于前端流式面板按链路分组展示）
NODE_CHAIN = {
    NODE_INTENT: "意图识别",
    NODE_CLARIFY: "澄清询问",
    NODE_HOUSE_STATUS: "全屋状态",
    NODE_CHAT: "情感聊天",
    NODE_RAG: "智能问答",
    NODE_RAG_ANSWER: "智能问答",
    NODE_REPORT: "报告生成",
    NODE_PLAN: "设备控制",
    NODE_APPROVAL: "设备控制",
    NODE_TOOLS: "设备控制",
    NODE_AGGREGATE: "结果汇总",
    NODE_RESPONSE: "回复生成",
    NODE_TASK: "任务执行",
}

# 链路 → 入口节点
CHAIN_ENTRY = {
    "chat": NODE_CHAT,
    "knowledge": NODE_RAG,
    "control": NODE_PLAN,
    "report": NODE_REPORT,
}

CHAIN_LABELS = {
    "chat": "情感聊天",
    "knowledge": "智能问答",
    "control": "设备控制",
    "report": "报告生成",
}

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    HAS_LANGGRAPH = True
except Exception:  # langgraph 未安装或版本不兼容
    HAS_LANGGRAPH = False


def _active_chains_from_state(state: dict) -> list:
    """读取或计算激活链路。"""
    chains = state.get("active_chains") or []
    if not chains:
        chains = compute_active_chains(state.get("intents") or [])
        state["active_chains"] = chains
    return chains


def _needs_house_status(chains: list) -> bool:
    return any(chain in ("control", "report") for chain in chains)


def route_after_intent(state: dict):
    """意图识别后路由：需澄清进澄清；否则补齐全屋状态后并发进入各链路。"""
    if state.get("needs_clarification"):
        return NODE_CLARIFY
    chains = _active_chains_from_state(state)
    if _needs_house_status(chains) and not state.get("house_status"):
        return NODE_HOUSE_STATUS
    return [CHAIN_ENTRY[chain] for chain in chains]


def route_after_house_status(state: dict) -> list:
    """全屋状态就绪后并发进入各激活链路。"""
    chains = _active_chains_from_state(state)
    return [CHAIN_ENTRY[chain] for chain in chains]


def route_after_clarify(state: dict) -> str:
    """回答后重新识别意图；规划阶段触发的澄清则回到任务规划；超限直接结束。"""
    if state.get("final_response"):
        return END
    if state.get("clarify_source") == "plan":
        return NODE_PLAN
    return NODE_INTENT


def route_after_plan(state: dict) -> str:
    """任务规划后：普通模式房间/参数不明确时再次澄清，否则进入审批。"""
    if state.get("needs_clarification"):
        return NODE_CLARIFY
    return NODE_APPROVAL


def route_after_approval(state: dict) -> str:
    """审批通过进入工具调用；取消则进入结果汇总（保留其他链路结果）。"""
    if state.get("approval_granted"):
        return NODE_TOOLS
    return NODE_AGGREGATE


async def _emit_node_event(on_node_event, node: str, status: str) -> None:
    """统一向调用方推送节点流式事件（含所属链路）。"""
    if on_node_event is None:
        return
    await on_node_event(
        {
            "type": "agent_step",
            "node": node,
            "label": NODE_LABELS.get(node, node),
            "chain": NODE_CHAIN.get(node, "执行链路"),
            "status": status,
        }
    )


class LightweightAgentRunner:
    """LangGraph 不可用时的轻量状态图执行器，保持同一 ainvoke 接口。

    非阻塞链路（聊天/问答/报告）并发执行，设备链路因可能中断按顺序执行。
    中断采用 state["_interrupt"] 标记；恢复时由 API 层写入
    state["_resume_data"] 后重新执行。
    """

    async def ainvoke(self, state: dict, on_node_event=None) -> dict:
        current = dict(state)

        await _emit_node_event(on_node_event, NODE_INTENT, "running")
        current = await intent_recognition_node(current)
        await _emit_node_event(on_node_event, NODE_INTENT, "completed")

        while True:
            if current.get("needs_clarification"):
                await _emit_node_event(on_node_event, NODE_CLARIFY, "running")
                current = await clarification_node(current)
                await _emit_node_event(on_node_event, NODE_CLARIFY, "completed")
                if current.get("_interrupt"):
                    return current
                if current.get("final_response"):
                    return current
                await _emit_node_event(on_node_event, NODE_INTENT, "running")
                current = await intent_recognition_node(current)
                await _emit_node_event(on_node_event, NODE_INTENT, "completed")
                continue
            break

        chains = _active_chains_from_state(current)
        current["active_chains"] = chains

        # 设备/报告链路需要全屋状态：先补齐一次（state 已有则复用，避免重复查库）
        if _needs_house_status(chains) and not current.get("house_status"):
            await _emit_node_event(on_node_event, NODE_HOUSE_STATUS, "running")
            current = await house_status_retrieval_node(current)
            await _emit_node_event(on_node_event, NODE_HOUSE_STATUS, "completed")

        # 并发执行非阻塞链路：聊天 / 知识问答 / 报告
        async def run_nonblocking_chain(name: str):
            snapshot = dict(current)
            if name == "chat" and "chat" in chains:
                await _emit_node_event(on_node_event, NODE_CHAT, "running")
                snapshot = await chat_generation_node(snapshot)
                await _emit_node_event(on_node_event, NODE_CHAT, "completed")
            elif name == "knowledge" and "knowledge" in chains:
                await _emit_node_event(on_node_event, NODE_RAG, "running")
                snapshot = await rag_retrieval_node(snapshot)
                await _emit_node_event(on_node_event, NODE_RAG, "completed")
                await _emit_node_event(on_node_event, NODE_RAG_ANSWER, "running")
                snapshot = await rag_answer_node(snapshot)
                await _emit_node_event(on_node_event, NODE_RAG_ANSWER, "completed")
            elif name == "report" and "report" in chains:
                await _emit_node_event(on_node_event, NODE_REPORT, "running")
                snapshot = await report_generation_node(snapshot)
                await _emit_node_event(on_node_event, NODE_REPORT, "completed")
            return snapshot.get("chain_results", {}).get(name)

        chain_results = dict(current.get("chain_results") or {})
        results = await asyncio.gather(
            run_nonblocking_chain("chat"),
            run_nonblocking_chain("knowledge"),
            run_nonblocking_chain("report"),
        )
        for name, result in zip(("chat", "knowledge", "report"), results):
            if result is not None:
                chain_results[name] = result
        current["chain_results"] = chain_results

        # 设备链路（顺序执行，可能中断审批）
        if "control" in chains:
            await _emit_node_event(on_node_event, NODE_PLAN, "running")
            current = await task_planning_node(current)
            await _emit_node_event(on_node_event, NODE_PLAN, "completed")

            if current.get("needs_clarification"):
                await _emit_node_event(on_node_event, NODE_CLARIFY, "running")
                current = await clarification_node(current)
                await _emit_node_event(on_node_event, NODE_CLARIFY, "completed")
                if current.get("_interrupt"):
                    return current
                if current.get("final_response"):
                    return current
                await _emit_node_event(on_node_event, NODE_PLAN, "running")
                current = await task_planning_node(current)
                await _emit_node_event(on_node_event, NODE_PLAN, "completed")

            await _emit_node_event(on_node_event, NODE_APPROVAL, "running")
            current = await approval_node(current)
            await _emit_node_event(on_node_event, NODE_APPROVAL, "completed")
            if current.get("_interrupt"):
                return current
            if current.get("approval_granted") is not False:
                await _emit_node_event(on_node_event, NODE_TOOLS, "running")
                current = await tool_execution_node(current)
                await _emit_node_event(on_node_event, NODE_TOOLS, "completed")
            # 取消时 chain_results["control"] 已写入 cancelled 标记

        await _emit_node_event(on_node_event, NODE_AGGREGATE, "running")
        current = await result_aggregation_node(current)
        await _emit_node_event(on_node_event, NODE_AGGREGATE, "completed")
        await _emit_node_event(on_node_event, NODE_RESPONSE, "running")
        current = await response_generation_node(current)
        await _emit_node_event(on_node_event, NODE_RESPONSE, "completed")
        await _emit_node_event(on_node_event, NODE_TASK, "running")
        current = await task_execution_node(current)
        await _emit_node_event(on_node_event, NODE_TASK, "completed")
        return current


NODE_FUNCS = {
    NODE_INTENT: intent_recognition_node,
    NODE_CLARIFY: clarification_node,
    NODE_HOUSE_STATUS: house_status_retrieval_node,
    NODE_CHAT: chat_generation_node,
    NODE_RAG: rag_retrieval_node,
    NODE_RAG_ANSWER: rag_answer_node,
    NODE_REPORT: report_generation_node,
    NODE_PLAN: task_planning_node,
    NODE_APPROVAL: approval_node,
    NODE_TOOLS: tool_execution_node,
    NODE_AGGREGATE: result_aggregation_node,
    NODE_RESPONSE: response_generation_node,
    NODE_TASK: task_execution_node,
}


def build_agent_graph():
    """构建意图优先 + 多链路并发状态图。"""
    if not HAS_LANGGRAPH:
        return LightweightAgentRunner()

    workflow = StateGraph(AgentState)
    for name, func in NODE_FUNCS.items():
        workflow.add_node(name, func)

    entry_map = {CHAIN_ENTRY[chain]: CHAIN_ENTRY[chain] for chain in CHAIN_ENTRY}

    workflow.add_edge(START, NODE_INTENT)
    workflow.add_conditional_edges(
        NODE_INTENT,
        route_after_intent,
        {NODE_CLARIFY: NODE_CLARIFY, NODE_HOUSE_STATUS: NODE_HOUSE_STATUS, **entry_map},
    )
    workflow.add_conditional_edges(NODE_HOUSE_STATUS, route_after_house_status, entry_map)

    workflow.add_conditional_edges(
        NODE_CLARIFY,
        route_after_clarify,
        {NODE_INTENT: NODE_INTENT, NODE_PLAN: NODE_PLAN, END: END},
    )

    # 聊天链路
    workflow.add_edge(NODE_CHAT, NODE_AGGREGATE)
    # 知识问答链路
    workflow.add_edge(NODE_RAG, NODE_RAG_ANSWER)
    workflow.add_edge(NODE_RAG_ANSWER, NODE_AGGREGATE)
    # 报告链路
    workflow.add_edge(NODE_REPORT, NODE_AGGREGATE)
    # 设备链路
    workflow.add_conditional_edges(
        NODE_PLAN,
        route_after_plan,
        {NODE_CLARIFY: NODE_CLARIFY, NODE_APPROVAL: NODE_APPROVAL},
    )
    workflow.add_conditional_edges(
        NODE_APPROVAL,
        route_after_approval,
        {NODE_TOOLS: NODE_TOOLS, NODE_AGGREGATE: NODE_AGGREGATE},
    )
    workflow.add_edge(NODE_TOOLS, NODE_AGGREGATE)

    workflow.add_edge(NODE_AGGREGATE, NODE_RESPONSE)
    workflow.add_edge(NODE_RESPONSE, NODE_TASK)
    workflow.add_edge(NODE_TASK, END)

    # MemorySaver 仅保存在内存：服务重启后需重新发起对话
    return workflow.compile(checkpointer=MemorySaver())


# 全局 Agent 实例（HTTP 与 WebSocket 共用）
agent_app = build_agent_graph()
