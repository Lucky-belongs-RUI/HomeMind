"""初始基线：按当前 ORM 模型建立全部表

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-16

## 为什么用 metadata.create_all 而不是逐表 op.create_table

建库初期的 schema 就是 ORM 模型的镜像。逐列手写 8 张表、100+ 字段，
只会引入"迁移脚本与模型不一致"的风险——而这恰恰是迁移工具要消除的问题。
从第二次结构变更开始，才应该用显式操作（`op.add_column` / `op.create_index`），
由 `alembic revision --autogenerate` 生成后人工复核。

## 与 database/init.sql 的关系

本基线与 `database/init.sql` 等价。**已经用 init.sql 建好库的环境不要执行 upgrade**，
应该先标记为已应用：

    alembic stamp 0001_initial

之后再正常走 `alembic upgrade head`。全新环境则直接 `alembic upgrade head`。
"""

from alembic import op

import homemind.models  # noqa: F401  导入以把所有表注册进 Base.metadata
from homemind.core.database import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
