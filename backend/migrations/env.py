"""Alembic 迁移环境。

两个关键设计：

1. **连接串从 Settings 读取**，与运行时共用同一份 `.env`，
   避免 alembic.ini 与 config.py 两处维护同一个数据库地址。

2. **异步驱动换成同步驱动**：项目运行时用 `mysql+aiomysql`，
   而 Alembic 的迁移脚本按同步方式执行。项目依赖里已有 `pymysql`，
   直接把 URL 里的 `+aiomysql` 换成 `+pymysql` 即可，无需引入 async 迁移模板。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import homemind.models  # noqa: F401  导入以把所有表注册进 Base.metadata
from homemind.core.config import settings
from homemind.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 的比对基准
target_metadata = Base.metadata


def _sync_url() -> str:
    """把运行时的异步连接串换成 Alembic 可用的同步连接串。"""
    return settings.mysql_url.replace("+aiomysql", "+pymysql")


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连数据库（用于上线前审查）。"""
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连库执行迁移。"""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _sync_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # 字段类型变更也要被 autogenerate 检出（默认不检）
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
