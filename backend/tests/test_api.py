"""HTTP 接口集成测试（ASGI 直连 + 内存 SQLite，无外部依赖）。

覆盖路由注册、鉴权依赖、响应模型过滤、家庭隔离与领域异常转译。
Agent 对话链路依赖真实模型，不在本文件覆盖（由 evals/e2e.py 负责）。

每个用例用不同的模拟客户端 IP，避免注册限流（单 IP 5 次/小时）互相干扰。
"""

import asyncio

import httpx

from tests.db import memory_database


async def _client(ip: str):
    from homemind.api import deps
    from homemind.main import app

    # 内存库每个用例都重启，user_id 会从 1 开始；清掉身份 TTL 缓存避免串库
    deps._identity_cache.clear()
    transport = httpx.ASGITransport(app=app, client=(ip, 12345))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _register(client: httpx.AsyncClient, username: str, family_name: str = "测试家庭"):
    response = await client.post(
        "/api/auth/register",
        json={
            "family_name": family_name,
            "username": username,
            "password": "secret-123",
            "nickname": "测试房主",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["token"], body["user"]["family_id"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_auth_flow():
    async def scenario():
        async with memory_database(), await _client("10.10.0.1") as client:
            health = await client.get("/")
            assert health.status_code == 200
            assert health.json()["status"] == "running"

            token, family_id = await _register(client, "api_owner_1")
            headers = _headers(token)

            me = await client.get("/api/auth/me", headers=headers)
            assert me.status_code == 200
            assert me.json()["role"] == "owner"
            assert me.json()["family_id"] == family_id

            unauthorized = await client.get("/api/auth/me")
            assert unauthorized.status_code == 401

            created = await client.post(
                "/api/auth/sub-account",
                headers=headers,
                json={
                    "username": "api_resident_1",
                    "password": "resident-123",
                    "nickname": "测试住户",
                    "role": "resident",
                },
            )
            assert created.status_code == 200
            assert created.json()["role"] == "resident"

            login = await client.post(
                "/api/auth/login",
                json={"username": "api_resident_1", "password": "resident-123"},
            )
            assert login.status_code == 200
            assert login.json()["user"]["role"] == "resident"

            changed = await client.put(
                "/api/auth/password",
                headers=headers,
                json={"old_password": "secret-123", "new_password": "secret-456"},
            )
            assert changed.status_code == 200

            old_login = await client.post(
                "/api/auth/login",
                json={"username": "api_owner_1", "password": "secret-123"},
            )
            assert old_login.status_code == 401

            new_login = await client.post(
                "/api/auth/login",
                json={"username": "api_owner_1", "password": "secret-456"},
            )
            assert new_login.status_code == 200
            assert new_login.json()["token"]

    asyncio.run(scenario())


def test_room_device_scene_lifecycle():
    async def scenario():
        async with memory_database(), await _client("10.10.0.2") as client:
            token, _ = await _register(client, "api_owner_2")
            headers = _headers(token)

            room = await client.post(
                "/api/rooms", headers=headers, json={"name": "客厅", "icon": "sofa"}
            )
            assert room.status_code == 200, room.text
            room_id = room.json()["id"]

            rooms = await client.get("/api/rooms", headers=headers)
            assert [item["name"] for item in rooms.json()] == ["客厅"]
            assert rooms.json()[0]["device_count"] == 0

            device = await client.post(
                "/api/devices",
                headers=headers,
                json={"name": "客厅灯", "type": "light", "room_id": room_id},
            )
            assert device.status_code == 200, device.text
            device_id = device.json()["id"]

            in_room = await client.get(f"/api/devices/room/{room_id}", headers=headers)
            assert [item["id"] for item in in_room.json()] == [device_id]

            detail = await client.get(f"/api/rooms/{room_id}", headers=headers)
            assert detail.json()["devices"][0]["name"] == "客厅灯"

            patched = await client.patch(
                f"/api/devices/{device_id}/status",
                headers=headers,
                json={"attributes": {"power": "on", "brightness": 80}},
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["status"]["power"] == "on"

            logs = await client.get(f"/api/devices/logs/{device_id}", headers=headers)
            assert logs.status_code == 200
            assert len(logs.json()) >= 1

            invalid_status = await client.patch(
                f"/api/devices/{device_id}/status",
                headers=headers,
                json={"attributes": {"nested": {"bad": True}}},
            )
            assert invalid_status.status_code == 422

            scene = await client.post(
                "/api/scenes",
                headers=headers,
                json={
                    "name": "回家模式",
                    "actions": {"actions": [{"device_id": device_id, "attributes": {"power": "on"}}]},
                },
            )
            assert scene.status_code == 200, scene.text
            scene_id = scene.json()["id"]

            executed = await client.post("/api/scenes/回家模式/execute", headers=headers)
            assert executed.status_code == 200, executed.text
            assert executed.json()["success"] is True
            assert executed.json()["failed_count"] == 0

            renamed_room = await client.put(
                f"/api/rooms/{room_id}", headers=headers, json={"name": "大客厅"}
            )
            assert renamed_room.json()["name"] == "大客厅"

            renamed_device = await client.put(
                f"/api/devices/{device_id}", headers=headers, json={"name": "主灯"}
            )
            assert renamed_device.json()["name"] == "主灯"

            updated_scene = await client.put(
                f"/api/scenes/{scene_id}", headers=headers, json={"description": "下班回家"}
            )
            assert updated_scene.json()["description"] == "下班回家"

            assert (
                await client.delete(f"/api/devices/{device_id}", headers=headers)
            ).status_code == 200
            assert (await client.get(f"/api/devices/{device_id}", headers=headers)).status_code == 404
            assert (await client.delete(f"/api/scenes/{scene_id}", headers=headers)).status_code == 200
            assert (await client.delete(f"/api/rooms/{room_id}", headers=headers)).status_code == 200
            assert (await client.get(f"/api/rooms/{room_id}", headers=headers)).status_code == 404

    asyncio.run(scenario())


def test_family_isolation_and_permissions():
    async def scenario():
        async with memory_database(), await _client("10.10.0.3") as owner_client:
            token_a, family_a = await _register(owner_client, "api_owner_a", "A 家庭")
            headers_a = _headers(token_a)

            room_a = await owner_client.post(
                "/api/rooms", headers=headers_a, json={"name": "书房"}
            )
            room_a_id = room_a.json()["id"]

            async with await _client("10.10.0.4") as client_b:
                token_b, family_b = await _register(client_b, "api_owner_b", "B 家庭")
                headers_b = _headers(token_b)
                await client_b.post("/api/rooms", headers=headers_b, json={"name": "B 客厅"})

                # 家庭隔离：A 的 token 不能读取 B 的家庭
                denied = await owner_client.get(f"/api/families/{family_b}", headers=headers_a)
                assert denied.status_code == 403
                assert (
                    await owner_client.get(f"/api/rooms/{room_a_id}", headers=headers_a)
                ).status_code == 200

                overview = await client_b.get("/api/families", headers=headers_b)
                assert [item["id"] for item in overview.json()] == [family_b]
                assert overview.json()[0]["rooms_count"] == 1

                cross_room = await client_b.get(f"/api/rooms/{room_a_id}", headers=headers_b)
                assert cross_room.status_code == 403 or cross_room.status_code == 404

            # 访客只读：不能创建房间
            await owner_client.post(
                "/api/auth/sub-account",
                headers=headers_a,
                json={
                    "username": "api_guest_a",
                    "password": "guest-123",
                    "nickname": "访客",
                    "role": "guest",
                },
            )
            guest_login = await owner_client.post(
                "/api/auth/login",
                json={"username": "api_guest_a", "password": "guest-123"},
            )
            guest_headers = _headers(guest_login.json()["token"])
            assert (
                await owner_client.get("/api/devices", headers=guest_headers)
            ).status_code == 200
            forbidden = await owner_client.post(
                "/api/rooms", headers=guest_headers, json={"name": "访客的房间"}
            )
            assert forbidden.status_code == 403

            members = await owner_client.get(f"/api/families/{family_a}/users", headers=headers_a)
            assert {item["role"] for item in members.json()} == {"owner", "guest"}

            renamed = await owner_client.put(
                f"/api/families/{family_a}", headers=headers_a, json={"name": "A 新家"}
            )
            assert renamed.json()["name"] == "A 新家"

            created = await owner_client.post(
                "/api/families",
                headers=headers_a,
                json={"name": "C 家庭", "owner_username": "api_owner_c", "owner_nickname": "房主C"},
            )
            assert created.status_code == 200
            assert created.json()["owner_username"] == "api_owner_c"

            # 新家庭有独立房主账户（默认密码 123456），只能由该房主删除
            owner_c_login = await owner_client.post(
                "/api/auth/login",
                json={"username": "api_owner_c", "password": "123456"},
            )
            assert owner_c_login.status_code == 200
            deleted = await owner_client.delete(
                f"/api/families/{created.json()['family_id']}",
                headers=_headers(owner_c_login.json()["token"]),
            )
            assert deleted.status_code == 200

    asyncio.run(scenario())


def test_agent_environment_and_history():
    async def scenario():
        async with memory_database(), await _client("10.10.0.5") as client:
            token, _ = await _register(client, "api_owner_5")
            headers = _headers(token)

            environment = await client.get("/api/agent/environment", headers=headers)
            assert environment.status_code == 200, environment.text
            assert "indoor_temperature" in environment.json()

            history = await client.get(
                "/api/agent/history", headers=headers, params={"session_id": "api-session-1"}
            )
            assert history.status_code == 200
            assert history.json()["session_id"] == "api-session-1"
            assert history.json()["messages"] == []

    asyncio.run(scenario())
