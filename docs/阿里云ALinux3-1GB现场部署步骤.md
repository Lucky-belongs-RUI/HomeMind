# Alibaba Cloud Linux 3 + 1GB + MariaDB：现场部署步骤

> 本文按你刚提供的真实环境定制：
>
> - Alibaba Cloud Linux 3.2104 U12（RHEL 8 系）
> - x86_64
> - 2 vCPU / 896Mi 内存 / 3Gi Swap / 30G 磁盘
> - `www` 用户已存在（uid/gid 1000）
> - 已安装 **MariaDB 10.5.27**，不是 MySQL 8
> - Nginx 尚未安装（`nginx.service` 不存在）
>
> 结论：**不用重装 MySQL 8**，先用现有 MariaDB 10.5 跑通学习环境；但要按 MariaDB 的低内存配置调优，并清楚 10.5 已停止维护，正式环境应升级 MariaDB 10.11 LTS 或使用阿里云 RDS MySQL 8。

---

## 一、当前环境判断

| 项目 | 现状 | 部署决策 |
|---|---|---|
| 内存 | 896Mi，已用 346Mi，可用 549Mi | 单 Uvicorn worker；MariaDB buffer pool 256M；不跑 Postgres/Chroma |
| Swap | 3Gi 已启用 | 不需要再创建；确认 `swapon --show` 即可 |
| CPU | 2 vCPU | 仍只开 1 个 worker，内存比 CPU 更紧张 |
| 磁盘 | 30G，可用 20G | 够用；日志和备份要轮转 |
| 数据库 | MariaDB 10.5.27 | 项目没有 MySQL 8 专属语法，可先兼容运行 |
| Nginx | 未安装 | 先在宝塔软件商店安装 Nginx，或 `dnf install nginx` |
| 用户 | `admin`（非 root），`www` 已存在 | 命令用 `sudo`；应用进程用 `www` |

先确认你有 sudo 权限：

```bash
sudo -v
```

如果提示没有 sudo，先用 root 登录或让管理员授权。

---

## 二、Step 1：确认宝塔、Nginx、MariaDB 状态

### 2.1 确认宝塔面板

```bash
which bt
sudo bt default
```

如果 `bt` 不存在，说明宝塔面板可能没装好，或者不在当前 PATH。先确认：

```bash
ls -ld /www/server/panel
```

### 2.2 确认 Nginx 是否已安装但没注册服务

```bash
which nginx
ps aux | grep -E 'nginx|openresty|tengine' | grep -v grep
ls -l /www/server/nginx/sbin/nginx 2>/dev/null
ls -l /www/server/openresty/nginx/sbin/nginx 2>/dev/null
systemctl list-unit-files | grep -Ei 'nginx|openresty|tengine'
```

如果 `/www/server/nginx/sbin/nginx` 存在，说明宝塔 Nginx 已安装但 systemd 服务名可能不是 `nginx`，可以直接在宝塔面板启动。

如果没有 Nginx：

1. 宝塔「软件商店」→ 搜索 Nginx → 安装稳定版（1.24/1.26）；
2. 或在面板「网站」里按提示安装 Nginx；
3. 不建议同时装 Apache/OpenLiteSpeed，避免端口冲突。

### 2.3 确认 MariaDB 服务

```bash
systemctl list-unit-files | grep -Ei 'mariadb|mysql'
systemctl status mariadb --no-pager || systemctl status mysqld --no-pager
sudo ss -lntp | grep 3306
```

MariaDB 服务名通常是 `mariadb`。如果没启动：

```bash
sudo systemctl enable --now mariadb
```

验证登录：

```bash
sudo mariadb -e "SELECT VERSION(); SHOW DATABASES;"
```

如果 `sudo mariadb` 不行，试：

```bash
sudo mysql -e "SELECT VERSION();"
```

---

## 三、Step 2：上传代码与 Python 3.11 环境

### 3.1 创建目录并上传代码

```bash
sudo mkdir -p /www/wwwroot/smart-home
sudo chown -R www:www /www/wwwroot/smart-home

# 方式一：服务器 git clone
sudo dnf install -y git curl
cd /www/wwwroot/smart-home
sudo -u www git clone <你的仓库地址> .

# 方式二：宝塔文件管理器上传压缩包，解压到 /www/wwwroot/smart-home
```

确认目录：

```bash
ls -la /www/wwwroot/smart-home
```

