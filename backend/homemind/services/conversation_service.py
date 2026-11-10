"""对话历史服务：保存、按会话查询、上下文压缩状态与重置。"""

from homemind.models.conversation import Conversation, SessionContext
from homemind.repositories import unit_of_work


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
    """写入一条对话记录。"""
    async with unit_of_work() as uow:
        conversation = await uow.conversations.add(
            Conversation(
                family_id=family_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
            )
        )
        await uow.commit()
        await uow.refresh(conversation)
        return conversation


async def get_session_conversations(
    family_id: int,
    user_id: int,
    session_id: str,
    limit: int = 30,
) -> list[Conversation]:
    """按会话查询 user/assistant 消息（正序），供前端恢复与模型上下文使用。"""
    async with unit_of_work() as uow:
        return await uow.conversations.list_by_session(family_id, user_id, session_id, limit)


async def get_session_messages_after(
    family_id: int,
    user_id: int,
    session_id: str,
    after_id: int | None,
) -> list[Conversation]:
    """取压缩边界之后的消息；边界为空时返回该会话全部消息。"""
    async with unit_of_work() as uow:
        return await uow.conversations.list_session_after(family_id, user_id, session_id, after_id)


async def get_session_context(
    family_id: int,
    user_id: int,
    session_id: str,
) -> SessionContext | None:
    async with unit_of_work() as uow:
        return await uow.conversations.get_session_context(family_id, user_id, session_id)


async def save_session_context(
    family_id: int,
    user_id: int,
    session_id: str,
    compressed_parts: list[str],
    compressed_until_id: int | None,
) -> SessionContext:
    """按会话更新压缩状态；不存在则创建。"""
    async with unit_of_work() as uow:
        context = await uow.conversations.get_session_context(family_id, user_id, session_id)
        if context is None:
            context = await uow.conversations.add_session_context(
                SessionContext(
                    family_id=family_id,
                    user_id=user_id,
                    session_id=session_id,
                    compressed_parts=list(compressed_parts),
                    compressed_until_id=compressed_until_id,
                )
            )
        else:
            context.compressed_parts = list(compressed_parts)
            context.compressed_until_id = compressed_until_id
        await uow.commit()
        await uow.refresh(context)
        return context


async def delete_session_conversations(family_id: int, user_id: int, session_id: str) -> int:
    """重置会话：删除该会话的全部消息与压缩状态，返回删除条数。"""
    async with unit_of_work() as uow:
        deleted = await uow.conversations.delete_by_session(family_id, user_id, session_id)
        await uow.conversations.delete_session_context(family_id, user_id, session_id)
        await uow.commit()
        return deleted


async def get_recent_conversations(user_id: int, limit: int = 50) -> list[Conversation]:
    """取用户最近的对话（用于偏好画像分析）。"""
    async with unit_of_work() as uow:
        return await uow.conversations.list_recent(user_id, limit)
