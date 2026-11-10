"""用户偏好画像服务：读取与基于对话历史的 LLM 分析。

提示词见 homemind/prompts.py。
"""

import logging
from typing import Any

from pydantic import RootModel

from homemind.llm.factory import get_llm_client
from homemind.llm.structured import chat_structured
from homemind.llm.types import Message
from homemind.prompts import PREFERENCE_ANALYSIS_PROMPT
from homemind.repositories import unit_of_work
from homemind.services.conversation_service import get_recent_conversations

logger = logging.getLogger(__name__)


class PreferenceProfile(RootModel[dict[str, Any]]):
    """偏好画像契约：键由模型根据对话内容自主决定，只约束顶层为 JSON 对象。"""


async def get_user_preferences(user_id: int) -> dict:
    """查询用户偏好画像，不存在时返回空画像。"""
    async with unit_of_work() as uow:
        record = await uow.preferences.get(user_id)
        return record.preferences if record else {}


async def analyze_user_preferences(user_id: int) -> dict:
    """基于最近对话历史调用 LLM 生成偏好画像并 upsert 保存。

    解析失败或没有足够对话时保留已有画像，避免空画像覆盖有效数据。
    """
    conversations = await get_recent_conversations(user_id, limit=50)
    conv_text = "\n".join(
        [
            f"{c.role}: {c.content}"
            for c in conversations
            if c.content and c.role in ("user", "assistant")
        ]
    )
    preferences = {}
    if conv_text:
        try:
            client = get_llm_client()
            profile = await chat_structured(
                client,
                messages=[
                    Message(
                        role="user",
                        content=PREFERENCE_ANALYSIS_PROMPT.render(conversations=conv_text),
                    )
                ],
                system="你是用户行为分析专家，输出严格的 JSON 格式。",
                model=PreferenceProfile,
                temperature=0.3,
            )
            preferences = {
                key: value for key, value in profile.root.items() if value not in (None, "", [], {})
            }
        except Exception as exc:  # 分析失败不影响主流程，保留旧画像
            logger.warning("偏好画像分析异常: %s", exc)
            preferences = {}

    async with unit_of_work() as uow:
        existing = await uow.preferences.get(user_id)
        if preferences:
            await uow.preferences.upsert(user_id, preferences)
            await uow.commit()
            return preferences
        # 无有效分析结果：保留已有画像（若存在），不覆盖为空
        if existing:
            return existing.preferences
        return {}