应该看到 `backend/`、`frontend/`、`database/`、`deploy/`。

### 3.2 安装 Python 3.11

先检查：

```bash
python3.11 --version || true
sudo dnf list available python3.11 python3.11-devel python3.11-pip
```

如果可用：

```bash
sudo dnf install -y python3.11 python3.11-devel python3.11-pip
```

如果 dnf 源里没有 3.11：

- 优先用宝塔「Python 项目管理器 → 版本管理」安装 Python 3.11；
- 或使用 `uv` 安装独立 Python（不污染系统）：

```bash
# 以 www 用户安装到自己的 HOME，避免 root 权限
sudo -u www -H bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u www -H bash -lc '~/.local/bin/uv python install 3.11'
```

先确认 `www` 的 HOME：

```bash
getent passwd www
```

### 3.3 创建 venv

如果使用系统 Python：

```bash
cd /www/wwwroot/smart-home/backend
sudo -u www -H python3.11 -m venv .venv
sudo -u www -H .venv/bin/python -m pip install --upgrade pip setuptools wheel
sudo -u www -H .venv/bin/pip install --no-cache-dir -r requirements.txt
```

如果使用 uv：

```bash
cd /www/wwwroot/smart-home/backend
sudo -u www -H bash -lc '~/.local/bin/uv venv .venv --python 3.11'
sudo -u www -H bash -lc '~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt'
```

只安装 `requirements.txt`：

- 不装 `requirements-dev.txt`；
- 不装 `requirements-optional.txt`；
- 1GB 上不装 ChromaDB、Whisper。

创建运行目录：

```bash
sudo -u www mkdir -p /www/wwwroot/smart-home/backend/uploads
sudo -u www mkdir -p /www/wwwroot/smart-home/backend/chroma_data
```

如果 pip 安装中途 OOM：

```bash
free -h
swapon --show
```

3GB Swap 已经在，但安装仍然慢。可以分组安装定位大包：

```bash
sudo -u www -H .venv/bin/pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic pydantic-settings
sudo -u www -H .venv/bin/pip install --no-cache-dir sqlalchemy aiomysql pymysql cryptography
sudo -u www -H .venv/bin/pip install --no-cache-dir -r requirements.txt
```

---

## 四、Step 3：调优 MariaDB 10.5

### 4.1 先备份原配置和数据库

```bash
sudo cp /etc/my.cnf /etc/my.cnf.bak.$(date +%F) 2>/dev/null || true
sudo mysqldump --all-databases --single-transaction > ~/all-databases-backup-$(date +%F).sql
```

确认现有数据库：

```bash
sudo mariadb -e "SHOW DATABASES;"
```

### 4.2 找到 MariaDB 实际读取的配置文件

```bash
mariadb --help --verbose | grep -A2 "Default options"
```

RHEL 系通常读取：

```text
/etc/my.cnf
/etc/my.cnf.d/*.cnf
```

宝塔 MariaDB 可能在：

```text
/www/server/mariadb/etc/my.cnf
```

如果是宝塔管理，优先在面板「软件商店 → MariaDB → 设置 → 配置修改」里改；直接改文件可能被面板覆盖。

### 4.3 应用低内存配置

仓库已经提供：

```text
deploy/mysql/1gb-low-memory-mariadb.cnf
```

RHEL 系直接复制：

```bash
sudo cp /www/wwwroot/smart-home/deploy/mysql/1gb-low-memory-mariadb.cnf /etc/my.cnf.d/99-low-memory.cnf
```

如果是宝塔 MariaDB，把文件内容粘贴到面板的「配置修改」中。

核心参数：

```ini
innodb_buffer_pool_size = 256M
innodb_buffer_pool_instances = 1
max_connections = 40
performance_schema = OFF
query_cache_type = 0
query_cache_size = 0
skip-log-bin
tmp_table_size = 16M
max_heap_table_size = 16M
sort_buffer_size = 256K
join_buffer_size = 256K
table_open_cache = 64
bind-address = 127.0.0.1
```

> MariaDB 10.5 不要照搬 MySQL 8 的 `mysqlx=0` 和 `innodb_buffer_pool_chunk_size`，这两个参数不适用。

重启：

```bash
sudo systemctl restart mariadb
sudo systemctl status mariadb --no-pager
```

如果启动失败：

```bash
sudo journalctl -u mariadb -n 100 --no-pager
```

