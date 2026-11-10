"""Agent HTTP 接口测试：鉴权、租户隔离、中断恢复与 SSE 事件。

用内存 SQLite 与 Fake Graph 替换真实模型，验证 API 层的合同，不触发网络调用。
"""

import asyncio
import json
from types import SimpleNamespace

import httpx
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from homemind.agent.runtime.graph import build_agent_graph
from homemind.agent.runtime.schemas import Plan, PlanTask
from tests.db import memory_database


async def _client(ip: str):
    from homemind.api import deps
    from homemind.main import app

    deps._identity_cache.clear()
    transport = httpx.ASGITransport(app=app, client=(ip, 12345))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _register(client: httpx.AsyncClient, username: str):
    response = await client.post(
        "/api/auth/register",
        json={
            "family_name": "v2 测试家庭",
            "username": username,
            "password": "secret-123",
            "nickname": "测试房主",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["token"], body["user"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeAgentApp:
    def __init__(self, result=None, values=None, events=None):
        self.result = result or {}
        self.values = values if values is not None else {}
        self.events = events or []
        self.calls = []

    async def aget_state(self, config):
        return SimpleNamespace(values=self.values, tasks=[])

    async def ainvoke(self, state, config=None):
        self.calls.append((state, config))
        return self.result

    async def astream_events(self, state, config, version):
        for event in self.events:
            yield event


def _patch_app(monkeypatch, fake):
    from homemind.api import agent_chat

    monkeypatch.setattr(agent_chat, "get_agent_app", lambda: fake)


def test_agent_chat_returns_answer_and_server_identity(monkeypatch):
    async def scenario():
        async with memory_database(), await _client("10.20.0.1") as client:
            token, user = await _register(client, "v2_owner_1")

            fake = FakeAgentApp(
                result={
                    "final_answer": "客厅灯已打开。",
                    "avatar_emotion": "happy",
                    "degraded": False,
                }
            )
            _patch_app(monkeypatch, fake)

            response = await client.post(
                "/api/agent/v2/chat",
                headers=_headers(token),
                json={
                    "message": "打开客厅灯",
                    "session_id": "v2-session-1",
                    "permission_mode": "high",
                },
            )

            assert response.status_code == 200, response.text
            body = response.json()
            assert body["response"] == "客厅灯已打开。"
            assert body["avatar_emotion"] == "happy"
            assert body["thread_id"] == f"v2:{user['family_id']}:{user['id']}:v2-session-1"

            state, config = fake.calls[0]
            assert state["request"]["user_id"] == user["id"]
            assert state["request"]["family_id"] == user["family_id"]
            assert state["request"]["role"] == "owner"
            assert config["configurable"]["thread_id"] == body["thread_id"]

    asyncio.run(scenario())


def test_agent_chat_requires_authentication():
    async def scenario():
        async with memory_database(), await _client("10.20.0.2") as client:
            response = await client.post("/api/agent/v2/chat", json={"message": "你好"})
            assert response.status_code == 401

    asyncio.run(scenario())


def test_agent_resume_rejects_other_users_thread(monkeypatch):
    async def scenario():
        async with memory_database(), await _client("10.20.0.3") as client:
            token, user = await _register(client, "v2_owner_2")
            fake = FakeAgentApp(
                result={"final_answer": "不应执行"},
                values={"request": {"user_id": user["id"] + 999, "family_id": user["family_id"]}},
            )
            _patch_app(monkeypatch, fake)

            response = await client.post(
                "/api/agent/v2/resume",
                headers=_headers(token),
                json={
                    "thread_id": f"v2:{user['family_id']}:{user['id']}:v2-session-2",
                    "resume_data": {"approved": True},
                },
            )
            assert response.status_code == 403, response.text
            assert fake.calls == []

    asyncio.run(scenario())


def test_agent_resume_returns_interrupt_payload(monkeypatch):
    async def scenario():
        async with memory_database(), await _client("10.20.0.4") as client:
            token, user = await _register(client, "v2_owner_3")
            fake = FakeAgentApp(values={"request": {"user_id": user["id"], "family_id": user["family_id"]}})
            fake_result = {
                "__interrupt__": [
                    SimpleNamespace(
                        value={
                            "type": "approval",
                            "question": "确认开锁吗？",
                            "tasks": [{"task_id": "task_1"}],
                        }
                    )
                ]
            }
            fake.result = fake_result
            _patch_app(monkeypatch, fake)

            response = await client.post(
                "/api/agent/v2/resume",
                headers=_headers(token),
                json={
                    "thread_id": f"v2:{user['family_id']}:{user['id']}:v2-session-3",
                    "resume_data": {"approved": True},
                },
            )

            assert response.status_code == 200, response.text
            body = response.json()
            assert body["response"] is None
            assert body["interrupt"]["type"] == "approval"
            assert body["interrupt"]["thread_id"].startswith("v2:")

    asyncio.run(scenario())


def test_agent_second_turn_does_not_reuse_previous_turn_state(monkeypatch):
    """同一个 session 第二轮不能带上一轮的 results/final_answer（曾经第二轮直接复述上一轮）。"""
    from homemind.agent.runtime import control as control_module
    from homemind.agent.runtime import graph as graph_module
    from homemind.agent.runtime import nodes as nodes_module
    from homemind.agent.tools import langchain_tools as tools_module

    async def scenario():
        contexts: list[str] = []

        class _ContextEchoModel:
            async def astream(self, messages):
                contexts.append(messages[0].content)
                yield AIMessage(content="好的。")

            async def ainvoke(self, messages):
                contexts.append(messages[0].content)
                return AIMessage(content="好的。")

        async def fake_planner(state):
            text = str(state.get("user_input") or "")
            if "灯" in text:
                tasks = [
                    PlanTask(branch="control", instruction="打开客厅灯"),
                ]
            else:
                tasks = [
                    PlanTask(branch="chat", instruction="日常交流"),
                ]
            return {
                "plan": Plan(tasks=tasks).model_dump(),
                "avatar_emotion": "thinking",
                # 真实 planner 会按需加载快照；这里替换了节点，直接给出最小快照
                "house_snapshot": {"devices": [{"room": "客厅", "type": "light"}]},
            }

        async def no_llm_plan(_state):
            return None

        async def fake_execute_tool(tool_name, arguments, user_id, role, family_id):
            return {"success": True, "message": "客厅灯已打开"}

        async def fake_save_conversation(**kwargs):
            return None

        monkeypatch.setattr(graph_module, "plan_node", fake_planner)
        monkeypatch.setattr(control_module, "_llm_tasks", no_llm_plan)
        monkeypatch.setattr(tools_module, "execute_tool", fake_execute_tool)
        monkeypatch.setattr(nodes_module, "build_response_model", lambda *a, **k: _ContextEchoModel())
        monkeypatch.setattr(nodes_module, "save_conversation", fake_save_conversation)

        graph_module.set_agent_app(build_agent_graph(checkpointer=MemorySaver()))
        try:
            async with memory_database(), await _client("10.20.0.6") as client:
                token, user = await _register(client, "v2_owner_turns")

                from homemind.models.device import Device
                from homemind.models.room import Room
                from homemind.repositories import default_status, unit_of_work

                async with unit_of_work() as uow:
                    room = await uow.rooms.add(
                        Room(
                            family_id=user["family_id"],
                            name="客厅",
                            icon="living",
                            sort_order=1,
                        )
                    )
                    await uow.devices.add(
                        Device(
                            family_id=user["family_id"],
                            name="客厅灯",
                            type="light",
                            room_id=room.id,
                            status=default_status("light"),
                        )
                    )
                    await uow.commit()

                first = await client.post(
                    "/api/agent/v2/chat",
                    headers=_headers(token),
                    json={"message": "打开客厅灯", "session_id": "two-turns"},
                )
                assert first.status_code == 200, first.text

                second = await client.post(
                    "/api/agent/v2/chat",
                    headers=_headers(token),
                    json={"message": "你好", "session_id": "two-turns"},
                )
                assert second.status_code == 200, second.text
        finally:
            graph_module.set_agent_app(None)

        assert "本轮已执行：" in contexts[0]
        assert "客厅灯已打开" in contexts[0]
        assert "本轮已执行：\n无" in contexts[1]
        assert "客厅灯已打开" not in contexts[1]

    asyncio.run(scenario())


def test_agent_stream_emits_tokens_and_done(monkeypatch):
    async def scenario():
        async with memory_database(), await _client("10.20.0.5") as client:
            token, user = await _register(client, "v2_owner_4")
            fake = FakeAgentApp(
                values={
                    "final_answer": "流式答案",
                    "avatar_emotion": "caring",
                    "degraded": False,
                    "request": {"user_id": user["id"], "family_id": user["family_id"]},
                },
                events=[
                    {
                        "event": "on_chat_model_stream",
                        "data": {"chunk": AIMessage(content='{"intents": []}')},
                        "metadata": {"langgraph_node": "planner"},
                    },
                    {
                        "event": "on_chat_model_stream",
                        "data": {"chunk": AIMessage(content="流式")},
                        "metadata": {"langgraph_node": "compose"},
                    },
                    {
                        "event": "on_chain_start",
                        "data": {},
                        "metadata": {"langgraph_node": "compose"},
                    },
                ],
            )
            _patch_app(monkeypatch, fake)

            response = await client.post(
                "/api/agent/v2/chat/stream",
                headers=_headers(token),
                json={"message": "你好", "session_id": "v2-stream-1"},
            )

            assert response.status_code == 200, response.text
            assert response.headers["content-type"].startswith("text/event-stream")

            events = [
                json.loads(line.removeprefix("data: "))
                for line in response.text.splitlines()
                if line.startswith("data: ")
            ]
            kinds = [event["type"] for event in events]
            assert kinds[0] == "run_started"
            assert "token" in kinds
            # 只有 compose 的 token 进入聊天流，路由模型输出不能泄漏
            tokens = [event["content"] for event in events if event["type"] == "token"]
            assert tokens == ["流式"]
            assert kinds[-1] == "done"
            assert events[-1]["response"] == "流式答案"

    asyncio.run(scenario())
