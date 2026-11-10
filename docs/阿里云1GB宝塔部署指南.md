# 阿里云 1GB + 宝塔面板：当前项目部署指南

> 如果你的服务器是 **Alibaba Cloud Linux 3 + MariaDB 10.5、Nginx 未安装**，优先看现场版：
> `docs/阿里云ALinux3-1GB现场部署步骤.md`。本文件是通用版，现场版按实际系统命令执行。

> 目标：在 1 核 1GB 阿里云服务器、宝塔 Linux 面板上，把当前 FastAPI + Vue 项目按接近企业级的方式部署起来，并理解每一步为什么这样做。
>
> 适用项目：`ZHJJ`（后端 `backend/homemind`，前端 `frontend`）。
>
> 重要结论先说：
>
> - **1GB 不适合作为正式生产环境**。MySQL 8 + FastAPI + Nginx + 宝塔面板本身就会接近 1GB；Postgres、ChromaDB、多 worker 都会把机器压垮。
> - 1GB 可以作为**学习/预发/演示环境**：单 worker、关闭 Postgres 持久化、关闭 ChromaDB、前端本地构建、加 2GB Swap。
> - 企业级标准是：应用与数据库分离，使用阿里云 RDS MySQL / RDS PostgreSQL / OSS / CDN / SLB，应用节点至少 2 核 4GB，多实例 + 健康检查 + 监控告警。本文最后一节会列出差距。

---

## 一、目标架构

```text
公网用户
  │ HTTPS 443
  ▼
阿里云安全组（只放行 80/443；SSH 限你的 IP）
  │
  ▼
Nginx（宝塔站点）
  ├─ /                 → /www/wwwroot/smart-home/frontend/dist
  ├─ /api/health       → 127.0.0.1:8000/
  ├─ /api/agent/v2/ws  → 127.0.0.1:8000（WebSocket Upgrade）
  └─ /api/             → 127.0.0.1:8000（REST + SSE）
                          │
                          ▼
                    FastAPI + Uvicorn（1 worker，systemd 守护）
                          │
                          ▼
                    MySQL 8.0（本机，低内存配置）
```

部署原则：

1. FastAPI 只监听 `127.0.0.1:8000`，不直接暴露公网。
2. 所有公网流量只经过 Nginx 的 80/443。
3. MySQL 只监听本机，不开放 3306。
4. 进程由 systemd 守护，SSH 断开不影响服务。
5. 配置和密钥只放 `backend/.env`，权限 600，不提交仓库。

---

## 二、1GB 内存预算与取舍

| 组件 | 约占用 | 说明 |
|---|---:|---|
| Linux + 宝塔面板 | 250-350MB | 面板本身也吃内存 |
| Nginx | 10-30MB | 静态资源 + 反向代理 |
| MySQL 8（低内存配置） | 300-450MB | buffer pool 256MB 起步 |
| FastAPI + Uvicorn 1 worker | 180-300MB | LangGraph/依赖加载后 |
| Postgres | 0 | **1GB 上关闭**，否则容易 OOM |
| ChromaDB | 0 | **1GB 上不安装**，用本地 JSON 回退 |
| 合计 | 约 800MB-1.1GB | 必须加 2GB Swap 兜底 |

因此 1GB 上必须做这些取舍：

- `LANGGRAPH_PERSISTENCE_ENABLED=false`：用 MemorySaver，服务重启后中断态丢失；换正式环境再接 Postgres。
- 不安装 `chromadb`：RAG 回退本地 JSON 向量检索；embedding 仍然需要 `DASHSCOPE_API_KEY`。
- 不安装 `openai-whisper`：语音识别不可用；文字聊天不受影响。
- Uvicorn 只开 `--workers 1`：不要用 `gunicorn -w 4`。
- 前端在本地构建，上传 `dist/`；不要在 1GB 服务器上跑 `npm run build`，很容易 OOM。
- 关闭宝塔里不用的 PHP 版本、phpMyAdmin 公网访问、无关插件。

---

## 三、部署前检查