验证：

```bash
sudo mariadb -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size';"
sudo mariadb -e "SHOW VARIABLES LIKE 'max_connections';"
sudo mariadb -e "SHOW VARIABLES LIKE 'bind_address';"
```

### 4.4 初始化 `smart_home` 数据库

先确认是否已存在，避免误删：

```bash
sudo mariadb -e "SHOW DATABASES LIKE 'smart_home';"
```

首次部署可以导入：

```bash
cd /www/wwwroot/smart-home
sudo mariadb < database/init.sql
```

注意：`database/init.sql` 开头会 `DROP DATABASE IF EXISTS smart_home`，**只适合首次初始化**。如果已有数据，先备份，不要直接执行。

验证：

```bash
sudo mariadb smart_home -e "SHOW TABLES;"
sudo mariadb smart_home -e "SELECT COUNT(*) AS users FROM users;"
```

### 4.5 创建应用专用账号

不要用 root 跑应用。创建 `homemind` 用户：

```bash
sudo mariadb <<'SQL'
CREATE USER IF NOT EXISTS 'homemind'@'127.0.0.1' IDENTIFIED BY 'REPLACE_WITH_STRONG_PASSWORD';
CREATE USER IF NOT EXISTS 'homemind'@'localhost' IDENTIFIED BY 'REPLACE_WITH_STRONG_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
ON smart_home.* TO 'homemind'@'127.0.0.1';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
ON smart_home.* TO 'homemind'@'localhost';

FLUSH PRIVILEGES;
SQL
```

验证：

```bash
mariadb -h 127.0.0.1 -u homemind -p smart_home -e "SELECT 1;"
```

### 4.6 MariaDB 兼容性说明

项目代码使用 `mysql+aiomysql`，MariaDB 走 MySQL 协议，可以连接。

已检查 `database/init.sql`：

- 没有 `utf8mb4_0900_*`、`JSON_TABLE`、`WITH RECURSIVE` 等 MySQL 8 专属语法；
- `JSON` 在 MariaDB 10.5 中是 `LONGTEXT + JSON_VALID` 别名，可以建表；
- `ENUM`、`CURRENT_TIMESTAMP ON UPDATE`、`CONSTRAINT`、`UNIQUE KEY` 均支持。

如果导入时报错，先保留完整错误信息，重点检查：

1. 是否用了 root 之外的账号执行 `DROP DATABASE`；
2. `JSON` 列是否被数据库版本当作未知类型；
3. `utf8mb4_unicode_ci` 是否存在；
4. MariaDB 的 `sql_mode` 是否过严。

学习环境可以继续用 MariaDB 10.5；正式环境建议：

- MariaDB 10.11 LTS，或
- 阿里云 RDS MySQL 8.0。

---

## 五、Step 4：配置 `.env` 并手工启动

```bash
cd /www/wwwroot/smart-home/backend
sudo -u www cp .env.example .env
sudo -u www chmod 600 .env
```

编辑 `.env`：

```dotenv
APP_ENV=production

MYSQL_URL=mysql+aiomysql://homemind:REPLACE_WITH_STRONG_PASSWORD@127.0.0.1:3306/smart_home

# 1GB 不跑 Postgres
LANGGRAPH_PERSISTENCE_ENABLED=false
LANGGRAPH_POOL_MAX_SIZE=2
POSTGRES_URL=postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph

CORS_ORIGINS=https://your-domain.com
TRUST_PROXY_HEADERS=true

JWT_SECRET=用-openssl-rand-hex-32-生成
JWT_EXPIRE_HOURS=24

LLM_PROVIDER=qwen
QWEN_API_KEY=你的-key
QWEN_MODEL=qwen-plus

DASHSCOPE_API_KEY=你的-key

AGENT_CONTEXT_TOKEN_BUDGET=1200
AGENT_MAX_PLAN_TASKS=3
AGENT_MAX_REFLECTIONS=1
AGENT_MAX_CLARIFICATIONS=2

ENABLE_SCHEDULER=false
LANGSMITH_TRACING=false
```

生成 JWT：

```bash
openssl rand -hex 32
```

如果 MariaDB 密码包含 `@ : / # ?`，写进 `MYSQL_URL` 前要做 URL 编码。

手工启动：

```bash
cd /www/wwwroot/smart-home/backend
sudo -u www -H .venv/bin/uvicorn homemind.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips=127.0.0.1
```

