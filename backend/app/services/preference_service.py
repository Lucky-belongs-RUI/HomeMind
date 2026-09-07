import json

from sqlalchemy import select

from app.database import get_db_session
from app.llm.factory import get_llm_client
from app.llm.message import Message
from app.models.preference import UserPreference
from app.services.conversation_service import get_recent_conversations

PREFERENCE_ANALYSIS_PROMPT = """分析以下用户对话历史，提取用户偏好画像，只输出 JSON。

对话历史：
{conversations}

输出 JSON 格式：
{{
  "preferred_temperature": {{"summer": 26, "winter": 22}},
  "sleep_schedule": {{"bedtime": "23:00", "wakeup": "07:00"}},
  "interests": ["音乐", "阅读"],
  "frequent_devices": ["air_conditioner"],
  "interaction_style": "concise"
}}
"""


async def get_user_preferences(user_id: int) -> dict:
    """查询用户偏好画像，不存在时返回空画像。"""
    async with get_db_session() as db:
        pref = await db.get(UserPreference, user_id)
        return pref.preferences if pref else {}


async def analyze_user_preferences(user_id: int) -> dict:
    """基于最近对话历史调用 LLM 生成偏好画像并 upsert 保存。"""
    conversations = await get_recent_conversations(user_id, limit=50)
    conv_text = "\n".join(
        [f"{c.role}: {c.content}" for c in conversations if c.content]
    )
    if not conv_text:
        preferences = {}
    else:
        client = get_llm_client()
        resp = await client.chat(
            messages=[Message(role="user", content=PREFERENCE_ANALYSIS_PROMPT.format(conversations=conv_text))],
            system="你是用户行为分析专家，输出严格的 JSON 格式。",
            temperature=0.3,
        )
        try:
            parsed = json.loads(resp.content)
            preferences = parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            preferences = {}

    async with get_db_session() as db:
        existing = await db.get(UserPreference, user_id)
        if existing:
            existing.preferences = preferences
        else:
            db.add(UserPreference(user_id=user_id, preferences=preferences))
        await db.commit()
    return preferences