登录服务器（宝塔终端或 SSH），执行：

```bash
cat /etc/os-release
uname -m
free -h
df -h
nproc
id www
systemctl status nginx --no-pager
mysql --version || true
```

确认：

- 系统是 Ubuntu 22.04/24.04、Debian 12 或 CentOS/Alma/Rocky 8+；
- 磁盘至少 20GB 可用（MySQL + 日志 + 备份）；
- 宝塔面板已安装 Nginx；
- `www` 用户存在（宝塔默认创建）。

查看当前内存占用：

```bash
ps aux --sort=-%mem | head -n 10
```

如果 PHP、phpMyAdmin、其他站点占了很多内存，先在宝塔里停掉不用的服务。

---

## 四、Step 1：安全组与宝塔面板加固

### 4.1 阿里云安全组

入方向只保留：

| 端口 | 来源 | 用途 |
|---|---|---|
| 22 | 你的公网 IP/32 | SSH |
| 80 | 0.0.0.0/0 | HTTP（跳 HTTPS） |
| 443 | 0.0.0.0/0 | HTTPS |
| 8888（或你改后的面板端口） | 你的公网 IP/32 | 宝塔面板 |

**不要放行**：8000、3306、5432、6379、8888 对全网。

出方向默认放行即可；项目需要访问 Qwen/DeepSeek/DashScope 的 443。

> 如果服务器在中国内地，域名绑定 80/443 通常需要 ICP 备案；没有备案时先用 IP + 非标准端口做学习验证，或使用中国香港地域。具体以阿里云当前规则为准。

### 4.2 宝塔面板加固

在宝塔「面板设置」中：

1. 修改面板端口，不要用默认 8888；
2. 开启面板 SSL；
3. 设置「授权 IP」，只允许你的公网 IP；
4. 修改面板密码为强密码；
5. 关闭面板的「公开访问」；
6. 删除不用的 PHP 版本、phpMyAdmin 公网入口、示例站点。

### 4.3 SSH 加固

```bash
# 确认你可以用密钥登录后，再禁用密码登录
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sudo systemctl reload sshd
```

不同发行版服务名可能是 `ssh` 或 `sshd`，先 `systemctl status ssh` 确认。

> 改 SSH 配置前，务必保留一个已登录的终端窗口，避免把自己锁在外面。

---

## 五、Step 2：增加 2GB Swap

1GB 物理内存必须加 Swap，主要作用是防止 MySQL/后端被 OOM Killer 直接杀掉。

```bash
sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

设置较低 swappiness，尽量优先用物理内存：

```bash
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

验证：

```bash
swapon --show
free -h
```

应看到 2GB swap。

> 某些云盘上 `fallocate` 可能失败，命令里已经用 `dd` 兜底。Swap 只是兜底，不是性能方案；频繁 swap 说明内存不够。

---

## 六、Step 3：安装并调优 MySQL 8

### 6.1 安装方式选择

优先级从高到低：

1. **阿里云 RDS MySQL 8.0（企业推荐）**：不占本机内存，自动备份/监控；1GB 应用机只跑后端。
2. **宝塔软件商店安装 MySQL 8.0**：图形化，适合学习；但 1GB 可能触发面板的最低内存检查。
3. **命令行安装 MySQL 8.0**：可控，但需要自己维护；不推荐生产。

如果宝塔因为内存不足拒绝安装：

- 先确认 Swap 已生效，再重试；
- 仍拒绝时，不要修改宝塔面板源码绕过检查；
- 改用 RDS，或升级到 2 核 4GB，或命令行安装。

### 6.2 宝塔安装 MySQL 8.0

宝塔「软件商店」→ 搜索 MySQL 8.0 → 安装。

安装完成后：

1. 「数据库」→ 添加数据库：
   - 数据库名：`smart_home`
   - 用户名：`homemind`
   - 密码：强随机密码
   - 访问权限：本地服务器（`localhost` / `127.0.0.1`）
2. 不要开启远程访问 3306。
3. 导入项目初始化 SQL（见 Step 4）。

