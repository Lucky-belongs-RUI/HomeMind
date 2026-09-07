import hashlib
import json
import re
from typing import AsyncIterator, List, Optional

from app.llm.base import BaseLLMClient
from app.llm.embed_utils import local_embed_texts
from app.llm.message import LLMResponse, Message, ToolCall, ToolDefinition


class MockLLMClient(BaseLLMClient):
    """无 API Key 时的规则降级客户端：支持核心工具链路演示。

    首次调用按关键词生成工具调用，工具结果返回后生成自然语言确认。
    """

    async def chat(self, messages, system=None, temperature=0.7, max_tokens=2048):
        text = messages[-1].content or ""
        if system:
            # 意图识别：返回规则引擎 JSON，保证无 Key 时完整链路可演示
            if "意图识别引擎" in system:
                from app.agent.rules.intent import build_rule_intents
                data = build_rule_intents(text)
                return LLMResponse(content=json.dumps(data, ensure_ascii=False))
            # 回复生成（旧/新提示词）：返回空内容，由节点回退到规则回复生成
            if ("RAG 知识上下文" in system or "各链路结果" in system) and "执行明细" in system:
                return LLMResponse(content="")
            # 情感聊天：返回暖心的演示回复
            if "日常聊天或情感关怀" in system:
                return LLMResponse(content="（演示模式）我在呢，有什么可以帮您的吗？")
            # 报告生成：返回空内容，由节点回退到规则版报告
            if "家庭情况报告" in system and "报告结构" in system:
                return LLMResponse(content="")
            # 知识问答：返回空内容，由节点回退到规则版知识回答
            if "检索到的知识片段" in system:
                return LLMResponse(content="")
        return LLMResponse(content=f"（演示模式）{text}")

    async def chat_with_tools(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        # 工具结果已返回：根据结果生成自然语言回复
        if messages and messages[-1].role == "tool":
            return LLMResponse(content=self._summarize_tool_result(messages[-1].content or ""))

        text = messages[-1].content or "" if messages else ""
        tool_calls = self._match_tool(text)
        if tool_calls:
            return LLMResponse(content=None, tool_calls=tool_calls, finish_reason="tool_calls")
        return LLMResponse(content=self._fallback_reply(text))

    async def stream_chat(self, messages, system=None) -> AsyncIterator[str]:
        text = messages[-1].content or "" if messages else ""
        for ch in self._fallback_reply(text):
            yield ch

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """本地中文向量，保证无 Key 时 RAG 链路可运行。"""
        return local_embed_texts(texts)

    def _match_tool(self, text: str) -> Optional[List[ToolCall]]:
        calls = []
        room = "卧室" if "卧室" in text else ("客厅" if "客厅" in text else "")
        if "空调" in text and "度" in text:
            temp = int(re.search(r"(\d+)", text).group(1)) if re.search(r"(\d+)", text) else 26
            calls.append(self._call("set_device_state", {
                "room_name": room or "卧室",
                "device_type": "air_conditioner",
                "attributes": {"temperature": temp, "power": "on"},
            }))
        elif "灯" in text:
            calls.append(self._call("set_device_state", {
                "room_name": room or "客厅",
                "device_type": "light",
                "attributes": {"power": "off" if "关" in text else "on"},
            }))
        elif "窗帘" in text:
            position = 100 if ("开" in text or "拉" in text) else 0
            calls.append(self._call("set_device_state", {
                "room_name": room or "客厅",
                "device_type": "curtain",
                "attributes": {"position": position},
            }))
        elif "电视" in text:
            calls.append(self._call("set_device_state", {
                "room_name": room or "客厅",
                "device_type": "tv",
                "attributes": {"power": "off" if "关" in text else "on"},
            }))
        elif "净化" in text:
            calls.append(self._call("set_device_state", {
                "room_name": room or "客厅",
                "device_type": "air_purifier",
                "attributes": {"power": "off" if "关" in text else "on"},
            }))
        elif "加湿" in text:
            calls.append(self._call("set_device_state", {
                "room_name": room or "卧室",
                "device_type": "humidifier",
                "attributes": {"power": "off" if "关" in text else "on"},
            }))
        elif "热水器" in text:
            attrs = {"power": "off" if "关" in text else "on"}
            if "度" in text:
                temp = int(re.search(r"(\d+)", text).group(1)) if re.search(r"(\d+)", text) else 45
                attrs["temperature"] = temp
            calls.append(self._call("set_device_state", {
                "room_name": room or "厨房",
                "device_type": "water_heater",
                "attributes": attrs,
            }))
        elif "洗衣机" in text:
            washing = "关" not in text and "停" not in text
            calls.append(self._call("set_device_state", {
                "room_name": room or "阳台",
                "device_type": "washer",
                "attributes": {"power": "on" if washing else "off", "status": "running" if washing else "idle"},
            }))
        elif "冰箱" in text:
            calls.append(self._call("set_device_state", {
                "room_name": room or "厨房",
                "device_type": "fridge",
                "attributes": {"power": "off" if "关" in text else "on"},
            }))
        elif "门锁" in text or "开锁" in text or "锁门" in text:
            calls.append(self._call("set_device_state", {
                "room_name": room or "客厅",
                "device_type": "door_lock",
                "attributes": {"locked": "开锁" in text or "开门" in text},
            }))
        elif "摄像头" in text or "监控" in text:
            recording = "录制" in text or ("开" in text and "摄像" in text)
            calls.append(self._call("set_device_state", {
                "room_name": room or "客厅",
                "device_type": "camera",
                "attributes": {"recording": recording, "power": "on"},
            }))
        elif "回家" in text:
            calls.append(self._call("trigger_scene", {"scene_name": "回家模式"}))
        elif "睡眠" in text:
            calls.append(self._call("trigger_scene", {"scene_name": "睡眠模式"}))
        elif "设备" in text or "房间" in text or "查询" in text:
            calls.append(self._call("list_room_devices", {"room_name": room or "all"}))
        return calls or None

    def _call(self, name: str, arguments: dict) -> ToolCall:
        return ToolCall(
            id=f"call_{abs(hash(name + json.dumps(arguments, ensure_ascii=False))) % 100000}",
            name=name,
            arguments=arguments,
        )

    def _summarize_tool_result(self, result: str) -> str:
        try:
            data = json.loads(result)
        except Exception:
            return "演示模式：操作已完成。"
        if not data.get("success"):
            return f"操作未能完成：{data.get('error', '未知错误')}"
        return data.get("message", "演示模式：操作已完成。")

    def _fallback_reply(self, text: str) -> str:
        return f"（演示模式）我理解您想处理：{text}。配置 LLM API Key 后可获得完整智能回复。"
