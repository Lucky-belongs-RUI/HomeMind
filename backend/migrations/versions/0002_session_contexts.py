"""新增会话上下文压缩状态表

Revision ID: 0002_session_contexts
Revises: 0001_initial
Create Date: 2026-11-05

存储每个会话的两级压缩摘要数组与已压缩到的消息边界，
使超预算时压缩而不是丢弃历史。
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_session_contexts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_contexts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("compressed_parts", sa.JSON(), nullable=True),
        sa.Column("compressed_until_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "user_id", "session_id", name="uq_session_context"),
    )
    op.create_index("ix_session_contexts_family_id", "session_contexts", ["family_id"])
    op.create_index("ix_session_contexts_user_id", "session_contexts", ["user_id"])
    op.create_index("ix_session_contexts_session_id", "session_contexts", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_session_contexts_session_id", table_name="session_contexts")
    op.drop_index("ix_session_contexts_user_id", table_name="session_contexts")
    op.drop_index("ix_session_contexts_family_id", table_name="session_contexts")
    op.drop_table("session_contexts")