### 6.3 低内存配置

打开宝塔「软件商店 → MySQL → 设置 → 配置修改」，把 `deploy/mysql/1gb-low-memory.cnf` 的内容合并进 `[mysqld]`。

核心参数：

```ini
innodb_buffer_pool_size = 256M
innodb_buffer_pool_instances = 1
innodb_buffer_pool_chunk_size = 128M
max_connections = 40
performance_schema = OFF
mysqlx = 0
skip-log-bin
tmp_table_size = 16M
max_heap_table_size = 16M
sort_buffer_size = 256K
join_buffer_size = 256K
table_open_cache = 64
innodb_io_capacity = 200
innodb_flush_method = O_DIRECT
```

保存后重启 MySQL。

验证：

```bash
mysql -u homemind -p -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size';"
mysql -u homemind -p -e "SHOW VARIABLES LIKE 'max_connections';"
```

如果 MySQL 仍然频繁 OOM：

- 把 `innodb_buffer_pool_size` 降到 `128M`；
- 把 `max_connections` 降到 `20`；
- 确认没有其他 PHP/Java 站点在抢内存；
- 查看 `dmesg -T | grep -i "killed process"`。

### 6.4 关于 `init.sql`

项目 `database/init.sql` 会：

- `DROP DATABASE IF EXISTS smart_home`；
- 重新创建数据库和 10 张表；
- 插入演示家庭、用户、设备、场景、偏好数据。

**只适合首次初始化**。后续表结构变更应使用 Alembic 迁移，不要重复执行 `init.sql`，否则会清空数据。

首次部署：

```bash
cd /www/wwwroot/smart-home
mysql -u homemind -p smart_home < database/init.sql
```

如果 `homemind` 没有建库/删库权限，先用 root 导入，再给应用用户授权：

```sql
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
ON smart_home.* TO 'homemind'@'127.0.0.1';
FLUSH PRIVILEGES;
```

生产环境还要：

- 删除或修改演示账号 `owner01/owner02/...`；
- 修改演示密码；
- 不要把 root 账号写进 `.env`。

---

## 七、Step 4：上传代码与创建轻量 venv

### 7.1 目录规划

```text
/www/wwwroot/smart-home/
├── backend/
│   ├── .venv/
│   ├── .env
│   ├── homemind/
│   ├── uploads/
│   └── chroma_data/
├── frontend/
│   └── dist/
├── database/
└── deploy/
```

### 7.2 上传代码

方式一：服务器 `git clone`（推荐）

```bash
sudo mkdir -p /www/wwwroot/smart-home
sudo chown -R www:www /www/wwwroot/smart-home
cd /www/wwwroot/smart-home
sudo -u www git clone <你的仓库地址> .
```

方式二：宝塔「文件」上传压缩包，解压到 `/www/wwwroot/smart-home`。

不要上传本地的 `.venv`、`node_modules`、`uploads`、`chroma_data`、`backend/.env`。

### 7.3 安装 Python 3.11

先看系统：

```bash
cat /etc/os-release
```

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev build-essential git curl
```

CentOS / Alma / Rocky：

```bash
sudo yum install -y python3.11 python3.11-devel gcc gcc-c++ make git curl
```

如果系统源没有 Python 3.11：

- 用宝塔「Python 项目管理器 → 版本管理」安装 3.11；
- 或使用 `pyenv` 编译安装（需要编译依赖和足够内存/Swap）；
- 或者换 Ubuntu 22.04 镜像。

确认：

```bash
python3.11 --version
```

### 7.4 创建 venv 并安装依赖

```bash
cd /www/wwwroot/smart-home/backend
sudo -u www python3.11 -m venv .venv
sudo -u www .venv/bin/python -m pip install --upgrade pip setuptools wheel
sudo -u www .venv/bin/pip install --no-cache-dir -r requirements.txt
```

只安装 `requirements.txt`，不要安装：

- `requirements-dev.txt`（pytest/ruff/mypy/langgraph-cli）；
- `requirements-optional.txt`（ChromaDB/Whisper）。

如果 pip 安装时 OOM：

```bash
# 确认 swap 已生效
free -h

