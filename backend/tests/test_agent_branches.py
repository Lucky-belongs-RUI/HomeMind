"""Agent 轻量分支测试：闲聊、知识检索与家庭报告（不依赖数据库与网络）。"""

import pytest

from homemind.agent.runtime import branches

_REQUEST = {"user_id": 1, "family_id": 2, "role": "owner"}


@pytest.mark.asyncio
async def test_knowledge_node_formats_context_and_sources(monkeypatch):
    async def fake_retrieve(**kwargs):
        assert kwargs["user_id"] == 1
        assert kwargs["family_id"] == 2
        return [
            {
                "content": "访客需登记。",
                "metadata": {"filename": "住户手册.pdf"},
                "score": 0.91,
            },
            {
                "content": "宠物需牵引。",
                "metadata": {"source": "社区规定"},
                "score": 0.82,
            },
        ]

    monkeypatch.setattr(branches, "retrieve_relevant_docs", fake_retrieve)
    result = await branches.knowledge_node(
        {"request": _REQUEST, "query": "访客规定"}
    )

    branch = result["results"][0]
    assert branch["success"] is True
    assert branch["data"]["context"].startswith("[1] 访客需登记。")
    assert [source["index"] for source in branch["sources"]] == [1, 2]
    assert branch["sources"][0]["source"] == "住户手册.pdf"


@pytest.mark.asyncio
async def test_knowledge_node_prefers_task_query(monkeypatch):
    async def fake_retrieve(**kwargs):
        assert kwargs["query"] == "访客登记规定"
        return []

    monkeypatch.setattr(branches, "retrieve_relevant_docs", fake_retrieve)
    result = await branches.knowledge_node(
        {
            "request": _REQUEST,
            "query": "打开客厅灯，顺便问下访客登记规定",
            "task": {"branch": "knowledge", "query": "访客登记规定"},
        }
    )

    assert result["results"][0]["success"] is True


@pytest.mark.asyncio
async def test_knowledge_node_handles_empty_and_missing_identity(monkeypatch):
    async def empty_retrieve(**kwargs):
        return []

    monkeypatch.setattr(branches, "retrieve_relevant_docs", empty_retrieve)
    empty = await branches.knowledge_node(
        {"request": _REQUEST, "query": "不存在的规定"}
    )
    assert empty["results"][0]["success"] is True
    assert "没有找到" in empty["results"][0]["summary"]

    missing = await branches.knowledge_node({"request": {}, "query": "规定"})
    assert missing["results"][0]["success"] is False
    assert "可信身份" in missing["results"][0]["summary"]


@pytest.mark.asyncio
async def test_knowledge_node_degrades_when_retrieval_fails(monkeypatch):
    async def broken_retrieve(**kwargs):
        raise RuntimeError("vector store down")

    monkeypatch.setattr(branches, "retrieve_relevant_docs", broken_retrieve)
    result = await branches.knowledge_node(
        {"request": _REQUEST, "query": "访客规定"}
    )

    assert result["results"][0]["success"] is False
    assert result["results"][0]["degraded"] is True


@pytest.mark.asyncio
async def test_report_node_summarizes_snapshot_without_db():
    snapshot = {
        "datetime": "2026-11-04 20:00",
        "weekday": "周三",
        "season": "秋季",
        "period": "晚上",
        "environment": {
            "indoor_temperature": 22.5,
            "indoor_humidity": 45,
            "air_quality": "优",
            "outdoor_temperature": 15,
            "weather": "晴",
        },
        "devices": [
            {
                "name": "客厅灯",
                "type": "light",
                "type_label": "灯",
                "room": "客厅",
                "status": {"power": "on"},
            }
        ],
    }

    result = await branches.report_node(
        {"request": _REQUEST, "house_snapshot": snapshot}
    )

    branch = result["results"][0]
    assert branch["branch"] == "report"
    assert branch["success"] is True
    assert "室内温度" in branch["data"]["context"]
    assert "客厅灯" in branch["data"]["context"]
    assert branch["data"]["snapshot"]["season"] == "秋季"


@pytest.mark.asyncio
async def test_chat_node_marks_emotional_care_tone():
    caring = await branches.chat_node(
        {"request": _REQUEST, "task": {"branch": "chat", "instruction": "我感冒了"}}
    )
    friendly = await branches.chat_node(
        {"request": _REQUEST, "task": {"branch": "chat", "instruction": "你好呀"}}
    )

    assert caring["results"][0]["data"]["tone"] == "caring"
    assert caring["results"][0]["summary"] == "用户需要情感陪伴"
    assert friendly["results"][0]["data"]["tone"] == "friendly"
