"""上下文工具测试：身份注入、画像与全屋快照按需读取。"""

import asyncio

from homemind.agent.tools.context_tools import get_house_snapshot, get_user_profile
from tests.db import memory_database, seed_household


def _state(family_id: int, user_id: int) -> dict:
    return {
        "request": {
            "family_id": family_id,
            "user_id": user_id,
            "role": "owner",
        }
    }


def test_context_tools_require_trusted_identity():
    async def scenario():
        assert (await get_house_snapshot.ainvoke({"state": {}}))["success"] is False
        assert (await get_user_profile.ainvoke({"state": {}}))["success"] is False

    asyncio.run(scenario())


def test_get_house_snapshot_reads_family_devices():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            result = await get_house_snapshot.ainvoke(
                {"state": _state(ids["family_id"], ids["user_id"])}
            )

            assert result["success"] is True
            assert result["snapshot"]["devices"][0]["type"] == "air_conditioner"
            assert result["snapshot"]["devices"][0]["room"] == "卧室"

    asyncio.run(scenario())


def test_get_user_profile_reads_database():
    async def scenario():
        async with memory_database():
            ids = await seed_household()
            result = await get_user_profile.ainvoke(
                {"state": _state(ids["family_id"], ids["user_id"])}
            )

            assert result["success"] is True
            assert isinstance(result["profile"], dict)

    asyncio.run(scenario())