# 逐个安装大包，定位是哪一个包吃内存
sudo -u www .venv/bin/pip install --no-cache-dir fastapi uvicorn
sudo -u www .venv/bin/pip install --no-cache-dir sqlalchemy aiomysql pymysql
sudo -u www .venv/bin/pip install --no-cache-dir langgraph langgraph-checkpoint-postgres
sudo -u www .venv/bin/pip install --no-cache-dir -r requirements.txt
```

创建运行目录：

```bash
sudo -u www mkdir -p /www/wwwroot/smart-home/backend/uploads
sudo -u www mkdir -p /www/wwwroot/smart-home/backend/chroma_data
```

---

## 八、Step 5：配置生产 `.env`

```bash
cd /www/wwwroot/smart-home/backend
sudo -u www cp .env.example .env
sudo -u www chmod 600 .env
```

编辑 `backend/.env`，1GB 版本建议：

```dotenv
APP_ENV=production

# 业务库：本机 MySQL
MYSQL_URL=mysql+aiomysql://homemind:强密码@127.0.0.1:3306/smart_home

# 1GB 不跑 Postgres，关闭 LangGraph 持久化
LANGGRAPH_PERSISTENCE_ENABLED=false
POSTGRES_URL=postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph
LANGGRAPH_POOL_MAX_SIZE=2

# 站点域名；没有域名时写 http://服务器公网IP
CORS_ORIGINS=https://your-domain.com
TRUST_PROXY_HEADERS=true

# JWT：必须换掉默认值
JWT_SECRET=用-openssl-rand-hex-32-生成
JWT_EXPIRE_HOURS=24

# 模型：1GB 不要跑本地 Ollama，使用云端 API
LLM_PROVIDER=qwen
QWEN_API_KEY=你的-key
QWEN_MODEL=qwen-plus

# RAG 文件入库必须；没有就暂时不要上传文件
DASHSCOPE_API_KEY=你的-key

# 1GB 降低并发/上下文开销
AGENT_CONTEXT_TOKEN_BUDGET=1200
AGENT_MAX_PLAN_TASKS=3
AGENT_MAX_REFLECTIONS=1
AGENT_MAX_CLARIFICATIONS=2

# 不需要设备模拟时关闭，省一点资源
ENABLE_SCHEDULER=false

# 不接 LangSmith
LANGSMITH_TRACING=false
```

生成 JWT 密钥：

```bash
openssl rand -hex 32
```

注意两个常见连接问题：

- MySQL 密码里如果包含 `@ : / # ?` 等字符，写进 `MYSQL_URL` 前要做 URL 编码，否则连接串会被截断。
- 宝塔建库时用户主机可能是 `localhost`，而 `.env` 写的是 `127.0.0.1`。如果报 `Access denied`，在宝塔数据库权限里同时授权 `localhost` 和 `127.0.0.1`，或把连接串主机改成 `localhost`。

### 8.1 为什么 `APP_ENV=production` 很重要

项目启动时会检查 JWT 密钥。如果 `APP_ENV=production` 且 `JWT_SECRET` 仍是默认值，服务会拒绝启动。这是防止生产环境使用公开默认密钥。

### 8.2 为什么关闭 Postgres 持久化

项目用 Postgres 保存 LangGraph 的澄清/审批中断态。1GB 同时跑 MySQL + Postgres + FastAPI 很容易 OOM。关闭后：

- 服务重启，处于中断态的会话无法恢复；
- 单进程内审批/澄清仍然可用；
- 正式环境应接阿里云 RDS PostgreSQL，再打开 `LANGGRAPH_PERSISTENCE_ENABLED=true`。

### 8.3 为什么不要装 ChromaDB

ChromaDB 会额外占用内存。1GB 上不安装时，`rag/vector_store.py` 会回退到本地 JSON + 余弦相似度：

