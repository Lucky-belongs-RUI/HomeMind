# macOS 前后端开发环境搭建（后端手敲重写版）

> 目标：在 Mac 上用**轻量 Python venv**（不使用 Conda）跑通当前仓库的后端、前端、MySQL、Postgres，并按《后端从 0 到 1 手敲实现计划》逐阶段重写后端。
>
> 适用：Apple Silicon（M1/M2/M3/M4）与 Intel Mac；macOS 13+。
>
> 原则：Python 依赖只装进 `backend/.venv`，不污染系统 Python；数据库用 Docker 或 Homebrew 单独启动；前端直接复用现有 Vue 工程，不手敲。

---

## 一、环境矩阵

| 组件 | 推荐版本 | 用途 |
|---|---|---|
| macOS | 13+ | 开发机 |
| Xcode Command Line Tools | 最新 | 编译 bcrypt、psycopg 等原生扩展 |
| Homebrew | 最新 | 安装 Python、Node、可选工具 |
| Python | 3.11 或 3.12 | 后端；3.11 对可选 Whisper/PyMuPDF 兼容性最好 |
| Node.js | 20 LTS | 前端 Vite 5 |
| MySQL | 8.0 | 业务库 |
| Postgres | 17 | LangGraph checkpointer + Store |
| Docker Desktop | 最新 | 启动 MySQL/Postgres（推荐） |
| Ollama（可选） | 最新 | 本地模型，免 API Key |

端口占用：

| 服务 | 端口 |
|---|---|
| 后端 FastAPI | 8000 |
| 前端 Vite | 5173 |
| MySQL | 3306 |
| Postgres | 5432 |

---

## 二、一次性安装系统依赖

### 2.1 安装 Xcode Command Line Tools

```bash
xcode-select --install
```

如果已经安装，会提示已存在。

### 2.2 安装 Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Apple Silicon 安装后按提示把 Homebrew 加入 `PATH`：

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
source ~/.zshrc
```

Intel Mac 的 Homebrew 前缀通常是 `/usr/local`。

### 2.3 安装 Python 3.11

```bash
brew install python@3.11
python3.11 --version
```

如果 `python3.11` 不在 `PATH`：

```bash
echo 'export PATH="/opt/homebrew/opt/python@3.11/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

> 也可以用 `python3.12`，项目要求 Python 3.11+。不建议用系统自带的 `/usr/bin/python3`。

### 2.4 安装 Node 20

方式一：Homebrew

```bash
brew install node@20
echo 'export PATH="/opt/homebrew/opt/node@20/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
node -v
npm -v
```

方式二：nvm（需要多版本切换时）

```bash
brew install nvm
mkdir -p ~/.nvm
```

