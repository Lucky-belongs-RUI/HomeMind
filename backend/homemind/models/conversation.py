from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from homemind.core.database import Base, BigIntPK


class Conversation(Base):
    """对话历史表：按家庭与用户隔离，session_id 关联多轮对话。"""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list | None] = mapped_column(JSON)
    tool_call_id: Mapped[str | None] = mapped_column(String(64))
    tool_name: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SessionContext(Base):
    """会话上下文压缩状态：压缩摘要数组 + 已压缩到的消息边界。"""

    __tablename__ = "session_contexts"
    __table_args__ = (
        UniqueConstraint("family_id", "user_id", "session_id", name="uq_session_context"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 按时间顺序保存的压缩片段：[二级强摘要, 一级精简摘要]
    compressed_parts: Mapped[list | None] = mapped_column(JSON, default=list)
    # 已纳入压缩的最后一条 conversation id；之后的消息仍是未压缩原文
    compressed_until_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
