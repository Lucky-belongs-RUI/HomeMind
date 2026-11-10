"""会话上下文两级压缩的纯函数测试（不依赖数据库与网络）。"""

import asyncio

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from homemind.agent.runtime.compression import KEEP_RECENT_TURNS, build_history_window


def _rows(turns: int) -> list[tuple[int, BaseMessage]]:
    rows: list[tuple[int, BaseMessage]] = []
    index = 1
    for turn in range(turns):
        rows.append((index, HumanMessage(content=f"问题{turn}")))
        index += 1
        rows.append((index, AIMessage(content=f"回答{turn}")))
        index += 1
    return rows


def _no_compress():
    async def compressor(text: str, limit: int) -> str:
        raise AssertionError("不应触发压缩")

    return compressor


def test_within_budget_keeps_all_turns_and_no_summary():
    rows = _rows(10)
    window = asyncio.run(
        build_history_window(
            rows,
            HumanMessage(content="本轮"),
            [],
            None,
            10_000,
            level1=_no_compress(),
            level2=_no_compress(),
        )
    )

    assert window.compressed is False
    assert window.messages[:-1] == [message for _, message in rows]
    assert window.messages[-1].content == "本轮"
    assert window.parts == []
    assert window.summary == ""
    assert window.usage["compressed_turns"] == 0


def test_over_budget_compresses_only_turns_older_than_six():
    rows = _rows(10)
    calls: list[tuple[str, str, int]] = []

    async def level1(text: str, limit: int) -> str:
        calls.append(("level1", text, limit))
        return "一级精简摘要"

    async def level2(text: str, limit: int) -> str:
        calls.append(("level2", text, limit))
        return "不应调用"

    window = asyncio.run(
        build_history_window(
            rows,
            HumanMessage(content="本轮"),
            [],
            None,
            budget=1,
            level1=level1,
            level2=level2,
        )
    )

    assert window.compressed is True
    assert [name for name, _, _ in calls] == ["level1"]
    assert "问题0" in calls[0][1] and "问题3" in calls[0][1]
    assert "问题4" not in calls[0][1]
    assert window.parts == ["一级精简摘要"]
    assert window.compressed_until_id == 8  # 前 4 轮共 8 条消息
    assert len(window.messages) == KEEP_RECENT_TURNS * 2 + 1
    assert window.messages[0].content == "问题4"
    assert window.messages[-1].content == "本轮"
    assert window.usage["compressed_turns"] == 4


def test_existing_parts_are_compressed_again_at_level_two():
    rows = _rows(8)
    calls: list[str] = []

    async def level1(text: str, limit: int) -> str:
        calls.append("level1")
        return "新增精简"

    async def level2(text: str, limit: int) -> str:
        calls.append("level2")
        return "二次强摘要"

    window = asyncio.run(
        build_history_window(
            rows,
            HumanMessage(content="本轮"),
            ["较早摘要", "更早摘要"],
            4,
            budget=1,
            level1=level1,
            level2=level2,
        )
    )

    assert calls == ["level1", "level2"]
    assert window.parts == ["二次强摘要", "新增精简"]
    assert window.summary == "二次强摘要\n新增精简"
    assert window.compressed_until_id == 4  # 前 2 轮共 4 条消息


def test_summary_alone_is_compressed_when_recent_turns_fit():
    rows = _rows(3)

    async def level1(text: str, limit: int) -> str:
        raise AssertionError("没有旧轮次时不应做一级压缩")

    async def level2(text: str, limit: int) -> str:
        return "强摘要"

    window = asyncio.run(
        build_history_window(
            rows,
            HumanMessage(content="本轮"),
            ["很长的旧摘要" * 100],
            6,
            budget=1,
            level1=level1,
            level2=level2,
        )
    )

    assert window.parts == ["强摘要"]
    assert window.compressed_until_id == 6
    assert len(window.messages) == 7


def test_compressor_failure_falls_back_to_truncated_text():
    rows = _rows(10)

    async def broken(text: str, limit: int) -> str:
        raise RuntimeError("模型不可用")

    window = asyncio.run(
        build_history_window(
            rows,
            HumanMessage(content="本轮"),
            [],
            None,
            budget=1,
            level1=broken,
            level2=broken,
        )
    )

    assert window.compressed is True
    assert window.parts and "问题0" in window.parts[0]
