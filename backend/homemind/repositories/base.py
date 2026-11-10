"""仓库基类：所有仓库共享同一个 AsyncSession。

分层约定：
- **仓库**只回答「怎么从数据库读写某个实体」，不含业务规则，也不自行提交事务；
- **service** 负责业务规则、事务边界与跨实体编排，通过 UnitOfWork 拿到仓库；
- 因此仓库可以用内存库独立测试，service 也可以用替身仓库脱离数据库测试。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """数据访问基类。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
