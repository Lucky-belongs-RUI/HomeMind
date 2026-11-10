"""对话历史表的数据访问。"""

from __future__ import annotations

from sqlalchemy import delete, select

from homemind.models.conversation import Conversation, SessionContext
from homemind.repositories.base import BaseRepository


class ConversationRepository(BaseRepository):
    """对话历史表读写。"""

    async def add(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def list_by_session(
        self,
        family_id: int,
        user_id: int,
        session_id: str,
        limit: int = 30,
    ) -> list[Conversation]:
        """按会话取 user/assistant 消息（时间正序）。

        created_at 精度只到秒，同一秒内写入的多条消息仅按它排序结果不确定，
        因此追加 id 作为决胜键——否则连续两轮问答的先后顺序可能被颠倒。
        """
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.family_id == family_id,
                Conversation.user_id == user_id,
                Conversation.session_id == session_id,
                Conversation.role.in_(["user", "assistant"]),
            )
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def list_session_after(
        self,
        family_id: int,
        user_id: int,
        session_id: str,
        after_id: int | None,
    ) -> list[Conversation]:
        """取压缩边界之后的 user/assistant 消息（时间正序）。"""
        statement = select(Conversation).where(
            Conversation.family_id == family_id,
            Conversation.user_id == user_id,
            Conversation.session_id == session_id,
            Conversation.role.in_(["user", "assistant"]),
        )
        if after_id is not None:
            statement = statement.where(Conversation.id > after_id)
        result = await self.session.execute(
            statement.order_by(Conversation.created_at.asc(), Conversation.id.asc())
        )
        return list(result.scalars().all())

    async def get_session_context(
        self,
        family_id: int,
        user_id: int,
        session_id: str,
    ) -> SessionContext | None:
        result = await self.session.execute(
            select(SessionContext).where(
                SessionContext.family_id == family_id,
                SessionContext.user_id == user_id,
                SessionContext.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_session_context(self, context: SessionContext) -> SessionContext:
        self.session.add(context)
        await self.session.flush()
        return context

    async def delete_session_context(
        self,
        family_id: int,
        user_id: int,
        session_id: str,
    ) -> int:
        result = await self.session.execute(
            delete(SessionContext).where(
                SessionContext.family_id == family_id,
                SessionContext.user_id == user_id,
                SessionContext.session_id == session_id,
            )
        )
        return result.rowcount or 0

    async def list_recent(self, user_id: int, limit: int = 50) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def delete_by_session(self, family_id: int, user_id: int, session_id: str) -> int:
        result = await self.session.execute(
            delete(Conversation).where(
                Conversation.family_id == family_id,
                Conversation.user_id == user_id,
                Conversation.session_id == session_id,
            )
        )
        return result.rowcount or 0

    async def delete_by_family(self, family_id: int) -> None:
        await self.session.execute(delete(Conversation).where(Conversation.family_id == family_id))
