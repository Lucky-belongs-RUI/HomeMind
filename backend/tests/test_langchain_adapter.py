"""LangChain 模型工厂与客户端适配器测试（不发起网络请求）。"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from homemind.core.config import settings
from homemind.llm.langchain import (
    LLMNotConfiguredError,
    _openai_tool_schema,
    build_chat_model,
    extract_usage,
    message_text,
    resolve_provider_config,
    to_langchain_messages,
)
from homemind.llm.types import Message, ToolCall, ToolDefinition


def test_to_langchain_messages_preserves_roles_and_tool_calls():
    messages = [
        Message(role="system", content="系统"),
        Message(role="user", content="打开灯"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="call_1", name="set_device_state", arguments={"a": 1})],
        ),
        Message(role="tool", content='{"ok": true}', tool_call_id="call_1", name="set_device_state"),
    ]
    converted = to_langchain_messages(messages, system="额外系统提示")

    assert isinstance(converted[0], SystemMessage)
    assert converted[0].content == "额外系统提示"
    assert isinstance(converted[1], SystemMessage)
    assert isinstance(converted[2], HumanMessage)
    assert isinstance(converted[3], AIMessage)
    assert converted[3].tool_calls[0]["name"] == "set_device_state"
    assert converted[3].tool_calls[0]["args"] == {"a": 1}
    assert isinstance(converted[4], ToolMessage)
    assert converted[4].tool_call_id == "call_1"


def test_openai_tool_schema_shape():
    schema = _openai_tool_schema(
        ToolDefinition(
            name="get_weather",
            description="查询天气",
            parameters={"type": "object", "properties": {}},
        )
    )
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "get_weather"
    assert schema["function"]["parameters"]["type"] == "object"


def test_resolve_provider_config_rejects_unknown_provider():
    with pytest.raises(LLMNotConfiguredError):
        resolve_provider_config("unknown-provider")


def test_resolve_provider_config_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "")
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(LLMNotConfiguredError):
        resolve_provider_config("qwen")


def test_resolve_provider_config_ollama_needs_no_real_key(monkeypatch):
    monkeypatch.setattr(settings, "ollama_base_url", "http://localhost:11434/v1")
    cfg = resolve_provider_config("ollama", "qwen2.5:7b")
    assert cfg.provider == "ollama"
    assert cfg.model == "qwen2.5:7b"
    assert cfg.api_key == "ollama"


def test_build_chat_model_returns_chat_openai(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "test-key")
    model = build_chat_model("qwen", "qwen-plus", timeout=5, max_retries=0)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "qwen-plus"
    assert model.max_retries == 0


def test_extract_usage_prefers_usage_metadata():
    message = AIMessage(content="hi", usage_metadata={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7})
    assert extract_usage(message) == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }


def test_extract_usage_falls_back_to_response_metadata():
    message = AIMessage(
        content="hi",
        response_metadata={"token_usage": {"prompt_tokens": 2, "completion_tokens": 5}},
    )
    assert extract_usage(message)["total_tokens"] == 7


def test_message_text_handles_string_and_blocks():
    assert message_text(AIMessage(content="纯文本")) == "纯文本"
    assert message_text(AIMessage(content=[{"type": "text", "text": "第一段"}, {"text": "第二段"}])) == "第一段第二段"
    assert message_text(AIMessage(content="")) == ""
