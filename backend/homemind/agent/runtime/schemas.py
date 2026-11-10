"""Agent 内部契约。

与 `schemas/`（对外 API）分开：这里只约束模型输出与图内部数据，
可以随图演进，不构成对客户端的承诺。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BranchName = Literal["chat", "knowledge", "control", "report"]
RiskLevel = Literal["low", "medium", "high"]


class PlanTask(BaseModel):
    """规划器拆出的单个子任务。

    `branch` 直接使用主图节点名，避免再做一层意图到分支的映射；
    `instruction` 是子目标（control/chat 使用），`query` 是独立检索问题。
    """

    model_config = ConfigDict(extra="ignore")

    branch: BranchName
    instruction: str = ""
    query: str = ""


class Plan(BaseModel):
    """规划器的结构化输出。"""

    model_config = ConfigDict(extra="ignore")

    tasks: list[PlanTask] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_options: list[str] = Field(default_factory=list)


class TaskSpec(BaseModel):
    """控制子图内可执行的单个工具任务。"""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    risk_level: RiskLevel = "low"
    expected_effect: str = ""
    idempotency_key: str = ""


class BranchResult(BaseModel):
    """子图回传给主图的结果。"""

    branch: str
    success: bool = True
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    degraded: bool = False


class ApprovalDecision(BaseModel):
    approved: bool = False
    approved_task_ids: list[str] = Field(default_factory=list)
    note: str = ""


class ClarificationDecision(BaseModel):
    answer: str = ""
    cancelled: bool = False