在 `~/.zshrc` 中加入：

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$(brew --prefix nvm)/nvm.sh" ] && . "$(brew --prefix nvm)/nvm.sh"
```

然后：

```bash
nvm install 20
nvm use 20
node -v
```

### 2.5 安装 Docker Desktop

推荐直接用 Docker Desktop 启动 MySQL/Postgres：

```bash
brew install --cask docker
open -a Docker
```

等 Docker Desktop 启动完成，确认：

```bash
docker --version
docker compose version
```

> 不想装 Docker Desktop 也可以用 Colima（更轻，但配置多）：
>
> ```bash
> brew install colima docker docker-compose
> colima start --cpu 2 --memory 4
> ```
>
> 或者用 Homebrew 直接安装 MySQL/Postgres，见本文第四节。

---

## 三、项目目录与轻量虚拟环境

### 3.1 进入项目

```bash
cd /path/to/ZHJJ
```

建议在新分支手敲后端：

```bash
git switch -c rebuild-backend
```

### 3.2 创建 venv

在 `backend/` 下创建，保证相对路径 `./uploads`、`./chroma_data`、`.env` 与现有代码一致：

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

确认解释器来自 venv：

```bash
which python
python --version
```

应看到 `.../backend/.venv/bin/python`。

### 3.3 安装后端依赖

```bash
python -m pip install -r requirements.txt
```

开发依赖（pytest、ruff、mypy、alembic、pyyaml）：

```bash
python -m pip install -r requirements-dev.txt
```

可选依赖先不要装，保持轻量：

- `chromadb`：缺失时 RAG 回退本地 JSON 向量检索；
- `openai-whisper`：缺失时语音识别报错，不影响文字对话。

需要时再装：

```bash
python -m pip install -r requirements-optional.txt
```

> 如果 pip 下载慢，可以临时使用镜像：
>
> ```bash
> python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```
>
> 不建议把镜像地址写死到项目配置里。

### 3.4 更快的可选方案：uv

如果本机已有 `uv`，可以替代 venv + pip，速度更快：

```bash
brew install uv
cd backend
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt
```

两者产物都是标准 `backend/.venv`，后续命令完全一致。

### 3.5 目录检查

```text
backend/
├── .venv/          # 轻量虚拟环境（已被 .gitignore 忽略）
├── .env            # 本地配置（已被 .gitignore 忽略）
├── uploads/        # 上传文件
├── chroma_data/    # 向量库
├── homemind/       # 后端源码
└── requirements*.txt
```

创建运行目录：

```bash
mkdir -p uploads chroma_data
```

---

## 四、启动数据库

### 4.1 方式一：Docker Compose（推荐）

在 `backend/` 目录执行：

```bash
docker compose up -d mysql postgres
docker compose ps
```

首次启动时 MySQL 会自动执行 `database/init.sql`，创建 `smart_home` 库、10 张表和演示数据。

等待健康检查通过：

```bash
docker compose ps
```

看到 `smart-home-mysql` 和 `smart-home-postgres` 都是 `healthy` 即可。

验证 MySQL：

```bash
docker exec -it smart-home-mysql mysql -uroot -proot -e "USE smart_home; SHOW TABLES;"
```

验证 Postgres：

```bash
docker exec -it smart-home-postgres psql -U langgraph -d langgraph -c "\dt"
```

> 注意：`init.sql` 只会在 MySQL 数据卷为空时自动执行。如果你之前启动过、后来改了表结构，需要手动重新导入：
>
> ```bash
> docker exec -i smart-home-mysql mysql -uroot -proot < ../database/init.sql
> ```
>
> 或者删除数据卷重来（会丢失本地数据库数据）：
>
> ```bash
> docker compose down -v
> docker compose up -d mysql postgres
> ```

### 4.2 方式二：Homebrew 本地安装

MySQL：

```bash
brew install mysql@8.0
brew services start mysql@8.0
```

Homebrew 安装的 MySQL root 默认可能没有密码。初始化库：

```bash
mysql -h 127.0.0.1 -uroot < ../database/init.sql
```

此时 `.env` 中连接串要按实际账号调整，例如：

```dotenv
MYSQL_URL=mysql+aiomysql://root@127.0.0.1:3306/smart_home
```

Postgres：

```bash
brew install postgresql@17
brew services start postgresql@17
createuser -s langgraph
createdb -O langgraph langgraph
psql -d postgres -c "ALTER USER langgraph WITH PASSWORD 'langgraph';"
```

验证：

```bash
psql "postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph" -c "select 1;"
```

### 4.3 没有 Postgres 时

在 `backend/.env` 设置：

```dotenv
LANGGRAPH_PERSISTENCE_ENABLED=false
```

后端会降级为进程内 `MemorySaver`。代价是服务重启后，处于澄清/审批中断态的会话无法恢复。只建议本地临时调试使用。

---

## 五、配置 backend/.env

复制模板：

```bash
cd backend
cp .env.example .env
```

最少需要确认以下配置：

```dotenv
# 业务库：宿主机直接跑后端时用 127.0.0.1
MYSQL_URL=mysql+aiomysql://root:root@127.0.0.1:3306/smart_home

# LangGraph 中断态持久化
POSTGRES_URL=postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph
LANGGRAPH_PERSISTENCE_ENABLED=true

# 模型供应商
LLM_PROVIDER=qwen
QWEN_API_KEY=你的-key
QWEN_MODEL=qwen-plus

# RAG 文件入库必须
DASHSCOPE_API_KEY=你的-key

# JWT 密钥，至少本地换掉默认值
JWT_SECRET=用-openssl-rand-hex-32-生成
```

生成 JWT 密钥：

```bash
openssl rand -hex 32
```

### 5.1 用 Ollama 免 API Key

```bash
brew install ollama
ollama serve
ollama pull qwen2.5:7b
```

另开终端拉模型后，在 `.env` 中设置：

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_MODEL=qwen2.5:7b
```

`DASHSCOPE_API_KEY` 仍然是 RAG 文件入库的硬性依赖；没有它不要上传文件。

### 5.2 Docker 内跑后端时的连接串

如果后端也在 Docker 里，主机名要改成 compose 服务名：