- 功能可用，适合小规模文档；
- 仍然需要 `DASHSCOPE_API_KEY` 做 embedding；
- 文档量大时再换 Chroma 或云向量库。

---

## 九、Step 6：手工启动并验证后端

先不要急着配 systemd，先确认应用本身能起来。

```bash
cd /www/wwwroot/smart-home/backend
sudo -u www .venv/bin/uvicorn homemind.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips=127.0.0.1
```

另开一个终端：

```bash
curl http://127.0.0.1:8000/
```

预期返回：

```json
{
  "service": "smart-home-backend",
  "status": "running",
  "docs": "/docs",
  "llm_provider": "qwen",
  "persistence": {"backend": "memory", "store": null, "error": null}
}
```

`persistence.backend=memory` 是 1GB 版本的预期结果。

如果启动失败，按顺序检查：

```bash
# 1. Python 依赖
.venv/bin/python -c "import fastapi, sqlalchemy, langgraph; print('ok')"

# 2. 数据库连接
mysql -u homemind -p -h 127.0.0.1 smart_home -e "select 1;"

# 3. 端口占用
ss -lntp | grep 8000

# 4. 环境变量
grep -E "MYSQL_URL|APP_ENV|JWT_SECRET" .env
```

确认无误后 `Ctrl+C` 停掉手工进程，进入 systemd。

---

## 十、Step 7：用 systemd 守护后端

### 10.1 安装服务文件

```bash
sudo cp /www/wwwroot/smart-home/deploy/systemd/smart-home-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smart-home-api
```

### 10.2 查看状态与日志

```bash
sudo systemctl status smart-home-api --no-pager
sudo journalctl -u smart-home-api -f
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8000/
```

### 10.3 常用操作

```bash
sudo systemctl restart smart-home-api
sudo systemctl stop smart-home-api
sudo systemctl start smart-home-api
sudo systemctl disable smart-home-api
```

> 服务文件里使用 `www` 用户，路径固定 `/www/wwwroot/smart-home/backend`。如果你放在别的目录，改 `WorkingDirectory` 和 `ExecStart`。

### 10.4 为什么不建议在 1GB 上用 Gunicorn 多 worker

Gunicorn + 2/4 个 Uvicorn worker 会成倍增加 Python 内存。1 核 1GB 上：

- 1 个 Uvicorn worker 足够学习/演示；
- 多 worker 适合 2 核 4GB 以上；
- 企业级多实例应放在负载均衡后面，而不是单机堆 worker。

---

## 十一、Step 8：构建前端并上传静态文件

### 11.1 推荐：本地构建

在本地 Mac/Windows：

```bash
cd frontend
npm ci
npm run build
```

产出 `frontend/dist/`。

上传到服务器：

```bash
# 在本地执行，替换 IP 和路径
scp -r frontend/dist/* root@<服务器IP>:/www/wwwroot/smart-home/frontend/dist/
```

或者用宝塔「文件」上传 `dist` 压缩包并解压。

服务器权限：

```bash
sudo chown -R www:www /www/wwwroot/smart-home/frontend/dist
```

### 11.2 备选：服务器构建

1GB 上构建可能 OOM，必须限制 Node 内存并确保 Swap 生效：

```bash
cd /www/wwwroot/smart-home/frontend
npm ci
NODE_OPTIONS=--max-old-space-size=512 npm run build
```

如果仍然失败，改回本地构建。

---

## 十二、Step 9：宝塔建站、Nginx 反向代理与 HTTPS

### 12.1 创建站点

宝塔「网站」→「添加站点」：

- 域名：`your-domain.com`
- 根目录：`/www/wwwroot/smart-home/frontend/dist`
- PHP 版本：纯静态
- 数据库：不创建

### 12.2 配置 Nginx

进入站点「设置」→「配置文件」，把 `deploy/nginx/smart-home.conf` 的内容合并进 `server { ... }`。

关键点：