另开终端：

```bash
curl http://127.0.0.1:8000/
```

预期：

```json
{
  "service": "smart-home-backend",
  "status": "running",
  "docs": "/docs",
  "llm_provider": "qwen",
  "persistence": {"backend": "memory", "store": null, "error": null}
}
```

`persistence.backend=memory` 是 1GB 版本预期。

如果失败：

```bash
.venv/bin/python -c "import fastapi, sqlalchemy, aiomysql, langgraph; print('ok')"
mariadb -h 127.0.0.1 -u homemind -p smart_home -e "SELECT 1;"
ss -lntp | grep 8000
```

---

## 六、Step 5：systemd 守护

```bash
sudo cp /www/wwwroot/smart-home/deploy/systemd/smart-home-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smart-home-api
sudo systemctl status smart-home-api --no-pager
sudo journalctl -u smart-home-api -f
```

验证：

```bash
curl -fsS http://127.0.0.1:8000/
```

如果服务启动失败，先看 journal；80% 是 `.env`、路径、权限或 Python 依赖问题。

### 内存观察

```bash
free -h
ps aux --sort=-%mem | head -n 10
```

如果 MariaDB 和 FastAPI 加起来把可用内存压到 100MB 以下，先降 MariaDB `innodb_buffer_pool_size` 到 128M，再观察。

---

## 七、Step 6：前端构建与上传

1GB 服务器不建议跑 `npm run build`，在本地构建：

```bash
cd frontend
npm ci
npm run build
```

上传 `dist`：

```bash
scp -r frontend/dist/* root@<服务器IP>:/www/wwwroot/smart-home/frontend/dist/
```

服务器权限：

```bash
sudo chown -R www:www /www/wwwroot/smart-home/frontend/dist
```

如果服务器上必须构建：

```bash
cd /www/wwwroot/smart-home/frontend
npm ci
NODE_OPTIONS=--max-old-space-size=512 npm run build
```

失败就回本地构建。

---

## 八、Step 7：安装/配置 Nginx 与站点

### 8.1 安装 Nginx

你的机器 `nginx.service` 不存在，先确认是不是宝塔 Nginx 没装：

```bash
ls -l /www/server/nginx/sbin/nginx 2>/dev/null
```

如果不存在：

- 宝塔「软件商店」→ 安装 Nginx 稳定版；
- 或在面板「网站」里按提示安装；
- 如果不用宝塔：`sudo dnf install -y nginx`。

安装后：

```bash
sudo systemctl enable --now nginx
sudo systemctl status nginx --no-pager
sudo nginx -t
```

### 8.2 宝塔建站

「网站」→「添加站点」：

- 域名：`your-domain.com`
- 根目录：`/www/wwwroot/smart-home/frontend/dist`
- PHP：纯静态
- 数据库：不创建

### 8.3 配置反向代理

站点「设置」→「配置文件」，合并 `deploy/nginx/smart-home.conf` 的内容。

关键配置：

```nginx
client_max_body_size 30m;

location = /api/health {
    proxy_pass http://127.0.0.1:8000/;
    ...
}

location = /api/agent/v2/ws {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    ...
}

location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;
    proxy_read_timeout 300s;
    ...
}

location / {
    try_files $uri $uri/ /index.html;
}
```

检查：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 8.4 HTTPS

宝塔站点「SSL」→ Let's Encrypt → 申请 → 强制 HTTPS。

前提：

- 域名已解析到公网 IP；
- 安全组放行 80/443；
- 国内服务器域名已完成 ICP 备案。

没有域名先用 `http://服务器IP` 学习，Let's Encrypt 不能签纯 IP。

---

## 九、Step 8：安全与备份

### 9.1 安全组

只放行：

- 22：你的公网 IP；
- 80/443：0.0.0.0/0；
- 宝塔面板端口：你的公网 IP。

不要放行 8000、3306、5432。

### 9.2 系统防火墙

