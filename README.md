# 智能家居大模型体验平台（Smart Home LLM Experience Platform）

将**大模型 Agent 能力**接入智能家居场景的全栈体验平台。用户通过文字或语音与 AI 助理交互，即可完成情感闲聊、知识问答、设备控制（含任务规划与审批）、场景联动和全屋报告生成。后端以 LangGraph 状态图编排「意图识别 → 多链路并发执行」，前端为玻璃拟态风格的 SPA，内置设备模拟器，开箱即可体验完整闭环。

## 核心功能

- **多意图 Agent**：意图识别优先，按需路由到 情感聊天 / RAG 知识问答 / 设备控制（规划→审批→工具执行）/ 全屋报告 等多条链路，可并发执行
- **多 LLM 适配**：通义千问（默认）、DeepSeek、智谱 GLM、本地 Ollama、Mock 模式，环境变量一键切换
- **RAG 知识库**：PDF / Word 文档上传 → 文本分块 → 向量化（ChromaDB，缺失时自动回退本地 JSON 检索）→ 检索增强问答
- **语音交互**：Whisper 语音识别（可选，缺失时返回演示指令）+ Edge-TTS 语音合成
- **设备模拟与实时推送**：APScheduler 定时模拟设备状态变化，WebSocket 实时推送；设备状态以 MySQL 为唯一数据源
- **家庭多角色权限**：房主 / 住户 / 访客三级权限矩阵，家庭数据隔离
- **Docker Compose**：一键启动 MySQL 8.0 + 后端

## 技术栈

| 模块 | 技术 |
| ---- | ---- |
| 后端 | Python 3.11+ · FastAPI · SQLAlchemy 2（aiomysql 异步）· JWT · LangGraph · ChromaDB · WebSocket · APScheduler |
| 前端 | Vue 3 · Vite 5 · Pinia · Vue Router · Element Plus · Tailwind CSS · Lottie |
| 数据库 | MySQL 8.0（`database/init.sql` 统一初始化） |

## 目录结构

```
ZHJJ/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── agent/              # LangGraph 状态图：意图识别、节点、规则、工具
│   │   ├── api/                # REST API（认证/设备/房间/场景/家庭/Agent/文件）
│   │   ├── llm/                # 多 LLM 适配层（Qwen/DeepSeek/Zhipu/Ollama/Mock）
│   │   ├── rag/                # 分块、向量化、检索、向量存储
│   │   ├── voice/              # STT（Whisper）与 TTS（Edge-TTS）
│   │   ├── websocket/          # 设备状态实时推送
│   │   ├── scheduler/          # 设备模拟器调度
│   │   ├── models/ · schemas/  # ORM 模型与 Pydantic 校验
│   │   └── config.py           # 配置（环境变量 / .env）
│   ├── requirements.txt        # 核心依赖
│   ├── requirements-optional.txt  # 可选增强（LangGraph/ChromaDB/Whisper，缺失自动降级）
│   ├── docker-compose.yml      # MySQL + 后端一键启动
│   └── .env.example
├── frontend/                   # Vue 3 前端（登录/设备/房间/AI 助理/家庭/数据上传）
├── database/init.sql           # 建库 + 建表 + 演示数据
└── plugins/                    # 第三方插件示例资源（非本项目代码，建议不提交）
```

## 环境要求

- **Python** 3.11+、**Node.js** 18+、npm 9+
- **MySQL** 8.0（或用 Docker 启动）
- 至少一个 LLM 的 API Key（默认通义千问 `QWEN_API_KEY`；也可用本地 Ollama 或 Mock 模式免 Key 运行）

## 快速开始

### 方式一：Docker Compose 一键启动后端（推荐）

```bash
cd backend
cp .env.example .env   # 填入 QWEN_API_KEY 等
docker compose up --build
```

MySQL 与后端一并启动，后端监听 <http://localhost:8000>。

### 方式二：手动运行

#### 1. 初始化数据库

```bash
# 在项目根目录执行
mysql -u root -p < database/init.sql
```

脚本会创建 `smart_home` 库及全部业务表，并写入演示数据。

#### 2. 启动后端（端口 8000）

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
# 可选增强依赖（缺失时自动降级，不影响核心链路）
# pip install -r requirements-optional.txt

cp .env.example .env     # 按需修改 MYSQL_URL 与 LLM 配置
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 文档：<http://localhost:8000/docs>

#### 3. 启动前端（端口 5173）

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 <http://localhost:5173>。Vite 已配置 `/api` 代理（含 WebSocket）到后端；也可通过 `VITE_API_BASE_URL` / `VITE_WS_URL` 直连。

### 演示账号

| 角色 | 用户名 | 密码 |
| ---- | ---- | ---- |
| 房主 | `owner01` | `123456` |
| 住户 | `resident01` | `123456` |
| 访客 | `guest01` | `123456` |

> 演示模式密码明文保存、不做哈希与安全校验，仅用于本地体验。

## 配置说明（`backend/.env`）

| 变量 | 说明 | 默认值 |
| ---- | ---- | ------ |
| `MYSQL_URL` | 异步 MySQL 连接串 | `mysql+aiomysql://root:root@localhost:3306/smart_home` |
| `LLM_PROVIDER` | 模型供应商：`qwen` / `deepseek` / `zhipu` / `ollama` / `mock` | `qwen` |
| `QWEN_API_KEY` 等 | 对应供应商的 API Key 与模型名 | 空 |
| `JWT_SECRET` | JWT 密钥 | 内置示例值（生产请修改） |
| `JWT_EXPIRE_HOURS` | Token 有效期 | `24` |
| `CHROMA_PATH` / `UPLOAD_DIR` | 向量库与上传目录 | `./chroma_data` / `./uploads` |
| `WHISPER_MODEL` / `TTS_VOICE` | 语音识别模型与合成音色 | `base` / `zh-CN-XiaoxiaoNeural` |

## 开源声明

本项目仅用于**学习与交流**，**禁止任何形式的商业用途**。

任何使用、修改、二次开发或参考本项目的行为，必须注明出处并引用本项目仓库（GitHub：https://github.com/Lucky-belongs-RUI/HomeMind）。