- `/api/health` 代理到后端 `/`，因为后端根路径被前端占用；
- `/api/agent/v2/ws` 必须带 `Upgrade` / `Connection`；
- `/api/` 关闭 `proxy_buffering`，否则 SSE 不逐字输出；
- `client_max_body_size 30m` 支持文件/音频上传；
- `proxy_read_timeout 300s` 适应 LLM 慢响应；
- `/` 使用 `try_files ... /index.html` 支持 Vue Router history。

保存后检查并重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 12.3 申请 HTTPS

宝塔站点「SSL」→「Let's Encrypt」→ 申请证书 → 开启「强制 HTTPS」。

申请前确认：

- 域名已解析到服务器公网 IP；
- 安全组已放行 80/443；
- 国内服务器域名已完成 ICP 备案。

没有域名时：

- 先用 `http://服务器IP` 学习部署；
- Let's Encrypt 不能给纯 IP 签发证书；
- 可临时用自签证书，但浏览器会告警，不建议长期。

### 12.4 验证

```bash
curl -I https://your-domain.com/
curl https://your-domain.com/api/health
```

预期：

- 根路径返回前端 `index.html`；
- `/api/health` 返回后端健康 JSON；
- 浏览器登录 `owner01 / 123456` 后可进入系统。

---

## 十三、Step 10：防火墙与安全收口

### 13.1 只暴露必要端口

```bash
# 如果使用 firewalld
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload

# 如果使用 ufw
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

不要放行 8000、3306、5432、8888。

### 13.2 宝塔与 SSH

- 宝塔面板端口只允许你的 IP；
- 开启面板 SSL；
- SSH 使用密钥，禁用密码登录；
- 安装宝塔「Fail2ban」插件，保护 SSH；
- 删除演示站点、默认页面、phpMyAdmin 公网入口。

### 13.3 密钥与权限

```bash
sudo chown www:www /www/wwwroot/smart-home/backend/.env
sudo chmod 600 /www/wwwroot/smart-home/backend/.env
sudo chmod 700 /www/wwwroot/smart-home/backend/.venv
```

确认 `.env` 不在 git 中：

```bash
cd /www/wwwroot/smart-home
git check-ignore -v backend/.env
```

---

## 十四、Step 11：验收清单

按顺序执行：

```bash
# 1. 服务状态
sudo systemctl status smart-home-api --no-pager
sudo systemctl status nginx --no-pager

# 2. 后端健康
curl -fsS http://127.0.0.1:8000/
curl -fsS https://your-domain.com/api/health

# 3. 前端
curl -I https://your-domain.com/

# 4. 登录
curl -X POST https://your-domain.com/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"owner01","password":"123456"}'

# 5. 资源
free -h
df -h
ps aux --sort=-%mem | head -n 10

