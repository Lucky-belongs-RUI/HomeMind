"""Agent 控制子图的规划、校验、观察与验证（不触网、不连库）。"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from homemind.agent.runtime import control as C


def _state(**overrides):
    base = {
        "request": {
            "user_id": 1,
            "family_id": 1,
            "role": "resident",
            "thread_id": "v2:1:1:s1",
        },
        "query": "打开客厅的灯",
        "task": {
            "branch": "control",
            "instruction": "打开客厅的灯",
            "query": "",
        },
        "house_snapshot": {
            "devices": [
                {"type": "light", "room": "客厅", "status": {"power": "off"}},
                {"type": "door_lock", "room": "玄关", "status": {"locked": True}},
            ]
        },
        "tasks": [],
        "observations": [],
        "results": [],
        "tool_events": [],
        "retry_count": 0,
    }
    base.update(overrides)
    return base


def test_rule_planner_maps_device_control():
    tasks = C._rule_tasks(_state())
    assert len(tasks) == 1
    assert tasks[0].tool == "set_device_state"
    assert tasks[0].arguments["room_name"] == "客厅"


def test_rule_planner_maps_time_and_weather_tools():
    for tool_name, text in (
        ("get_current_time", "现在几点了"),
        ("get_weather", "今天天气怎么样"),
    ):
        tasks = C._rule_tasks(
            _state(query=text, task={"branch": "control", "instruction": text})
        )
        assert len(tasks) == 1
        assert tasks[0].tool == tool_name
        assert tasks[0].arguments == {}


def test_rule_planner_reads_full_query_for_multiple_devices():
    """主图把 control 任务收窄成一句时，规则规划仍要覆盖整轮输入。"""
    state = _state(
        query="把卧室灯调暗，空调设置为23度",
        task={"branch": "control", "instruction": "把卧室灯调暗"},
        house_snapshot={
            "devices": [
                {"type": "light", "room": "卧室"},
                {"type": "air_conditioner", "room": "卧室"},
            ]
        },
    )

    tasks = C._rule_tasks(state)

    by_type = {task.arguments["device_type"]: task.arguments["attributes"] for task in tasks}
    assert by_type == {"light": {"brightness": 30}, "air_conditioner": {"temperature": 23}}


def test_rule_planner_does_not_execute_knowledge_question():
    """“打开空调费电吗”是知识问题，不能因为出现动作词就真的开空调。"""
    state = _state(
        query="把卧室灯调暗，顺便讲讲打开空调费电吗",
        task={"branch": "control", "instruction": "把卧室灯调暗"},
        house_snapshot={
            "devices": [
                {"type": "light", "room": "卧室"},
                {"type": "air_conditioner", "room": "卧室"},
            ]
        },
    )

    tasks = C._rule_tasks(state)

    assert [task.arguments["device_type"] for task in tasks] == ["light"]


def test_rule_planner_maps_scene_and_query():
    scene = C._rule_tasks(
        _state(query="我要回家了", task={"branch": "control", "instruction": "我要回家了"})
    )
    assert scene[0].tool == "trigger_scene"
    assert scene[0].arguments["scene_name"] == "回家模式"

    query = C._rule_tasks(
        _state(
            query="客厅灯现在是什么状态",
            task={"branch": "control", "instruction": "客厅灯现在是什么状态"},
        )
    )
    assert query[0].tool == "get_device_state"


class _FakeToolCallingModel:
    def __init__(self, tool_calls):
        self._tool_calls = tool_calls

    def bind_tools(self, tools):
        self._bound_tools = list(tools)
        return self

    async def ainvoke(self, _messages):
        return SimpleNamespace(tool_calls=self._tool_calls)


@pytest.mark.asyncio
async def test_planner_binds_control_tools(monkeypatch):
    model = _FakeToolCallingModel([])
    monkeypatch.setattr(C, "build_chat_model", lambda **_: model)

    await C._llm_tasks(_state())
    assert [tool.name for tool in model._bound_tools] == list(C.CONTROL_TOOL_NAMES)


@pytest.mark.asyncio
async def test_planner_converts_tool_calls_to_tasks(monkeypatch):
    model = _FakeToolCallingModel(
        [
            {
                "name": "set_device_state",
                "args": {
                    "room_name": "客厅",
                    "device_type": "light",
                    "attributes": {"power": "on"},
                },
                "id": "call_1",
                "type": "tool_call",
            }
        ]
    )
    monkeypatch.setattr(C, "build_chat_model", lambda **_: model)

    tasks = await C._llm_tasks(_state())
    assert tasks is not None
    assert tasks[0].tool == "set_device_state"
    assert tasks[0].arguments["attributes"] == {"power": "on"}


@pytest.mark.asyncio
async def test_plan_falls_back_when_llm_invents_tool(monkeypatch):
    """模型臆造 control_device 等工具名时必须回退规则规划，而不是直接取消。"""
    model = _FakeToolCallingModel(
        [
            {
                "name": "control_device",
                "args": {"room_name": "客厅", "device_type": "light"},
                "id": "call_1",
                "type": "tool_call",
            }
        ]
    )
    monkeypatch.setattr(C, "build_chat_model", lambda **_: model)

    assert await C._llm_tasks(_state()) is None
    result = await C.plan_node(_state())
    assert result["plan_ready"] is True
    assert result["tasks"][0]["tool"] == "set_device_state"


@pytest.mark.asyncio
async def test_plan_falls_back_when_llm_arguments_incomplete(monkeypatch):
    model = _FakeToolCallingModel(
        [
            {
                "name": "set_device_state",
                "args": {"device_type": "light"},
                "id": "call_1",
                "type": "tool_call",
            }
        ]
    )
    monkeypatch.setattr(C, "build_chat_model", lambda **_: model)

    result = await C.plan_node(_state())
    assert result["tasks"][0]["tool"] == "set_device_state"
    assert result["tasks"][0]["arguments"]["room_name"] == "客厅"


@pytest.mark.asyncio
async def test_plan_merges_explicit_devices_missing_from_llm_plan(monkeypatch):
    """模型只规划了灯时，规则层必须补上用户明确要求的空调温度。"""
    model = _FakeToolCallingModel(
        [
            {
                "name": "set_device_state",
                "args": {
                    "room_name": "卧室",
                    "device_type": "light",
                    "attributes": {"brightness": 30},
                },
                "id": "call_1",
                "type": "tool_call",
            }
        ]
    )
    monkeypatch.setattr(C, "build_chat_model", lambda **_: model)

    state = _state(
        query="把卧室灯调暗，空调设置为23度",
        task={"branch": "control", "instruction": "把卧室灯调暗"},
        house_snapshot={
            "devices": [
                {"type": "light", "room": "卧室"},
                {"type": "air_conditioner", "room": "卧室"},
            ]
        },
    )
    result = await C.plan_node(state)

    tasks = result["tasks"]
    assert len(tasks) == 2
    by_type = {task["arguments"]["device_type"]: task["arguments"]["attributes"] for task in tasks}
    assert by_type["air_conditioner"] == {"temperature": 23}
    assert [task["task_id"] for task in tasks] == ["task_1", "task_2"]


@pytest.mark.asyncio
async def test_plan_drops_implicit_scene_when_explicit_write_exists(monkeypatch):
    model = _FakeToolCallingModel(
        [
            {
                "name": "trigger_scene",
                "args": {"scene_name": "睡眠模式"},
                "id": "call_1",
                "type": "tool_call",
            },
            {
                "name": "set_device_state",
                "args": {
                    "room_name": "卧室",
                    "device_type": "air_conditioner",
                    "attributes": {"temperature": 23},
                },
                "id": "call_2",
                "type": "tool_call",
            },
        ]
    )
    monkeypatch.setattr(C, "build_chat_model", lambda **_: model)

    state = _state(
        query="我想睡觉了，空调设置为23度",
        task={"branch": "control", "instruction": "我想睡觉了，空调设置为23度"},
        house_snapshot={"devices": [{"type": "air_conditioner", "room": "卧室"}]},
    )
    result = await C.plan_node(state)

    assert [task["tool"] for task in result["tasks"]] == ["set_device_state"]


@pytest.mark.asyncio
async def test_plan_node_deduplicates_and_sets_idempotency(monkeypatch):
    async def no_llm(_state):
        return None

    monkeypatch.setattr(C, "_llm_tasks", no_llm)
    result = await C.plan_node(_state())
    assert result["plan_ready"] is True
    assert result["tasks"][0]["idempotency_key"]


@pytest.mark.asyncio
async def test_validate_rejects_unknown_room_device():
    state = _state(
        tasks=[
            {
                "task_id": "task_1",
                "tool": "set_device_state",
                "arguments": {
                    "room_name": "车库",
                    "device_type": "light",
                    "attributes": {"power": "on"},
                },
            }
        ]
    )
    result = await C.validate_node(state)
    assert result["plan_ready"] is False
    assert "未找到" in result["last_error"]


@pytest.mark.asyncio
async def test_validate_rejects_device_task_when_snapshot_empty():
    """快照为空时不能静默跳过设备存在性校验。"""
    state = _state(
        house_snapshot={"devices": []},
        tasks=[
            {
                "task_id": "task_1",
                "tool": "set_device_state",
                "arguments": {
                    "room_name": "客厅",
                    "device_type": "light",
                    "attributes": {"power": "on"},
                },
            }
        ],
    )
    result = await C.validate_node(state)

    assert result["plan_ready"] is False
    assert "设备列表为空" in result["last_error"]


@pytest.mark.asyncio
async def test_validate_marks_low_risk_as_allow():
    state = _state(
        tasks=[
            {
                "task_id": "task_1",
                "tool": "set_device_state",
                "arguments": {
                    "room_name": "客厅",
                    "device_type": "light",
                    "attributes": {"power": "on"},
                },
            }
        ]
    )
    result = await C.validate_node(state)
    assert result["plan_ready"] is True
    assert result["policy_action"] == "allow"
    assert result["tasks"][0]["risk_level"] == "low"


@pytest.mark.asyncio
async def test_validate_escalates_door_lock_to_approval():
    state = _state(
        tasks=[
            {
                "task_id": "task_1",
                "tool": "set_device_state",
                "arguments": {
                    "room_name": "玄关",
                    "device_type": "door_lock",
                    "attributes": {"locked": False},
                },
            }
        ]
    )
    result = await C.validate_node(state)
    assert result["policy_action"] == "approval"
    assert result["tasks"][0]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_set_device_state_rejects_invalid_attributes():
    """Agent 工具路径必须和 HTTP 接口共用同一套状态字段校验。"""
    from homemind.agent.tools.device_tools import _tool_set_device_state

    result = await _tool_set_device_state(
        {
            "room_name": "客厅",
            "device_type": "light",
            "attributes": {"brightness": "很亮"},
        },
        user_id=1,
        user_role="owner",
        family_id=1,
    )
    assert result["success"] is False
    assert "不合法" in result["error"]


def test_numeric_attributes_accept_degree_and_percent_suffix():
    from homemind.agent.tools.device_tools import _coerce_numeric_attributes

    coerced = _coerce_numeric_attributes(
        {"temperature": "23°", "brightness": "30%", "position": " 50度 ", "mode": "cool"}
    )

    assert coerced == {
        "temperature": 23,
        "brightness": 30,
        "position": 50,
        "mode": "cool",
    }


@pytest.mark.asyncio
async def test_observe_maps_tool_message_to_task():
    state = _state(
        tasks=[
            {
                "task_id": "task_1",
                "tool": "set_device_state",
                "arguments": {"room_name": "客厅", "device_type": "light"},
            }
        ],
        messages=[
            ToolMessage(
                content=json.dumps({"success": True, "message": "已打开客厅灯"}),
                tool_call_id="call_task_1",
            )
        ],
    )
    result = await C.observe_node(state)
    assert result["observations"][0]["task_id"] == "task_1"
    assert result["observations"][0]["success"] is True
    assert result["tool_events"][0]["tool"] == "set_device_state"


@pytest.mark.asyncio
async def test_verify_success_and_failure():
    tasks = [{"task_id": "task_1", "tool": "set_device_state", "description": "开灯"}]
    success = await C.verify_node(
        _state(
            tasks=tasks,
            observations=[{"task_id": "task_1", "success": True, "result": {"message": "已开灯"}}],
        )
    )
    assert success["results"][0]["success"] is True

    failure = await C.verify_node(
        _state(
            tasks=tasks,
            observations=[{"task_id": "task_1", "success": False, "error": "设备离线"}],
        )
    )
    assert failure["results"][0]["success"] is False


def test_control_routing_is_pure():
    state = _state(plan_ready=True, policy_action="approval", approval_granted=False)
    snapshot = dict(state)
    assert C.route_after_validate(state) == "approval"
    assert C.route_after_approval(state) == "cancel"
    assert state == snapshot
