"""Agent 上下文工具与会话互斥的纯函数测试（不依赖数据库与网络）。"""

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from homemind.agent.runtime.context import (
    estimate_tokens,
    format_recent_history,
    history_without_current,
    render_profile,
)
from homemind.agent.runtime.session_lock import (
    SessionBusy,
    acquire,
    is_busy,
    release,
    session_guard,
)


def test_estimate_tokens_prefers_overestimate():
    assert estimate_tokens("") == 0
    assert estimate_tokens("客厅灯") == 3
    assert estimate_tokens("abcd") == 1


def test_history_without_current_drops_matching_last_user_message():
    messages = [
        HumanMessage(content="第一轮"),
        AIMessage(content="第一轮回答"),
        HumanMessage(content="本轮"),
    ]
    assert history_without_current(messages, "本轮") == messages[:-1]
    # 内容不一致（澄清回答）时不能误删
    assert history_without_current(messages, "上一轮") == messages


def test_format_recent_history_marks_roles_and_caps_length():
    messages = [
        HumanMessage(content="把客厅空调调到26度"),
        AIMessage(content="已调到26度"),
    ]
    text = format_recent_history(messages, max_chars=200)
    assert text == "用户：把客厅空调调到26度\n助手：已调到26度"

    capped = format_recent_history(messages, max_chars=4)
    assert capped.endswith("…")
    assert len(capped) < len(text)


def test_render_profile_skips_empty_values_and_caps_length():
    assert render_profile({}) == ""
    assert render_profile({"怕冷": True, "备注": ""}) == "- 怕冷：True"
    rendered = render_profile({"偏好": "很长的描述" * 100}, max_chars=10)
    assert len(rendered) == 11  # 10 字符 + 省略号
    assert rendered.endswith("…")


def test_session_guard_rejects_concurrent_use_and_releases():
    async def scenario():
        async with session_guard("thread-a"):
            assert is_busy("thread-a")
            with pytest.raises(SessionBusy):
                acquire("thread-a")
        assert not is_busy("thread-a")

        # release 幂等，供流式响应兜底
        acquire("thread-a")
        release("thread-a")
        release("thread-a")
        assert not is_busy("thread-a")

    asyncio.run(scenario())


def test_system_message_is_not_history():
    """历史格式化只处理对话消息，SystemMessage 不应混入。"""
    messages = [SystemMessage(content="系统提示"), HumanMessage(content="你好")]
    assert "系统提示" not in format_recent_history(messages)