# 6. 日志
sudo journalctl -u smart-home-api --since "10 min ago" --no-pager
sudo tail -n 50 /www/wwwlogs/your-domain.com.error.log
```

浏览器验收：

1. 登录；
2. 设备列表能加载；
3. 设备状态能修改；
4. 场景能执行；
5. AI 聊天能回复；
6. 高风险操作能弹审批；
7. 审批通过/拒绝都能继续；
8. 文件上传后能问答（如果配置了 `DASHSCOPE_API_KEY`）；
9. 刷新任意前端路由不 404；
10. WebSocket 不报 400/404。

---

## 十五、Step 12：日常运维

### 15.1 查看日志

```bash
sudo journalctl -u smart-home-api -f
sudo journalctl -u smart-home-api --since today
sudo tail -f /www/wwwlogs/your-domain.com.error.log
```

### 15.2 查看资源

```bash
free -h
df -h
ps aux --sort=-%mem | head -n 10
ss -lntp
mysql -u homemind -p -e "SHOW PROCESSLIST;"
```

### 15.3 备份 MySQL

使用 `deploy/scripts/backup_mysql.sh`，建议放到宝塔「计划任务」，每天 03:00：

```bash
export MYSQL_USER=homemind
export MYSQL_PASSWORD='强密码'
bash /www/wwwroot/smart-home/deploy/scripts/backup_mysql.sh
```

生产建议：

- 备份文件同步到阿里云 OSS；
- 至少保留 7 天；
- 定期做恢复演练；
- `.env` 和 JWT 密钥单独离线备份。

### 15.4 发布更新

后端：

```bash
cd /www/wwwroot/smart-home
bash deploy/scripts/deploy_backend.sh
```

前端：

```bash
# 本地构建后上传 dist
scp -r frontend/dist/* root@<服务器IP>:/www/wwwroot/smart-home/frontend/dist/
```

### 15.5 回滚

```bash
cd /www/wwwroot/smart-home
git log --oneline -5
git checkout <上一个稳定提交>
sudo systemctl restart smart-home-api
```

数据库变更要保证向后兼容；不要在没有备份的情况下执行破坏性 SQL。

---

## 十六、1GB 进一步优化与升级路径

### 16.1 还能省的地方

- 关闭不用的宝塔 PHP 版本；
- 关闭 `ENABLE_SCHEDULER`；
- `AGENT_CONTEXT_TOKEN_BUDGET=1200`；
- `AGENT_MAX_PLAN_TASKS=3`；
- `AGENT_MAX_REFLECTIONS=1`；
- 不安装 ChromaDB、Whisper；
- MySQL buffer pool 从 256M 降到 128M（如果 OOM）；
- 日志轮转，避免磁盘满；
- 前端静态资源上 CDN。

### 16.2 企业级标准差距

| 维度 | 当前 1GB 学习版 | 企业级标准 |
|---|---|---|
| 应用节点 | 1 核 1GB，单 worker | 2 核 4GB 起，多实例 |
| 业务库 | 本机 MySQL 8 | 阿里云 RDS MySQL 8，多可用区 |
| LangGraph 持久化 | MemorySaver，关闭 Postgres | 托管 PostgreSQL，开启 checkpointer |
| 向量库 | 本地 JSON 回退 | 托管向量库 / 独立 Chroma 服务 |
| 文件存储 | 本机 uploads | 阿里云 OSS |
| 静态资源 | Nginx 本机 | CDN + OSS |
| 进程管理 | systemd 单实例 | systemd/K8s + 健康检查 + 滚动发布 |
| 监控 | 宝塔 + 手工命令 | Prometheus/Grafana/云监控 + 告警 |
| 日志 | journald + Nginx 日志 | 集中日志（SLS/Loki） |
| 备份 | 本机 mysqldump | 自动备份 + 异地容灾 + 恢复演练 |
| 安全 | 安全组 + 宝塔 + Fail2ban | WAF + 堡垒机 + 最小权限 + 密钥管理 |
| 发布 | git pull + 重启 | CI/CD + 灰度/蓝绿发布 |

### 16.3 推荐升级顺序

1. 应用节点升到 2 核 4GB；
2. MySQL 换 RDS；
3. 打开 Postgres 持久化；
4. 上 OSS + CDN；
5. 加监控告警；
6. 再做多实例和滚动发布。

---

## 十七、常见问题排查

### 17.1 502 Bad Gateway

```bash
sudo systemctl status smart-home-api
sudo journalctl -u smart-home-api -n 100 --no-pager
ss -lntp | grep 8000
```

常见原因：

- 后端没启动；
- 端口不是 8000；
- Nginx `proxy_pass` 地址写错；
- SELinux 阻止 Nginx 访问本机端口（CentOS）。

### 17.2 504 Gateway Timeout

- LLM 响应慢：确认 Nginx `proxy_read_timeout 300s`；
- 工具执行慢：检查后端日志和外部 API；
- 1GB 内存不足导致 swap 抖动：`free -h`、`vmstat 1`。

### 17.3 WebSocket 400/404

- Nginx 缺少：
  ```nginx
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  ```
- 路径必须是 `/api/agent/v2/ws`；
- HTTPS 页面必须用 `wss://`；
- 检查浏览器 Network → WS。

### 17.4 SSE 不逐字输出

确认 `/api/` 配置了：

```nginx
proxy_buffering off;
proxy_cache off;
```

### 17.5 上传 413

调大 Nginx：

```nginx
client_max_body_size 30m;
```

同时确认后端 `max_file_size` / `max_audio_size` 配置。

### 17.6 MySQL 被 OOM Killer 杀掉

```bash
dmesg -T | grep -i "killed process"
free -h
```

处理：

- 降 `innodb_buffer_pool_size`；
- 降 `max_connections`；
- 关闭其他占内存服务；
- 确认 Swap 生效；
- 长期方案升级内存或使用 RDS。

### 17.7 启动报 JWT 密钥不安全

`APP_ENV=production` 时，默认 `JWT_SECRET` 会被拒绝。执行：

```bash
openssl rand -hex 32
```

写入 `.env` 后重启。

### 17.8 健康检查显示 `persistence.backend=memory`

1GB 版本这是预期。需要中断态跨重启恢复时：

- 接阿里云 RDS PostgreSQL；
- 设置 `LANGGRAPH_PERSISTENCE_ENABLED=true`；
- 配置 `POSTGRES_URL`；
- 重启后端，确认健康检查显示 `postgres`。

### 17.9 前端刷新 404

确认 Nginx：

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

### 17.10 `npm run build` OOM

- 本地构建后上传 `dist`；
- 或加 Swap，设置 `NODE_OPTIONS=--max-old-space-size=512`；
- 关闭其他占内存进程。

---

## 十八、部署完成后的企业级检查表

- [ ] 安全组只开放 22（限 IP）、80、443、面板端口（限 IP）。
- [ ] 宝塔面板改端口、开 SSL、授权 IP、强密码。
- [ ] SSH 密钥登录，禁用密码登录。
- [ ] 2GB Swap 已启用并写入 `/etc/fstab`。
- [ ] MySQL 8 低内存配置已生效。
- [ ] 数据库使用独立应用账号，不用 root。
- [ ] `.env` 权限 600，且不在 git 中。
- [ ] `APP_ENV=production`，`JWT_SECRET` 已更换。
- [ ] FastAPI 只监听 `127.0.0.1:8000`。
- [ ] systemd 开机自启、崩溃自动拉起。
- [ ] Nginx 配置 `nginx -t` 通过。
- [ ] HTTPS 证书自动续期。
- [ ] `/api/health` 可访问。
- [ ] WebSocket 可连接。
- [ ] SSE 逐字输出。
- [ ] 前端路由刷新不 404。
- [ ] MySQL 每日备份，且做过恢复演练。
- [ ] 日志轮转，磁盘不会被打满。
- [ ] 监控能看到 CPU、内存、磁盘、接口错误。
- [ ] 发布和回滚步骤已实际演练。

---

## 十九、参考来源

- 宝塔面板部署 Python 项目（详细教程）：https://www.cnblogs.com/lujugeo/articles/20519838
- 宝塔面板部署 FastAPI：Gunicorn + Nginx 反代：https://m.php.cn/faq/2409839.html
- Vue + FastAPI 项目宝塔部署指南：https://m.blog.csdn.net/June_Swift/article/details/160716142
- 1 核 1GB 云服务器部署建议（Swap、CDN）：https://smartmll.com/archives/64757.html
- 宝塔 MySQL 8.0 内存过高：Buffer Pool 与 Binlog 优化：https://m.php.cn/faq/2380829.html
- 宝塔 MySQL 内存不足频繁重启：Swap 与并发限制：https://m.php.cn/faq/2353041.html
- 宝塔安装 MySQL 8.0 内存不足：2GB Swap 实操：https://m.php.cn/faq/2419790.html
- Gunicorn + systemd + Nginx 部署 FastAPI：https://bbs.huaweicloud.com/blogs/519295
- FastAPI 生产部署：systemd + Nginx：https://blog.csdn.net/jjiejingtazhu/article/details/163148990
- Nginx 反代 FastAPI 的超时与连接问题：https://blog.csdn.net/Y_gao/article/details/159820038
