"""新增用户个人模型配置表

Revision ID: 0003_user_model_configs
Revises: 0002_session_contexts
Create Date: 2026-11-10

API Key 只保存 Fernet 密文，接口不返回明文。
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_user_model_configs"
down_revision = "0002_session_contexts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_model_configs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("api_key_encrypted", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_user_model_config_name"),
    )
    op.create_index("ix_model_configs_user", "user_model_configs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_model_configs_user", table_name="user_model_configs")
    op.drop_table("user_model_configs")
