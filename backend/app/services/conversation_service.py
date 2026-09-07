from sqlalchemy import select

from app.database import get_db_session
from app.models.conversation import Conversation


async def save_conversation(
    family_id: int,
    user_id: int,
    session_id: str,
    role: str,
    content: str,
    tool_calls: list | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
) -> Conversation:
    async with get_db_session() as db:
        conv = Conversation(
            family_id=family_id,
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
        return conv


async def get_session_conversations(
    family_id: int,
    user_id: int,
    session_id: str,
    limit: int = 30,
) -> list[Conversation]:
    """按会话查询 user/assistant 消息（正序），供前端恢复与模型上下文使用。"""
    async with get_db_session() as db:
        result = await db.execute(
            select(Conversation)
            .where(
                Conversation.family_id == family_id,
                Conversation.user_id == user_id,
                Conversation.session_id == session_id,
                Conversation.role.in_(["user", "assistant"]),
            )
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))


async def delete_session_conversations(
    family_id: int, user_id: int, session_id: str
) -> int:
    """重置会话：删除该会话的全部消息，返回删除条数。"""
    from sqlalchemy import delete

    async with get_db_session() as db:
        result = await db.execute(
            delete(Conversation).where(
                Conversation.family_id == family_id,
                Conversation.user_id == user_id,
                Conversation.session_id == session_id,
            )
        )
        await db.commit()
        return result.rowcount or 0


async def get_recent_conversations(user_id: int, limit: int = 50) -> list[Conversation]:
    async with get_db_session() as db:
        result = await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))