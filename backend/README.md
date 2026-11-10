# 智能家居大模型体验平台 - 后端

FastAPI 后端服务，实现认证、家庭管理、设备控制、Agent、RAG、语音与场景联动。

## 目录结构（标准 FastAPI 分层）

```text
homemind/
├── main.py            # FastAPI 入口：路由挂载、CORS、生命周期
├── api/               # 路由层：每个业务域一个 APIRouter
├── schemas/           # Pydantic 请求/响应模型
├── services/          # 业务逻辑与事务边界
├── repositories/      # 数据访问（SQL 只出现在这里）
├── models/            # SQLAlchemy ORM
├── core/              # 配置、数据库会话、异常体系与全局处理器
├── agent/             # Agent 编排
│   ├── runtime/       # LangGraph 主图、规划、分支、控制子图、持久化
│   ├── rules/         # LLM 不可用时的规则兜底
│   └── tools/         # 设备工具实现与 LangChain 绑定
├── llm/               # LLM 供应商适配与 LangChain 模型工厂
├── rag/               # 分块、向量化、检索
├── prompts.py         # 带版本号的提示词资产
├── voice/             # 语音识别与合成
├── scheduler/         # 设备模拟调度
└── websocket/         # 实时推送
```

## 本地运行（MySQL 8.0）

```bash
cd backend
pip install -r requirements.txt
# 可选增强依赖（LangGraph/ChromaDB/Whisper），缺失时自动降级
# pip install -r requirements-optional.txt

# 1. 初始化数据库（建库 + 建表 + 演示数据，演示账号密码统一 123456）
#    方式一：直接导入 SQL（在项目根目录执行）
#    mysql -u root -p < database/init.sql
#    方式二：使用 Docker 启动 MySQL 8.0 并自动初始化
#    docker compose up -d mysql

# 2. 复制环境配置并按本地账号修改 MYSQL_URL（默认 mysql+aiomysql://root:root@localhost:3306/smart_home）
copy .env.example .env

# 3. 启动服务
uvicorn homemind.main:app --reload --host 0.0.0.0 --port 8000
```

- API 文档：http://localhost:8000/docs
- 演示账号：owner01 / 123456（张三的家）、owner02 / 123456（赵六的家）
- 密码按演示需求明文保存，不做哈希与安全校验
- 数据库结构由 `database/init.sql` 统一管理，后端启动时不再自动建表或写入种子数据

## 对接前端

前端已移除 mock 演示层，默认通过 Vite `/api` 代理到本后端；只需先初始化 `database/init.sql`，再启动后端与前端即可全流程联动。
