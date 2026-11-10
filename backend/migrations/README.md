# 数据库迁移（Alembic）

## 它解决什么问题

在此之前，项目的 schema 管理有两个洞：

1. **建表靠手工执行 `database/init.sql`** —— 没有版本记录，改了也不知道谁改的、改了什么；
2. **结构变更靠应用启动时跑 `ALTER TABLE`**（原先 `file_service.ensure_collection_column`）——
   没有回滚手段，而且多副本并发启动会 DDL 竞争。

Alembic 把每次结构变更变成一个**有 id、可前进可回滚**的版本。部署流程随之变成：

```bash
alembic upgrade head && uvicorn homemind.main:app --host 0.0.0.0 --port 8000
```

## 常用命令

在 `backend/` 目录执行：

```bash
alembic upgrade head                        # 升级到最新
alembic downgrade -1                        # 回滚一步
alembic current                             # 当前版本
alembic history --verbose                   # 变更历史
alembic revision --autogenerate -m "说明"    # 按模型差异生成迁移（需连库）
alembic upgrade head --sql                  # 只输出 SQL 不执行（上线前审查用）
```

## 已有环境如何接入

`0001_initial` 与 `database/init.sql` **等价**。所以：

| 环境状态 | 该做什么 |
| --- | --- |
| 已用 `init.sql` 建好库 | `alembic stamp 0001_initial`（标记为已应用，不要执行 upgrade） |
| 全新环境 | 直接 `alembic upgrade head` |

## 为什么初始迁移用 `metadata.create_all()`

建库初期的 schema 就是 ORM 模型的镜像。逐列手写 8 张表、100+ 字段，
只会引入"迁移脚本与模型不一致"的风险——而这恰恰是迁移工具要消除的问题。

**从第二次结构变更开始**，才应该用显式操作（`op.add_column` / `op.create_index`），
由 `alembic revision --autogenerate` 生成后人工复核。

## 两个实现细节

**连接串从 Settings 读取**（`migrations/env.py`），与运行时共用同一份 `.env`，
避免 `alembic.ini` 与 `config.py` 两处维护同一个数据库地址。

**异步驱动换成同步驱动**：项目运行时用 `mysql+aiomysql`，而 Alembic 的迁移脚本
按同步方式执行。依赖里已有 `pymysql`，直接把 URL 里的 `+aiomysql` 换成 `+pymysql`。

## ⚠️ 为什么 alembic.ini 是纯英文的

`configparser` 读取配置文件时使用**平台默认编码**——中文 Windows 上是 GBK。
文件里只要有任何一个非 ASCII 字节，所有 alembic 命令都会直接抛：

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0xae in position 24
```

这个坑是实际运行 `alembic upgrade head --sql` 时才发现的，静态检查看不出来。
所以 `alembic.ini` 保持纯 ASCII，中文说明放在本文件里。
