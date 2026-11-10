"""Agent 任务规划测试：结构化分解、强指令补全与 Send 扇出。

规划器只负责拆任务；具体执行交给各分支。这里用假模型验证合同，
不触网、不连库。
"""

import pytest

from homemind.agent.runtime import planner
from homemind.agent.runtime.planner import (
    _normalize_tasks,
    plan_node,
    route_after_clarify,
    route_after_plan,
)
from homemind.agent.runtime.schemas import Plan, PlanTask
from homemind.core.config import settings

_REQUEST = {"user_id": 1, "family_id": 1, "role": "owner", "thread_id": "t"}


class _FakeRouter:
    def __init__(self, plan: Plan | None = None, error: Exception | None = None):
        self.plan = plan
        self.error = error
        self.messages = None

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.plan


class _FakeContextTool:
    def __init__(self, result: dict):
        self.result = result
        self.calls: list[dict] = []
        self.name = "fake_context_tool"

    async def ainvoke(self, payload):
        self.calls.append(payload)
        return self.result


def _state(text: str, devices: list[dict] | None = None) -> dict:
    return {
        "user_input": text,
        "request": _REQUEST,
        "house_snapshot": {"devices": devices or []},
        "profile_text": "- 怕冷：true",
        "history_text": "用户：把客厅空调调到26度\n助手：已调到26度",
    }


def _bare_state(text: str) -> dict:
    return {
        "user_input": text,
        "request": _REQUEST,
        "house_snapshot": None,
        "profile": {},
        "profile_text": "",
        "history_text": "",
    }


def _patch_router(monkeypatch, router: _FakeRouter) -> _FakeRouter:
    monkeypatch.setattr(planner, "build_router_model", lambda *_a, **_k: router)
    return router


@pytest.mark.asyncio
async def test_plan_node_preserves_model_decomposition(monkeypatch):
    router = _patch_router(
        monkeypatch,
        _FakeRouter(
            Plan(
                tasks=[
                    PlanTask(branch="chat", instruction="安慰感冒的用户"),
                    PlanTask(branch="control", instruction="调高一下空调温度"),
                    PlanTask(
                        branch="knowledge",
                        instruction="查询药箱用药资料",
                        query="感冒时药箱里的药怎么吃",
                    ),
                ]
            )
        ),
    )

    result = await plan_node(
        _state(
            "我感冒了，调高一下空调温度，药箱里的药我该吃哪些药",
            [{"room": "卧室", "type": "air_conditioner"}],
        )
    )

    assert [task["branch"] for task in result["plan"]["tasks"]] == [
        "chat",
        "control",
        "knowledge",
    ]
    assert result["plan"]["tasks"][1]["instruction"] == "调高一下空调温度"
    assert result["plan"]["tasks"][2]["query"] == "感冒时药箱里的药怎么吃"
    assert "怕冷" in router.messages[0].content
    assert "把客厅空调调到26度" in router.messages[0].content


@pytest.mark.asyncio
async def test_plan_node_merges_strong_control_signal(monkeypatch):
    """模型只拆出 chat，但用户明确要求开灯时必须补上 control。"""
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="chat", instruction="回应")])),
    )

    result = await plan_node(
        _state("打开客厅灯", [{"room": "客厅", "type": "light"}])
    )

    branches = [task["branch"] for task in result["plan"]["tasks"]]
    assert branches == ["chat", "control"]
    assert result["plan"]["tasks"][1]["instruction"] == "打开客厅灯"


@pytest.mark.asyncio
async def test_plan_node_does_not_invent_control_for_health(monkeypatch):
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="chat", instruction="安慰")])),
    )

    result = await plan_node(
        _state("我感冒了", [{"room": "卧室", "type": "air_conditioner"}])
    )

    assert [task["branch"] for task in result["plan"]["tasks"]] == ["chat"]


@pytest.mark.asyncio
async def test_plan_node_falls_back_to_rules_on_model_error(monkeypatch):
    _patch_router(monkeypatch, _FakeRouter(error=RuntimeError("model down")))

    result = await plan_node(
        _state("打开客厅灯", [{"room": "客厅", "type": "light"}])
    )

    assert [task["branch"] for task in result["plan"]["tasks"]] == ["control"]


@pytest.mark.asyncio
async def test_plan_node_rule_fallback_keeps_health_as_chat(monkeypatch):
    _patch_router(monkeypatch, _FakeRouter(error=RuntimeError("model down")))

    result = await plan_node(
        _state("我感冒了", [{"room": "卧室", "type": "air_conditioner"}])
    )

    assert [task["branch"] for task in result["plan"]["tasks"]] == ["chat"]


