"""Agent WebSocket 事件映射测试：复用前端既有消息协议。"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from homemind.api import agent_chat


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))


class FakeApp:
    def __init__(self, events, values=None, interrupts=None):
        self.events = events
        self.values = values or {}
        self.interrupts = interrupts or []

    async def astream_events(self, graph_input, config, version):
        for event in self.events:
            yield event

    async def aget_state(self, config):
        tasks = [SimpleNamespace(interrupts=self.interrupts)] if self.interrupts else []
        return SimpleNamespace(values=self.values, tasks=tasks)


def _event(kind, node=None, data=None, name=None):
    return {
        "event": kind,
        "name": name or (node or "graph"),
        "data": data or {},
        "metadata": {"langgraph_node": node} if node else {},
    }


@pytest.mark.asyncio
async def test_stream_maps_nodes_tokens_tools_and_done(monkeypatch):
    events = [
        _event("on_chain_start", "planner"),
        _event("on_chain_end", "planner"),
        _event(
            "on_chat_model_stream",
            "planner",
            {"chunk": AIMessage(content="内部结构化输出不应透出")},
        ),
        _event("on_tool_start", "control", {"input": {}}, name="set_device_state"),
        _event("on_tool_end", "control", {"output": {}}, name="set_device_state"),
        _event("on_chain_start", "compose"),
        _event("on_chat_model_stream", "compose", {"chunk": AIMessage(content="客厅灯")}),
        _event("on_chat_model_stream", "compose", {"chunk": AIMessage(content="已打开。")}),
        _event("on_chain_end", "compose"),
    ]
    monkeypatch.setattr(
        agent_chat,
        "get_agent_app",
        lambda: FakeApp(
            events,
            values={
                "final_answer": "客厅灯已打开。",
                "avatar_emotion": "happy",
                "degraded": False,
                "request": {"session_id": "from-checkpoint"},
            },
        ),
    )

    websocket = FakeWebSocket()
    await agent_chat._stream_graph_events(
        websocket, {}, {"configurable": {"thread_id": "v2:1:2:s"}}, "client-session"
    )

    kinds = [item["type"] for item in websocket.sent]
    assert kinds[0] == "avatar_state"
    assert websocket.sent[0]["state"] == "thinking"

    tokens = [item["content"] for item in websocket.sent if item["type"] == "agent_token"]
    assert tokens == ["客厅灯", "已打开。"]
    assert "内部结构化输出不应透出" not in tokens

    steps = [item for item in websocket.sent if item["type"] == "agent_step"]
    assert any(step["node"] == "planner" and step["status"] == "completed" for step in steps)
    assert any(step["node"] == "tool:set_device_state" and step["status"] == "running" for step in steps)
    assert any(step["node"] == "tool:set_device_state" and step["status"] == "completed" for step in steps)

    done = websocket.sent[-1]
    assert done["type"] == "agent_done"
    assert done["content"] == "客厅灯已打开。"
    assert done["avatar_emotion"] == "happy"
    assert done["session_id"] == "from-checkpoint"
    assert done["model_warning"] is None


@pytest.mark.asyncio
async def test_stream_emits_interrupt_and_skips_done(monkeypatch):
    interrupt_value = {
        "type": "approval",
        "risk_level": "high",
        "question": "确认开锁吗？",
        "tasks": [{"task_id": "task_1", "risk_level": "high"}],
    }
    monkeypatch.setattr(
        agent_chat,
        "get_agent_app",
        lambda: FakeApp([], values={}, interrupts=[SimpleNamespace(value=interrupt_value)]),
    )

    websocket = FakeWebSocket()
    await agent_chat._stream_graph_events(
        websocket, {}, {"configurable": {"thread_id": "v2:1:2:s"}}, "session-x"
    )

    kinds = [item["type"] for item in websocket.sent]
    assert "agent_done" not in kinds
    interrupt = next(item for item in websocket.sent if item["type"] == "agent_interrupt")
    assert interrupt["interrupt"]["type"] == "approval"
    assert interrupt["interrupt"]["thread_id"] == "v2:1:2:s"
    assert websocket.sent[-1] == {"type": "avatar_state", "state": "idle"}


@pytest.mark.asyncio
async def test_stream_marks_degraded_answer(monkeypatch):
    monkeypatch.setattr(
        agent_chat,
        "get_agent_app",
        lambda: FakeApp(
            [],
            values={
                "final_answer": "规则兜底回复",
                "avatar_emotion": "idle",
                "degraded": True,
                "request": {"session_id": "s1"},
            },
        ),
    )
    websocket = FakeWebSocket()
    await agent_chat._stream_graph_events(
        websocket, {}, {"configurable": {"thread_id": "v2:1:2:s"}}, "s1"
    )
    done = websocket.sent[-1]
    assert done["type"] == "agent_done"
    assert done["model_warning"]


def test_agent_websocket_route_is_registered():
    from homemind.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/agent/v2/ws" in paths


def _minimal_ws_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(agent_chat.router, prefix="/api")
    return app


def test_websocket_transport_chat_and_ping(monkeypatch):
    from fastapi.testclient import TestClient

    identity = {"user_id": 1, "family_id": 2, "role": "owner"}

    async def fake_user(token=None):
        assert token == "test-token"
        return identity

    async def fake_build_state(payload, current_user, session_id):
        return {
            "request": {
                "user_id": current_user["user_id"],
                "family_id": current_user["family_id"],
                "role": current_user["role"],
                "session_id": session_id,
                "thread_id": f"v2:2:1:{session_id}",
            },
            "user_input": payload.message,
            "messages": [],
        }

    async def fake_save_conversation(**kwargs):
        return None

    fake_app = FakeApp(
        events=[
            _event("on_chain_start", "compose"),
            _event("on_chat_model_stream", "compose", {"chunk": AIMessage(content="你好")}),
            _event("on_chain_end", "compose"),
        ],
        values={
            "final_answer": "你好，我是小智。",
            "avatar_emotion": "caring",
            "degraded": False,
            "request": {**identity, "session_id": "ws-session"},
        },
    )
    monkeypatch.setattr(agent_chat, "current_user_payload_from_query", fake_user)
    monkeypatch.setattr(agent_chat, "get_agent_app", lambda: fake_app)
    monkeypatch.setattr(agent_chat, "_build_state", fake_build_state)
    monkeypatch.setattr(agent_chat, "save_conversation", fake_save_conversation)

    with (
        TestClient(_minimal_ws_app()) as client,
        client.websocket_connect("/api/agent/v2/ws?token=test-token") as ws,
    ):
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

        ws.send_json({"type": "chat", "message": "你好", "session_id": "ws-session"})
        received = []
        while True:
            message = ws.receive_json()
            received.append(message)
            if message["type"] in ("agent_done", "agent_interrupt", "agent_error"):
                break

    assert any(item["type"] == "agent_token" and item["content"] == "你好" for item in received)
    assert received[-1]["type"] == "agent_done"
    assert received[-1]["content"] == "你好，我是小智。"
    assert received[-1]["avatar_emotion"] == "caring"


def test_websocket_resume_requires_thread_id(monkeypatch):
    from fastapi.testclient import TestClient

    async def fake_user(token=None):
        return {"user_id": 1, "family_id": 2, "role": "owner"}

    monkeypatch.setattr(agent_chat, "current_user_payload_from_query", fake_user)
    monkeypatch.setattr(agent_chat, "get_agent_app", lambda: FakeApp([]))

    with (
        TestClient(_minimal_ws_app()) as client,
        client.websocket_connect("/api/agent/v2/ws?token=t") as ws,
    ):
        ws.send_json({"type": "resume", "resume_data": {"approved": True}})
        error = ws.receive_json()

    assert error["type"] == "agent_error"
    assert "thread_id" in error["content"]
