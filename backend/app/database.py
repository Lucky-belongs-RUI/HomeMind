from contextlib import asynccontextmanager

from sqlalchemy import BigInteger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# 主键统一使用 BIGINT，与 MySQL 表结构保持一致
BigIntPK = BigInteger()


class Base(DeclarativeBase):
    """SQLAlchemy ORM 基类，所有模型继承。"""


def _create_engine():
    try:
        return create_async_engine(settings.mysql_url, echo=False, future=True)
    except ModuleNotFoundError as exc:
        if "aiomysql" in str(exc):
            raise RuntimeError("缺少 aiomysql，请执行: pip install aiomysql") from exc
        raise


engine = _create_engine()
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI 依赖：提供异步会话。"""
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def get_db_session():
    """业务服务统一使用的会话上下文，异常时自动回滚。"""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
