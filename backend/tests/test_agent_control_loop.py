"""控制子图闭环测试：ToolNode 注入身份、审批中断、失败反思重试。"""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from homemind.agent.runtime import control


def _state(**overrides):
    base = {
        "request": {
            "user_id": 42,
            "family_id": 7,
            "role": "owner",
            "thread_id": "control-thread",
        },
        "query": "把客厅灯打开",
        "task": {
            "branch": "control",
            "instruction": "把客厅灯打开",
            "query": "",
        },
        "house_snapshot": {
            "devices": [{"room": "客厅", "type": "light", "name": "客厅灯"}]
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def fake_tools(monkeypatch):
    calls: list[dict] = []
    results: list[dict] = []

    async def fake_execute_tool(tool_name, arguments, user_id, role, family_id):
        calls.append(
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "user_id": user_id,
                "role": role,
                "family_id": family_id,
            }
        )
        return results.pop(0) if results else {"success": True, "message": "操作成功"}

    async def no_llm_plan(state):
        return None

    monkeypatch.setattr(control, "_llm_tasks", no_llm_plan)
    monkeypatch.setattr("homemind.agent.tools.langchain_tools.execute_tool", fake_execute_tool)
    return calls, results


@pytest.mark.asyncio
async def test_control_loop_executes_tool_with_server_identity(fake_tools):
    calls, _ = fake_tools
    graph = control.build_control_subgraph()

    result = await graph.ainvoke(_state())

    assert result["results"][0]["success"] is True
    assert result["results"][0]["branch"] == "control"
    assert len(result["tool_events"]) == 1
    assert result["tool_events"][0]["tool"] == "set_device_state"
    assert calls[0]["user_id"] == 42
    assert calls[0]["role"] == "owner"
    assert calls[0]["family_id"] == 7
    assert calls[0]["arguments"] == {
        "room_name": "客厅",
        "device_type": "light",
        "attributes": {"power": "on"},
    }


@pytest.mark.asyncio
async def test_control_loop_executes_every_explicit_device(fake_tools):
    """灯与空调写在同一条输入里时，控制子图必须下发两个工具调用。"""
    calls, results = fake_tools
    results.extend(
        [
            {"success": True, "message": "卧室灯已调暗"},
            {"success": True, "message": "卧室空调已调到23度"},
        ]
    )
    graph = control.build_control_subgraph()

    result = await graph.ainvoke(
        _state(
            query="把卧室灯调暗，空调设置为23度",
            task={
                "branch": "control",
                "instruction": "把卧室灯调暗，空调设置为23度",
                "query": "",
            },
            house_snapshot={
                "devices": [
                    {"room": "卧室", "type": "light"},
                    {"room": "卧室", "type": "air_conditioner"},
                ]
            },
        )
    )

    assert {call["arguments"]["device_type"] for call in calls} == {
        "light",
        "air_conditioner",
    }
    assert result["results"][0]["success"] is True


@pytest.mark.asyncio
async def test_high_risk_device_waits_for_approval(fake_tools):
    calls, _ = fake_tools
    graph = control.build_control_subgraph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "control-approval"}}

    first = await graph.ainvoke(
        _state(
            query="把门锁解锁",
            task={
                "branch": "control",
                "instruction": "把门锁解锁",
                "query": "",
            },
            house_snapshot={"devices": [{"room": "大门", "type": "door_lock"}]},
        ),
        config=config,
    )

    assert calls == []
    interrupts = first["__interrupt__"]
    assert interrupts[0].value["type"] == "approval"
    assert interrupts[0].value["tasks"][0]["risk_level"] == "high"

    second = await graph.ainvoke(Command(resume={"approved": True}), config=config)
    assert second["results"][0]["success"] is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_denied_approval_cancels_without_execution(fake_tools):
    calls, _ = fake_tools
    graph = control.build_control_subgraph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "control-deny"}}

    await graph.ainvoke(
        _state(
            query="把门锁解锁",
            task={
                "branch": "control",
                "instruction": "把门锁解锁",
                "query": "",
            },
            house_snapshot={"devices": [{"room": "大门", "type": "door_lock"}]},
        ),
        config=config,
    )
    result = await graph.ainvoke(Command(resume={"approved": False}), config=config)

    assert calls == []
    assert result["results"][0]["success"] is False
    assert "取消" in result["results"][0]["summary"]


@pytest.mark.asyncio
async def test_approval_with_unmatched_task_ids_cancels(fake_tools):
    """approved=True 但选择的任务不存在时，不能静默当作“执行成功”。"""
    calls, _ = fake_tools
    graph = control.build_control_subgraph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "control-empty-approval"}}

    await graph.ainvoke(
        _state(
            query="把门锁解锁",
            task={
                "branch": "control",
                "instruction": "把门锁解锁",
                "query": "",
            },
            house_snapshot={"devices": [{"room": "大门", "type": "door_lock"}]},
        ),
        config=config,
    )
    result = await graph.ainvoke(
        Command(resume={"approved": True, "approved_task_ids": ["not-exist"]}),
        config=config,
    )

    assert calls == []
    assert result["results"][0]["success"] is False
    assert "所选操作" in result["results"][0]["summary"]


@pytest.mark.asyncio
async def test_retryable_failure_reflects_and_retries(fake_tools):
    calls, results = fake_tools
    results.extend(
        [
            {"success": False, "error": "设备网络超时"},
            {"success": True, "message": "重试后已打开"},
        ]
    )
    graph = control.build_control_subgraph()

    result = await graph.ainvoke(_state())

    assert len(calls) == 2
    # 子图对外只暴露 results/tool_events；重试通过两次工具事件体现
    assert len(result["tool_events"]) == 2
    assert result["results"][0]["success"] is True
    assert "重试后已打开" in result["results"][0]["summary"]


@pytest.mark.asyncio
async def test_non_retryable_failure_returns_degraded_result(fake_tools):
    calls, results = fake_tools
    results.append({"success": False, "error": "设备不存在"})
    graph = control.build_control_subgraph()

    result = await graph.ainvoke(_state())

    assert len(calls) == 1
    assert result["results"][0]["success"] is False
    assert result["results"][0]["degraded"] is True
    assert "设备不存在" in result["results"][0]["summary"]


@pytest.mark.asyncio
async def test_visitor_write_is_denied_before_tool_execution(fake_tools):
    calls, _ = fake_tools
    graph = control.build_control_subgraph()

    result = await graph.ainvoke(
        _state(request={"user_id": 9, "family_id": 7, "role": "visitor"})
    )

    assert calls == []
    assert result["results"][0]["success"] is False
    assert "访客" in result["results"][0]["summary"]