@pytest.mark.asyncio
async def test_plan_node_loads_house_snapshot_on_demand(monkeypatch):
    router = _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="control", instruction="打开客厅灯")])),
    )
    tool = _FakeContextTool(
        {"success": True, "snapshot": {"devices": [{"room": "客厅", "type": "light"}]}}
    )
    monkeypatch.setattr(planner, "get_house_snapshot", tool)

    result = await plan_node(_bare_state("打开客厅灯"))

    assert len(tool.calls) == 1
    assert result["house_snapshot"]["devices"][0]["room"] == "客厅"
    assert "客厅" in router.messages[0].content


@pytest.mark.asyncio
async def test_plan_node_skips_house_snapshot_for_time_query(monkeypatch):
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="control", instruction="查时间")])),
    )
    tool = _FakeContextTool({"success": True, "snapshot": {"devices": []}})
    monkeypatch.setattr(planner, "get_house_snapshot", tool)

    result = await plan_node(_bare_state("现在几点了"))

    assert tool.calls == []
    assert result.get("house_snapshot") is None


@pytest.mark.asyncio
async def test_plan_node_loads_house_snapshot_for_model_detected_report(monkeypatch):
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="report", instruction="汇总家庭状态")])),
    )
    tool = _FakeContextTool(
        {"success": True, "snapshot": {"devices": [{"room": "卧室", "type": "light"}]}}
    )
    monkeypatch.setattr(planner, "get_house_snapshot", tool)

    result = await plan_node(_bare_state("家里现在怎么样"))

    assert len(tool.calls) == 1
    assert result["house_snapshot"]["devices"][0]["room"] == "卧室"


@pytest.mark.asyncio
async def test_plan_node_loads_profile_on_personal_signal(monkeypatch):
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="chat", instruction="安慰用户")])),
    )
    house_tool = _FakeContextTool({"success": True, "snapshot": {"devices": []}})
    profile_tool = _FakeContextTool({"success": True, "profile": {"怕冷": True}})
    monkeypatch.setattr(planner, "get_house_snapshot", house_tool)
    monkeypatch.setattr(planner, "get_user_profile", profile_tool)

    result = await plan_node(_bare_state("我感冒了"))

    assert house_tool.calls == []
    assert len(profile_tool.calls) == 1
    assert result["profile"] == {"怕冷": True}
    assert "怕冷" in result["profile_text"]


@pytest.mark.asyncio
async def test_plan_node_skips_profile_for_generic_chat(monkeypatch):
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="chat", instruction="讲故事")])),
    )
    house_tool = _FakeContextTool({"success": True, "snapshot": {"devices": []}})
    profile_tool = _FakeContextTool({"success": True, "profile": {"怕冷": True}})
    monkeypatch.setattr(planner, "get_house_snapshot", house_tool)
    monkeypatch.setattr(planner, "get_user_profile", profile_tool)

    result = await plan_node(_bare_state("给我讲个睡前故事"))

    assert house_tool.calls == []
    assert profile_tool.calls == []
    assert "profile" not in result


@pytest.mark.asyncio
async def test_plan_node_loads_house_snapshot_for_unrecognized_device_expression(monkeypatch):
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="control", instruction="让客厅亮堂一点")])),
    )
    tool = _FakeContextTool(
        {"success": True, "snapshot": {"devices": [{"room": "客厅", "type": "light"}]}}
    )
    monkeypatch.setattr(planner, "get_house_snapshot", tool)

    result = await plan_node(_bare_state("让客厅亮堂一点"))

    assert len(tool.calls) == 1
    assert result["house_snapshot"]["devices"][0]["type"] == "light"


@pytest.mark.asyncio
async def test_plan_node_loads_snapshot_for_mixed_time_and_indoor_state(monkeypatch):
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="control", instruction="查询时间和空气")])),
    )
    tool = _FakeContextTool(
        {"success": True, "snapshot": {"devices": [{"room": "客厅", "type": "air_monitor"}]}}
    )
    monkeypatch.setattr(planner, "get_house_snapshot", tool)

    result = await plan_node(_bare_state("现在几点，家里空气怎么样"))

    assert len(tool.calls) == 1
    assert result["house_snapshot"]["devices"][0]["type"] == "air_monitor"


@pytest.mark.asyncio
async def test_plan_node_merges_rule_room_clarification(monkeypatch):
    devices = [
        {"room": "客厅", "type": "air_conditioner"},
        {"room": "卧室", "type": "air_conditioner"},
    ]
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="control", instruction="把空调调到20度")])),
    )

    result = await plan_node(_state("把空调调到20度", devices))

    assert result["plan"]["needs_clarification"] is True
    assert result["plan"]["clarification_options"]


@pytest.mark.asyncio
async def test_plan_node_does_not_merge_noisy_rule_clarification(monkeypatch):
    devices = [
        {"room": "客厅", "type": "air_conditioner"},
        {"room": "卧室", "type": "air_conditioner"},
    ]
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="chat", instruction="解释原因")])),
    )

    result = await plan_node(_state("空调为什么吹热风", devices))

    assert result["plan"]["needs_clarification"] is False