```dotenv
MYSQL_URL=mysql+aiomysql://root:root@mysql:3306/smart_home
POSTGRES_URL=postgresql://langgraph:langgraph@postgres:5432/langgraph
```

本文默认后端在宿主机 venv 里跑，所以用 `127.0.0.1`。

---

## 六、启动后端

```bash
cd backend
source .venv/bin/activate
uvicorn homemind.main:app --reload --host 127.0.0.1 --port 8000
```

验证：

```bash
curl http://127.0.0.1:8000/
```

预期返回类似：

```json
{
  "service": "smart-home-backend",
  "status": "running",
  "docs": "/docs",
  "llm_provider": "qwen",
  "persistence": {"backend": "postgres", "store": "AsyncPostgresStore", "error": null}
}
```

打开接口文档：

```bash
open http://127.0.0.1:8000/docs
```

登录演示账号：

| 角色 | 用户名 | 密码 |
|---|---|---|
| 房主 | `owner01` | `123456` |
| 住户 | `resident01` | `123456` |
| 访客 | `guest01` | `123456` |

首次成功登录后，演示明文密码会自动升级为 bcrypt 哈希。

---

## 七、启动前端

前端不需要手敲，直接复用现有 Vue 工程。

```bash
cd frontend
npm ci
npm run dev
```

打开：

```bash
open http://127.0.0.1:5173
```

Vite 已配置 `/api` 代理到 `http://localhost:8000`，包含 WebSocket 代理，不需要额外改前端配置。

如果后端不在 8000，修改 `frontend/vite.config.js` 的 proxy target，或按前端代码支持的方式设置环境变量。

生产构建验证：

```bash
npm run build
```

---

## 八、测试与质量门禁

### 8.1 全量测试

```bash
cd backend
source .venv/bin/activate
pytest
```

测试设计为**零外部依赖**：

- 不需要 MySQL；
- 不需要 LLM API Key；
- 不需要网络。

数据库相关测试使用内存 SQLite；真实模型/端到端场景放在 `evals/`。

### 8.2 按阶段跑测试

按《后端从 0 到 1 手敲实现计划》逐阶段执行，例如：

```bash
pytest tests/test_repositories.py
pytest tests/test_services.py
pytest tests/test_rules_plan.py
pytest tests/test_agent_control.py
pytest tests/test_agent_api.py
```

### 8.3 静态检查

```bash
ruff check homemind tests
mypy homemind
```

### 8.4 评测

```bash
python -m evals.runner
python -m evals.e2e
python -m evals.api_benchmark
```

- `evals.runner` 规则模式离线可跑；
- `evals.e2e` 需要真实模型 API Key；
- `evals.api_benchmark` 使用 ASGI 直连 + 内存 SQLite。

---

## 九、可选能力

### 9.1 ChromaDB

```bash
python -m pip install -r requirements-optional.txt
```

不装时 `rag/vector_store.py` 会回退到本地 JSON + 余弦相似度，功能可用但规模有限。

### 9.2 Whisper 语音识别

Whisper 依赖较重（会拉 PyTorch），按需安装：

```bash
brew install ffmpeg
python -m pip install openai-whisper
```

首次使用会下载模型。只做后端重写和文字对话时不需要。

### 9.3 Edge-TTS

`edge-tts` 已包含在核心依赖中，不需要额外安装。Windows 上还有 SAPI 回退，macOS 主要使用 Edge-TTS。

---

## 十、一键初始化脚本

仓库根目录提供了 `scripts/setup_mac.sh`，只做项目内初始化，不会安装系统软件、不会覆盖已有 `.env`：

```bash
cd /path/to/ZHJJ
chmod +x scripts/setup_mac.sh
bash scripts/setup_mac.sh
```

脚本会：

1. 检查 Python/Node/npm；
2. 创建 `backend/.venv`；
3. 安装核心与开发依赖；
4. 从 `.env.example` 生成 `.env`（仅当不存在）；
5. 创建 `uploads/`、`chroma_data/`；
6. 执行 `npm ci`（仅当 `node_modules` 不存在）。

数据库仍需按第四节单独启动。

---

## 十一、每日开发流程

### 终端 1：数据库

```bash
cd backend
docker compose up -d mysql postgres
```

### 终端 2：后端

```bash
cd backend
source .venv/bin/activate
uvicorn homemind.main:app --reload --port 8000
```

### 终端 3：前端

```bash
cd frontend
npm run dev
```

### 每完成一个阶段

