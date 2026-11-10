"""结构化输出：让 LLM 返回的 JSON 变成有契约、可校验、可重试的结果。

## 原先的问题

各节点用 `extract_json()` 做正则截取，只保证"能解析成 dict"：

- 少一个字段 → 下游 KeyError 或静默取默认值，行为不可预测；
- 类型不对（如 `clarity: "高"`）→ 在很远的地方才炸，堆栈难以定位；
- 每个节点自己写一套清洗逻辑（`_normalize_intents` / `_normalize_llm_task`），
  规则不一致且重复。

## 现在的做法

声明式模型 + 校验 + 失败重试：

1. 契约写在 Pydantic 模型里（见 `homemind/agent/contracts.py`），一处定义、一处修改；
2. 校验失败时把**具体错误原因**追加给模型再试一次，而不是立刻降级到规则引擎；
3. 重试仍失败才走兜底。

## 为什么默认只重试一次

重试的收益来自"模型偶发格式抖动"，不是"模型能力不足"。若第一次就完全没按格式
输出，第二次大概率也一样，继续重试只是白烧 token 与延迟。
"""

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from homemind.llm.types import Message

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

#: 校验失败后的额外重试次数（0 表示不重试）
MAX_STRUCTURED_RETRIES = 1


class StructuredOutputError(RuntimeError):
    """模型输出无法解析为期望的结构。"""


# ============================================================
# 提取
# ============================================================


def extract_json_object(text: str | None) -> dict[str, Any] | None:
    """从模型输出中提取第一个 JSON 对象，兼容 markdown 代码块包裹。

    这是"尽力而为"的提取：找到最外层花括号后交给 json.loads。
    提取失败返回 None，由调用方决定如何处理。
    """
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def looks_like_json(text: str | None) -> bool:
    """判断模型是否把结构化输出当成了回复文本。

    回复类节点（聊天 / 问答 / 报告 / 组织回复）只需要这个布尔判断，
    不需要解析——因此不复用 `parse_structured`，避免为一个布尔值付出校验成本。
    """
    return extract_json_object(text) is not None


# ============================================================
# 校验
# ============================================================


def _format_validation_error(exc: ValidationError) -> str:
    """把 pydantic 的校验错误压成一句给模型看的提示。

    只取前 3 条：错误太多时模型抓不住重点，反而更容易改错。
    """
    parts = []
    for error in exc.errors()[:3]:
        location = ".".join(str(item) for item in error.get("loc", ())) or "(根)"
        parts.append(f"{location}: {error.get('msg', '不合法')}")
    return "；".join(parts)


def parse_structured(text: str | None, model: type[T]) -> T:
    """把模型输出解析为 Pydantic 模型。

    失败时抛 `StructuredOutputError` 并附带**可读的失败原因**——
    这个原因会被回传给模型用于重试，因此不能是裸的堆栈。
    """
    payload = extract_json_object(text)
    if payload is None:
        raise StructuredOutputError("输出中没有找到合法的 JSON 对象")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(_format_validation_error(exc)) from exc


# ============================================================
# 调用 + 重试
# ============================================================


def _retry_hint(error: str) -> str:
    """构造回传给模型的修正提示。"""
    return (
        f"上一次输出未通过格式校验：{error}\n"
        "请重新输出，只包含一个符合要求的 JSON 对象，"
        "不要包含解释文字，也不要用 markdown 代码块包裹。"
    )


async def chat_structured(
    client,
    messages: list[Message],
    system: str,
    model: type[T],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1600,
    max_retries: int = MAX_STRUCTURED_RETRIES,
) -> T:
    """调用模型并把回复解析为结构化结果，校验失败时带原因重试。

    抛出 `StructuredOutputError` 表示重试耗尽仍未通过校验——
    调用方应捕获它并降级（通常是回退规则引擎）。
    """
    conversation = list(messages)
    last_error = ""

    for attempt in range(max_retries + 1):
        if attempt > 0:
            conversation.append(Message(role="user", content=_retry_hint(last_error)))

        response = await client.chat(
            messages=conversation,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        try:
            return parse_structured(response.content, model)
        except StructuredOutputError as exc:
            last_error = str(exc)
            logger.warning(
                "结构化输出校验失败（第 %s/%s 次）: %s",
                attempt + 1,
                max_retries + 1,
                last_error,
            )

    raise StructuredOutputError(f"重试 {max_retries} 次后仍未通过校验：{last_error}")