@pytest.mark.asyncio
async def test_plan_node_loads_profile_for_preference_question(monkeypatch):
    _patch_router(
        monkeypatch,
        _FakeRouter(Plan(tasks=[PlanTask(branch="chat", instruction="按喜好推荐")])),
    )
    profile_tool = _FakeContextTool({"success": True, "profile": {"喜欢": "安静"}})
    monkeypatch.setattr(planner, "get_user_profile", profile_tool)

    result = await plan_node(_bare_state("根据我的喜好推荐一部电影"))

    assert len(profile_tool.calls) == 1
    assert "安静" in result["profile_text"]


@pytest.mark.asyncio
async def test_plan_node_keeps_tasks_for_routing_to_cap(monkeypatch):
    tasks = [
        PlanTask(branch="knowledge", instruction=f"问题{i}", query=f"问题{i}")
        for i in range(settings.agent_max_plan_tasks + 3)
    ]
    _patch_router(monkeypatch, _FakeRouter(Plan(tasks=tasks)))

    state = _state("查资料")
    result = await plan_node(state)
    sends = route_after_plan({**state, **result})

    # 截断在扇出时完成，且优先保留 control/report/chat
    assert len(sends) == settings.agent_max_plan_tasks


def test_normalize_tasks_merges_control_and_dedupes_knowledge():
    tasks = [
        PlanTask(branch="knowledge", instruction="规定", query="访客规定"),
        PlanTask(branch="control", instruction="打开客厅灯"),
        PlanTask(branch="control", instruction="把空调调到26度"),
        PlanTask(branch="knowledge", instruction="重复", query="访客规定"),
        PlanTask(branch="chat", instruction="闲聊一"),
        PlanTask(branch="chat", instruction="闲聊二"),
    ]

    normalized = _normalize_tasks(tasks, "原始输入")

    assert [task.branch for task in normalized] == ["knowledge", "control", "chat"]
    assert normalized[1].instruction == "打开客厅灯；把空调调到26度"


def test_normalize_tasks_prioritizes_control_when_over_limit():
    tasks = [
        PlanTask(branch="knowledge", instruction=f"问题{i}", query=f"问题{i}")
        for i in range(settings.agent_max_plan_tasks)
    ]
    tasks.append(PlanTask(branch="control", instruction="打开客厅灯"))

    normalized = _normalize_tasks(tasks, "打开客厅灯")

    assert len(normalized) == settings.agent_max_plan_tasks
    assert normalized[0].branch == "control"


def test_route_after_plan_fans_out_one_send_per_task():
    state = {
        "user_input": "你好，顺便问下门锁规定",
        "request": _REQUEST,
        "plan": Plan(
            tasks=[
                PlanTask(branch="chat", instruction="打招呼"),
                PlanTask(branch="knowledge", instruction="门锁规定", query="门锁规定"),
            ]
        ).model_dump(),
    }

    sends = route_after_plan(state)

    assert [send.node for send in sends] == ["chat", "knowledge"]
    assert sends[0].arg["task"]["branch"] == "chat"
    assert sends[0].arg["request"]["role"] == "owner"
    assert "messages" not in sends[0].arg
    assert "results" not in sends[0].arg


def test_route_after_plan_asks_for_clarification_first():
    state = {
        "user_input": "把空调调到20度",
        "request": _REQUEST,
        "plan": Plan(
            tasks=[PlanTask(branch="chat", instruction="回应用户")],
            needs_clarification=True,
            clarification_question="要控制哪个房间？",
            clarification_options=["客厅", "卧室"],
        ).model_dump(),
    }

    assert route_after_plan(state) == "clarify"


def test_route_after_plan_stops_clarifying_at_limit():
    state = {
        "user_input": "把空调调到20度",
        "request": _REQUEST,
        "clarification_attempts": settings.agent_max_clarifications,
        "plan": Plan(
            tasks=[PlanTask(branch="chat", instruction="回应用户")],
            needs_clarification=True,
            clarification_question="要控制哪个房间？",
        ).model_dump(),
    }

    sends = route_after_plan(state)

    assert [send.node for send in sends] == ["chat"]


def test_route_after_plan_defaults_to_chat_without_tasks():
    sends = route_after_plan(
        {"user_input": "你好", "request": _REQUEST, "plan": {"tasks": []}}
    )

    assert [send.node for send in sends] == ["chat"]


def test_route_after_clarify_resumes_or_falls_back_to_chat():
    assert (
        route_after_clarify(
            {"clarification": {"answer": "客厅"}, "clarification_attempts": 1}
        )
        == "planner"
    )

    cancelled = route_after_clarify(
        {"clarification": {"cancelled": True}, "clarification_attempts": 1, "user_input": "算了"}
    )
    assert [send.node for send in cancelled] == ["chat"]

    exhausted = route_after_clarify(
        {"clarification": {"answer": "客厅"}, "clarification_attempts": settings.agent_max_clarifications}
    )
    assert [send.node for send in exhausted] == ["chat"]
