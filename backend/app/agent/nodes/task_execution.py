"""任务执行节点：保存对话并处理场景联动等收尾动作。"""
import logging

from app.agent.nodes._base import log_node_run

logger = logging.getLogger(__name__)


@log_node_run
async def task_execution_node(state: dict) -> dict:
    """保存 assistant 对话；预留场景联动、定时任务与结果推送扩展点。"""
    state = dict(state)

    # 场景联动：场景触发任务已在工具执行节点通过 trigger_scene 完成
    # 定时任务：后续可基于 tasks 中的 time 字段注册 APScheduler 任务
    # 结果推送：由 API 层保存 assistant 回复并根据 avatar_emotion 推送 WebSocket
    return state