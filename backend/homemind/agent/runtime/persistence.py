"""LangGraph 持久化：Postgres checkpointer（中断态）+ Postgres Store（长期记忆）。

职责：
- 应用启动时创建 psycopg 异步连接池、AsyncPostgresSaver 与 AsyncPostgresStore，
  并各执行一次 setup()（建表，幂等）；
- 任一环节失败时明确记录日志并降级为进程内 MemorySaver，不阻断服务启动；
  实际生效的后端可通过 persistence_status() 查询（已暴露在 / 健康检查里）。

为什么用 Postgres：LangGraph 官方 checkpointer 只提供 SQLite 与 Postgres 两个
持久化实现，没有 MySQL 版；本项目业务库仍是 MySQL，两者互不影响。

关于 setup()：它会建表并跑迁移，属于部署期动作。单进程本地开发在启动时执行
是安全的；多副本部署时应改为在发布流程中单独执行一次，避免并发 DDL 竞争。
"""

import logging

from langgraph.checkpoint.memory import MemorySaver

from homemind.core.config import settings

logger = logging.getLogger(__name__)

_pool = None
_checkpointer = None
_store = None
_backend = "memory"
_last_error = ""


async def _build_store(pool):
    """构建 Postgres Store（跨线程长期记忆），兼容不同版本的导出路径。"""
    try:
        from langgraph.store.postgres import AsyncPostgresStore
    except ImportError:  # pragma: no cover - 兼容按 aio 子模块导出的版本
        from langgraph.store.postgres.aio import AsyncPostgresStore

    store = AsyncPostgresStore(pool)
    await store.setup()
    return store


async def init_persistence():
    """初始化持久化组件，返回 (checkpointer, store)；失败时降级为内存实现。"""
    global _pool, _checkpointer, _store, _backend, _last_error

    if not settings.langgraph_persistence_enabled:
        logger.info(
            "LangGraph 持久化已关闭（LANGGRAPH_PERSISTENCE_ENABLED=false），使用进程内 MemorySaver"
        )
        _checkpointer = MemorySaver()
        _store = None
        _backend = "memory"
        _last_error = ""
        return _checkpointer, None

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=settings.postgres_url,
            max_size=settings.langgraph_pool_max_size,
            open=False,
            kwargs={
                # 手工构建连接池时 PostgresSaver / PostgresStore 有硬性要求：
                # 缺 autocommit 会导致 setup() 建表不落库；
                # 缺 row_factory=dict_row 会在读回 checkpoint 时抛 TypeError。
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        await pool.open(wait=True, timeout=10)

        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()

        store = None
        try:
            store = await _build_store(pool)
        except Exception as exc:
            # Store 失败不影响 checkpointer：中断恢复是硬需求，长期记忆是增强项
            logger.warning("LangGraph Store 初始化失败，长期记忆接口暂不可用: %s", exc)

        _pool = pool
        _checkpointer = checkpointer
        _store = store
        _backend = "postgres"
        _last_error = ""
        logger.info(
            "LangGraph 持久化已启用：checkpointer=AsyncPostgresSaver，store=%s",
            type(store).__name__ if store else "未启用",
        )
        return checkpointer, store

    except Exception as exc:
        _last_error = str(exc)
        _checkpointer = MemorySaver()
        _store = None
        _backend = "memory"
        logger.error(
            "LangGraph Postgres 持久化初始化失败，已降级为进程内 MemorySaver："
            "服务重启后处于澄清/审批中断态的会话将无法恢复。原因: %s",
            exc,
        )
        return _checkpointer, None


async def shutdown_persistence():
    """关闭连接池，释放数据库连接。"""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
        except Exception as exc:
            logger.warning("关闭 LangGraph Postgres 连接池失败: %s", exc)
        _pool = None


def get_store():
    """返回当前 Store 实例；未启用时返回 None。"""
    return _store


def get_checkpointer():
    """返回当前 checkpointer；运行时在启动时注入。"""
    return _checkpointer


def persistence_status() -> dict:
    """持久化后端状态，供健康检查与排障使用。"""
    return {
        "backend": _backend,
        "store": type(_store).__name__ if _store else None,
        "error": _last_error or None,
    }