```bash
sudo systemctl status firewalld --no-pager || true
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

如果使用 `ufw`，改用 `ufw allow 80/tcp`、`ufw allow 443/tcp`。

### 9.3 MariaDB 只监听本机

确认配置：

```ini
bind-address = 127.0.0.1
```

验证：

```bash
sudo ss -lntp | grep 3306
```

应该只看到 `127.0.0.1:3306`，不能是 `0.0.0.0:3306`。

### 9.4 文件权限

```bash
sudo chown www:www /www/wwwroot/smart-home/backend/.env
sudo chmod 600 /www/wwwroot/smart-home/backend/.env
sudo chmod 700 /www/wwwroot/smart-home/backend/.venv
```

### 9.5 备份

仓库提供：

```bash
deploy/scripts/backup_mysql.sh
```

手工测试：

```bash
export MYSQL_USER=homemind
export MYSQL_PASSWORD='你的密码'
bash /www/wwwroot/smart-home/deploy/scripts/backup_mysql.sh
```

之后放到宝塔「计划任务」，每天 03:00 执行，并把备份同步到阿里云 OSS。

---

## 十、Step 9：验收

```bash
# 服务
sudo systemctl status smart-home-api --no-pager
sudo systemctl status nginx --no-pager
sudo systemctl status mariadb --no-pager

# 后端健康
curl -fsS http://127.0.0.1:8000/
curl -fsS https://your-domain.com/api/health

# 前端
curl -I https://your-domain.com/

# 登录
curl -X POST https://your-domain.com/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"owner01","password":"123456"}'

# 资源
free -h
ps aux --sort=-%mem | head -n 10
df -h

# 日志
sudo journalctl -u smart-home-api --since "10 min ago" --no-pager
sudo journalctl -u mariadb --since "10 min ago" --no-pager
```

浏览器验收：

1. 登录成功；
2. 设备列表加载；
3. 修改设备状态；
4. 执行场景；
5. AI 聊天有回复；
6. 高风险操作出现审批；
7. 审批通过/拒绝都能继续；
8. 前端路由刷新不 404；
9. WebSocket 不报 400/404；
10. 上传文件后能问答（如果配置了 `DASHSCOPE_API_KEY`）。

---

## 十一、这台机器的关键风险

1. **MariaDB 10.5 已停止维护**：学习可以，生产应升级 MariaDB 10.11 LTS 或 RDS MySQL 8。
2. **896Mi 内存很紧**：MySQL + FastAPI + Nginx + 宝塔面板已接近上限；不要装 Postgres、Chroma、Whisper。
3. **关闭 Postgres 持久化**：审批/澄清中断态在服务重启后丢失；正式环境要接 RDS PostgreSQL。
4. **单 worker**：没有并发冗余，重启有秒级中断；企业级需要多实例 + 负载均衡。
5. **Nginx 未安装**：先装 Nginx，否则只能裸端口访问，不适合上线。
6. **没有域名/备案**：只能先用 IP 学习；HTTPS 需要域名。
7. **1GB 不是生产规格**：建议升级到 2 核 4GB，数据库换 RDS，再谈企业级。

---

## 十二、下一步执行顺序

按下面顺序做，不要跳步：

1. `sudo -v` 确认权限；
2. 宝塔软件商店安装/启动 Nginx；
3. 上传代码到 `/www/wwwroot/smart-home`；
4. 安装 Python 3.11 并创建 `backend/.venv`；
5. 复制 MariaDB 低内存配置并重启；
6. 导入 `database/init.sql`，创建 `homemind` 用户；
7. 配置 `.env`，手工启动后端并 `curl` 通；
8. 配 systemd；
9. 本地构建前端并上传 `dist`；
10. 宝塔建站、粘贴 Nginx 配置、申请 SSL；
11. 安全组/防火墙收口；
12. 按验收清单逐项验证。

---

## 十三、参考来源

- 宝塔面板部署 Python 项目（详细教程）：https://www.cnblogs.com/lujugeo/articles/20519838
- 宝塔面板部署 FastAPI：Gunicorn + Nginx 反代：https://m.php.cn/faq/2409839.html
- 1 核 1GB 云服务器部署建议（Swap/CDN）：https://smartmll.com/archives/64757.html
- 宝塔 MySQL 8.0 内存过高：Buffer Pool 与 Binlog 优化：https://m.php.cn/faq/2380829.html
- 宝塔 MySQL 内存不足频繁重启：Swap 与并发限制：https://m.php.cn/faq/2353041.html
- Gunicorn + systemd + Nginx 部署 FastAPI：https://bbs.huaweicloud.com/blogs/519295
- FastAPI 生产部署：systemd + Nginx：https://blog.csdn.net/jjiejingtazhu/article/details/163148990