```bash
cd backend
source .venv/bin/activate
pytest tests/test_<stage>.py
pytest
ruff check homemind tests
```

---

## 十二、常见问题

### 12.1 `python3.11: command not found`

```bash
brew install python@3.11
echo 'export PATH="/opt/homebrew/opt/python@3.11/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

确认没有误用系统 Python：

```bash
which python3.11
```

### 12.2 `bcrypt` / `psycopg` 编译失败

先装 Xcode Command Line Tools，再升级 pip：

```bash
xcode-select --install
python -m pip install --upgrade pip setuptools wheel
python -m pip install "psycopg[binary,pool]" bcrypt
```

仍失败时：

```bash
brew install libpq pkg-config
```

并把 `libpq` 加入 PATH：

```bash
echo 'export PATH="/opt/homebrew/opt/libpq/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 12.3 `pip install` 在 Apple Silicon 上尝试从源码编译

确认当前 Python 是 arm64 原生版本：

```bash
python -c "import platform; print(platform.machine())"
```

应输出 `arm64`，不是 `x86_64`。如果输出 `x86_64`，说明用了 Rosetta 下的 Python，重新用 Homebrew 安装原生 Python。

### 12.4 MySQL 连接失败

检查容器：

```bash
docker compose ps
docker logs smart-home-mysql --tail 50
```

宿主机后端要用 `127.0.0.1:3306`；容器内后端才用 `mysql:3306`。

Homebrew MySQL 如果 root 无密码，连接串要写：

```dotenv
MYSQL_URL=mysql+aiomysql://root@127.0.0.1:3306/smart_home
```

### 12.5 Postgres 连接失败

```bash
docker compose ps
docker logs smart-home-postgres --tail 50
```

确认 `POSTGRES_URL` 的用户/密码/库名与 compose 一致。没有 Postgres 时设置：

```dotenv
LANGGRAPH_PERSISTENCE_ENABLED=false
```

### 12.6 健康检查显示 `persistence.backend=memory`

说明 Postgres 未连上，后端已降级。看后端日志中的 `LangGraph Postgres 持久化初始化失败`，修好 Postgres 后重启后端。

### 12.7 RAG 上传文件失败

检查是否配置：

```dotenv
DASHSCOPE_API_KEY=...
```

项目明确要求 RAG 使用阿里云 `text-embedding-v2`，未配置 Key 或调用失败会直接标记文件 `failed`，不会静默降级。

### 12.8 前端 5173 打不开或接口 404

确认：

```bash
curl http://127.0.0.1:8000/
```

后端正常后，检查 `frontend/vite.config.js` 的 proxy target 是否为 `http://localhost:8000`。如果后端跑在别的端口，改 target 后重启 `npm run dev`。

### 12.9 端口被占用

```bash
lsof -i :8000
lsof -i :5173
lsof -i :3306
lsof -i :5432
```

杀掉占用进程或换端口。

### 12.10 `npm ci` 报 lockfile 不一致

```bash
cd frontend
rm -rf node_modules
npm install
```

`npm install` 会更新 lockfile；如果不想改 lockfile，先确认 `package.json` 与 `package-lock.json` 是否来自同一版本。

---

## 十三、最简启动清单

如果只想快速跑起来，按下面复制：

```bash
# 1. 系统依赖
brew install python@3.11 node@20
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# 2. 配置
cp backend/.env.example backend/.env
# 编辑 backend/.env：MYSQL_URL、QWEN_API_KEY、DASHSCOPE_API_KEY、JWT_SECRET

# 3. 数据库
cd backend
docker compose up -d mysql postgres
cd ..

# 4. 后端
cd backend
source .venv/bin/activate
uvicorn homemind.main:app --reload --port 8000

# 5. 前端（另开终端）
cd frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`，用 `owner01 / 123456` 登录。

---

## 十四、与手敲重写计划的配合

按 `docs/后端从0到1手敲实现计划.md` 施工时：

- 阶段 0-2：只需要 venv + pytest，不依赖 MySQL；
- 阶段 3-6：需要 MySQL 才能手工验证 API；pytest 仍用内存 SQLite；
- 阶段 7-11：纯逻辑与 Agent 节点测试，不需要数据库和模型；
- 阶段 12-14：需要启动 Postgres、配置模型 Key 才能完整体验；
- 阶段 15：`evals.runner` 离线可跑，`evals.e2e` 需要真实模型。

建议每个阶段结束提交一次：

```bash
git add backend tests docs
git commit -m "stage N: <本阶段完成内容>"
```
