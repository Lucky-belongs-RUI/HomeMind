# ZHJJ 项目面试问题详解（89 问全答案）

> 覆盖板块：A 项目概览与架构 / B 数据库设计 / C 后端与认证 / D Agent 核心 / E RAG 知识库 / F 实时推送与模拟器 / G 前端 / H 部署与深度追问
> 每题答案结构：**结论 → 关键细节（含代码位置）→ 面试追问应对**。

---

## A. 项目概览与架构（10 问）

### A1. 介绍这个项目是做什么的？核心功能有哪些？

**答案**：这是一个**智能家居大模型体验平台**（目录名 ZHJJ），核心是"用自然语言控制真实的家电设备状态"。用户打开网页，对 AI 助理说"把客厅空调调到 26 度"或"我感冒了"，AI 会理解意图、规划任务、必要时请求用户审批确认，然后修改数据库中的设备状态，并通过 WebSocket 实时把新状态推送到前端卡片上。

**核心功能（8 项）**：
1. **设备与房间管理**：房间、设备全生命周期增删改查，设备状态以 JSON 存储，前端卡片化展示与手动控制。
2. **AI 自然语言控制**：LangGraph + 规则引擎双通道理解意图，工具调用改设备状态（核心卖点）。
3. **场景联动**：一键执行"回家模式""睡眠模式"等批量操作，AI 也可自然语言触发场景。
4. **多家庭多角色**：房主/住户/访客三级权限，家庭数据隔离，模拟多个家庭体验。
5. **RAG 私有知识库**：上传 PDF/Word，向量化后 AI 可基于个人偏好与家庭规章制度回答。
6. **语音交互**：语音转文字（STT，缺失时演示降级）+ 文字转语音（edge-tts）。
7. **虚拟形象**：卡通形象根据回复情感切换 idle/speaking/thinking/happy/sad 表情。
8. **设备模拟引擎**：APScheduler 定时模拟扫地机器人电量下降、位置移动，让平台有"活态"演示效果。

**技术定位**：演示/教学型全栈项目，前后端分离、数据库为唯一状态源，强调"即使 LLM 不可用，规则引擎也能兜底跑通全流程"。

### A2. 技术栈？为什么选 FastAPI + Vue3 + MySQL？

**答案**：后端 **FastAPI（Python 3.11）+ SQLAlchemy 2.0 异步 + LangGraph + APScheduler**；前端 **Vue 3（组合式 API）+ Pinia + Element Plus + TailwindCSS + Vite**；数据库 **MySQL 8.0**；LLM 适配 **OpenAI 兼容接口（Qwen/DeepSeek/Zhipu/Ollama）**。

选型理由：
- **FastAPI**：原生 async/await 异步高性能，天然适配 WebSocket 长连接与流式输出；Pydantic 自动校验请求参数并生成 Swagger 文档（/docs 可调试）。
- **Vue 3**：组合式 API 让状态逻辑（审批、流式）可复用；Pinia 轻量状态管理；生态成熟（Element Plus 组件）。
- **MySQL + JSON 字段**：MySQL 稳定、事务可靠；设备状态用 JSON 列存储，20+ 种设备类型的状态结构各不相同（空调有温度/模式、扫地机有电量/位置），JSON 免去频繁加列。
- **LangGraph**：把 Agent 做成显式状态图，支持中断（interrupt/resume）、并发扇出、逐节点事件，比手写 while 循环编排能力强。

### A3. 用户说"把客厅空调调到 26 度"，从输入到设备更新的完整链路？

**答案**（核心串讲题，按代码实际路径）：
1. **前端发送**：AgentView.vue 捕获输入 → 优先走 WebSocket 发送 `{type:'chat', message, session_id, permission_mode, provider, model}`；若 WS 未连接，回退 HTTP `POST /api/agent/chat`。
2. **接口层**：`api/agent.py` 的 agent_chat → 校验 JWT（get_current_user）→ 保存用户消息到 conversations 表 → 构造初始 state。
3. **意图识别**：`nodes/intent_recognition.py` 用规则引擎（`rules/intent.py`）命中 `air_conditioner` + 房间"客厅" + `temperature=26`，输出 `device_control` 意图；链路判定为 `control`。
4. **任务规划**：`nodes/task_planning.py` 把意图转成任务 `{tool_name:"set_device_state", arguments:{room_name:"客厅", device_type:"air_conditioner", attributes:{temperature:26, power:"on"}}, needs_approval:True}`。
5. **审批**：普通模式下 `nodes/approval.py` 通过 LangGraph `interrupt()` 中断，前端弹审批面板，用户勾选确认后 resume。
6. **工具执行**：`nodes/tool_execution.py` → `tools/device_tools.py` 的 `set_device_state` → `services/device_service.py::update_device_status` 更新 MySQL devices 表的 status JSON。
7. **广播**：写入后调用 `websocket/manager.py::broadcast_device_update` 推送 `device_status_update` 到所有客户端。
8. **前端更新**：`useWebSocket.js` dispatch 按 family_id 过滤 → `deviceStore.updateDeviceFromWS` 更新卡片状态。
9. **回复**：result_aggregation 汇总 → response_generation 生成"已为您将客厅空调调至 26 度" → 返回/流式推送。

**一句话总结**：前端 → Agent 状态图（意图→规划→审批→执行）→ 数据库（权威源）→ WebSocket 广播 → 前端卡片。

### A4. 前后端有哪两种通信方式？各自适用场景？

**答案**：
- **REST（HTTP）**：登录、设备/房间/场景/文件/用户的增删改查、一次性的 Agent 请求兜底。特点：无状态、简单、可缓存。
- **WebSocket（长连接）**：`/api/agent/ws`，用于三类实时场景——① Agent 流式输出（agent_step 节点进度 / agent_token 逐字回复 / agent_done 结束）；② 设备状态变化实时推送（device_status_update）；③ 中断交互（agent_interrupt 审批/澄清）。特点：全双工、低延迟。

**设计要点**：不是二选一，而是**双通道并存**——聊天优先走 WS（体验好），WS 未连接时自动降级 HTTP 轮询式请求（sendAgentMessage 返回 false 就发 HTTP），保证功能可用。

### A5. 多家庭多角色（房主/住户/访客）设计目的？数据如何隔离？

**答案**：目的是模拟真实"一个平台服务多个家庭"的体验，并演示**权限矩阵**（开发文档 5.13）：
- **房主 owner**：全部权限——管理房间/设备/场景/用户、上传家庭规章制度、控制设备。
- **住户 resident**：可控制设备、上传个人文档，但不能做管理操作。
- **访客 guest**：只读——能看家庭/设备/场景，不能控制与上传。

**隔离实现（两层）**：
- **数据层**：所有业务表（users/rooms/devices/scenes/conversations/uploaded_files）都带 `family_id`，查询全部按家庭过滤。
- **接口层**：`api/family.py` 的 `_ensure_family_access(family_id, current_user)` 强制校验 `family_id == current_user["family_id"]`，不一致返回 403；`api/deps.py` 提供 `require_owner` / `require_owner_or_resident` 做角色校验。
- **前端层**：`composables/usePermission.js` 用 `userStore.isOwner/isGuest` 计算 `canManageDevices/canControlDevice` 等，控制按钮显隐——但**这只是体验层，真正安全在后端强制校验**。

**追问应对**：可说"前端权限只是 UI 隐藏，后端 Depends 校验才是安全边界；这也是面试常考的'前端权限不可信'实践"。

### A6. 项目中哪些是真实实现、哪些是模拟？

**答案**：
**真实实现**：设备/房间 CRUD、JWT 认证、Agent 意图识别与工具调用、场景联动、RAG（向量检索真实可用）、对话历史持久化、WebSocket 推送、edge-tts 语音合成、时间/天气查询（真实数据源）、用户画像自由 JSON 分析（真实 LLM）。
**模拟/降级设计（v2 收紧后）**：
1. **设备模拟器**：仅剩 `scheduler/simulators/vacuum_simulator.py`——APScheduler 定时模拟扫地机"电量下降/位置移动"（真实代码，模拟的是随时间演化的设备行为）。**空调模拟器已删除**。
2. **LLM 兜底**：模型不可用/无 Key 时回退**规则引擎**（意图识别/任务规划/回复生成都有规则实现）；**MockClient 已删除**——不存在任何假回复、假工具数据。
3. **语音识别 STT**：Whisper 真实转写；模型缺失/加载失败时**直接报错**（不再返回 mock 演示文本）。
4. **密码明文**：README 声明演示模式明文存储，不做哈希与安全校验（有意的演示降级，生产须换 bcrypt）。
5. **向量库**：ChromaDB 或本地 JSON 均为真实向量检索（无假向量）；**嵌入强制阿里云 text-embedding-v2（1536 维）**，无 Key/失败直接报错不降级（v2.1）。

**追问应对**：强调"**项目坚持真实流程**——用户明确要求删除所有 mock 与演示输出，当前链路（含 qwen 无 Key 降级的规则路径）全部走真实设备数据；降级只体现在'算法路径'（规则 vs LLM），不体现在'数据'（都是数据库真实值）"。

### A7. 为什么把 Agent 做成状态图？相比 if-else 流程的优势？

**答案**：项目用 **LangGraph StateGraph（唯一执行引擎）**，相比手写 if-else 的优势：
1. **显式可编排**：节点（intent/plan/approval/tools/response…）和条件边（路由函数）一目了然，新增节点只需加节点函数 + 路由。
2. **可中断/可恢复**：LangGraph `interrupt()` 把"审批""澄清"这类需要用户参与的环节挂起，`Command(resume=data)` 恢复——if-else 很难干净地实现跨请求状态保持。
3. **并发扇出**：多链路（chat/control/knowledge/report）可同时执行，路由函数返回列表即可并发，结果用 reducer 合并（`operator.or_`）。
4. **可观测**：每个节点执行前后都能发出 agent_step 事件，前端实时展示"正在做什么"。
5. **状态集中**：所有数据在 state 字典里流动（messages/intents/tasks/rag_context…），好调试、好测试。

**追问应对**：可补充"v2 起 LangGraph 是**唯一执行引擎**（轻量执行器双实现已删除），节点/路由/中断/恢复全部收敛到 LangGraph 语义，避免两套执行器行为分叉"。

### A8. 执行器架构：为什么完全采用 LangGraph？（原双执行器已删除）

**答案（v2 架构）**：`agent/graph.py` 当前**只有一套执行器——LangGraph StateGraph**：
- `build_agent_graph()`：注册 13 个节点 + 条件边/并发边，`compile(checkpointer=MemorySaver())` 编译为 `agent_app` 单例（HTTP 与 WS 共用）。
- 中断：节点里 `wait_user` → `langgraph.types.interrupt` 原生抛出，state 由 MemorySaver 按 `thread_id` 落盘；
- 恢复：`Command(resume=resume_data)` 从断点继续，`interrupt()` 的返回值即用户回答/审批结果；
- 并发：条件路由函数返回**节点名列表**，LangGraph 并发扇出多链路。

**为什么删掉轻量执行器**（用户明确要求"完全实现 LangGraph，删除相关代码和参数"）：
1. 双实现让同一套节点函数跑在两套编排上，中断/恢复/并发语义各写一遍，行为极易分叉（如轻量执行器的 `_resume_store` 快照重放只是"近似恢复"，不是真断点）；
2. 维护成本翻倍：改一次澄清逻辑要同步改两处；
3. LangGraph 已是成熟依赖，不再做"可选依赖降级"的妥协。

**追问应对**：这是"**收敛架构复杂度**"的工程决策——用框架原语（interrupt/Command/MemorySaver/reducer）替代自研近似实现，换来单一事实来源。

### A9. 目录结构如何分层？各层职责？

**答案**（后端 `backend/homemind/`）：
| 层 | 目录 | 职责 |
|---|---|---|
| 接口层 | `api/` | FastAPI 路由：auth/device/room/scene/family/file/agent |
| 校验层 | `schemas/` | Pydantic 请求/响应模型（AgentChatRequest、DeviceStatusUpdate…） |
| 业务层 | `services/` | 业务逻辑：device_service、scene_service、family_service、file_service… |
| 数据层 | `models/` | SQLAlchemy ORM：User、Device、Room、Scene、Conversation… |
| Agent 层 | `agent/` | state.py 状态 / graph.py 编排 / nodes/ 节点 / rules/ 规则引擎 / tools/ 工具 |
| 知识库 | `rag/` | vector_store（向量存储）、retriever、chunker、embedder |
| 模型适配 | `llm/` | factory 多模型工厂（deepseek/qwen/zhipu/ollama）、message 构造、embed_utils 向量化 |
| 调度 | `scheduler/` | APScheduler 引擎 + simulators/ 设备模拟器 |
| 推送 | `websocket/` | manager.py 连接管理 + 广播 |

前端 `frontend/src/`：views（页面）/ components（组件）/ stores（Pinia）/ api（接口封装）/ composables（组合函数）/ router。

**追问应对**：强调"**依赖方向自上而下**：api 调 service，service 用 model，Agent 是独立模块通过 service 与工具操作数据"。

### A10. 你在项目里承担什么角色？最有挑战的部分？

**答案**（自述模板，建议按实际调整）：
"我在项目中负责 **Agent 核心模块的架构与实现**。最有挑战的是两部分：
1. **Agent 状态图 + 中断/恢复**：要让'审批''澄清'这类用户交互真正打断并恢复执行，且 HTTP 和 WebSocket 两条通道都能恢复。方案是 LangGraph interrupt + Command(resume) + MemorySaver 按 thread_id 恢复，并完成'删除轻量执行器双实现'的架构收敛。
2. **澄清机制的迭代**：从'固定问句问哪个房间'演进到**两级澄清**（模糊需求先做设备方案确认，确认操作后才问房间）+ **多选解析**（回答按顿号切分逐段生成多任务）+ 取消退回闲聊，选项基于家庭真实设备动态生成。

我也做过**全链路逻辑审查与真实化改造**：删除所有 mock/死代码（MockClient、空调模拟器、演示输出），新增时间/天气真实查询工具、用户画像自由 JSON 分析、文件双级可见性与孤儿向量对账清理等，保证每条链路都走真实数据。"

---

## B. 数据库设计（12 问）

### B1. 数据库有哪些表？主外键关系？

**答案**（init.sql 共 10 张表）：
| 表 | 关键字段 | 关系 |
|---|---|---|
| users | family_id | 属于某家庭（FK→families.id） |
| families | owner_user_id | 房主指向 users.id（uk_owner 唯一） |
| rooms | family_id | 属于家庭 |
| devices | family_id, room_id, status(JSON) | 挂在房间下 |
| scenes | family_id, actions(JSON) | 属于家庭 |
| conversations | session_id, user_id, role(user/assistant/tool), content | 属于用户，FK→users ON DELETE CASCADE |
| session_contexts | family_id, user_id, session_id, compressed_parts | 会话压缩状态 |
| device_operation_logs | family_id, device_id, source, before/after_status(JSON) | 操作审计 |
| uploaded_files | family_id, user_id, file_type, content_hash, status | 属于用户 |
| user_preferences | user_id, preferences(JSON) | 属于用户，FK→users CASCADE |
| user_model_configs | user_id, name, provider, model, base_url, api_key_encrypted | 用户个人模型配置，API Key 加密存储 |

**双向引用**：users.family_id → families.id；families.owner_user_id → users.id（房主注册时序：先建 user(family_id=0) → 建 family → 回填）。

### B2. 设备状态为什么用 JSON 字段？优缺点？

**答案**：
- **优点**：20+ 设备类型状态结构差异极大（空调 temperature/mode/fan_speed，扫地机 battery/position/status，门锁 locked/auto_lock…），JSON 一列全搞定，新增字段不用改表；读写都方便（ORM 直接存取 dict）。
- **缺点**：无法用 SQL 对内部字段做索引/范围查询（如"查所有温度>26 的空调"要全表扫）；无数据库级 schema 校验，类型错误只能靠代码兜底；字段名靠约定（如扫地机状态必须是 `cleaning` 而非 `running`——这正是 P1 修复的教训）。

**追问应对**：可答改进方案——"设备量大后把高频查询字段抽成独立列并加索引，或引入 Pydantic 每类型状态模型做写入校验"。

### B3. 软删除（is_active）为什么设计？哪些表用？

**答案**：families / rooms / devices / scenes 四张表都有 `is_active TINYINT(1) DEFAULT 1`，删除操作改为 `is_active=0`。
**目的**：① 保留历史数据用于对话追溯（如"昨天那台空调"）；② 删除可恢复；③ 与审计日志对得上。
**例外**：conversations/uploaded_files 是真删除（个人数据），删除家庭时业务数据硬删、family 记录软删。

### B4. 为什么所有表以 family_id 为第一索引？

**答案**：因为**家庭是最常查询的隔离边界**——设备列表、房间列表、场景、对话、文件全部按 family_id 过滤，`INDEX idx_family_active (family_id, is_active)` 这类复合索引保证"按家庭+启用状态"的查询走索引。这是多租户类系统的通用实践：**租户维度放索引第一位**。

### B5. 场景动作为什么用 room_name+device_type 定位设备而非 device_id？局限？

**答案**：场景 actions 结构是 `{"device_type":"light","room_name":"客厅","attributes":{...}}`，执行时 `get_device_by_room_and_type(room_id, device_type, family_id)` 定位——**不存 device_id**。
**原因**：演示数据的定位语义是"在哪个房间的哪种设备"，对用户更友好（说"客厅的灯"而不是"设备 #5"）；文档的 actions 示例即此结构。
**局限**：**同一房间同类型多台设备时无法精确定位**（会命中第一台）；设备被删除/换房间后动作语义变化。改进方向是支持 device_id 或"第几台"。

### B6. 演示数据有哪些设备类型？状态结构为何各不相同？

**答案**：两个家庭约 40 台设备、20+ 类型：air_conditioner、light、tv、robot_vacuum、curtain、speaker、water_heater、fridge、washer、door_lock、camera、air_purifier、humidifier、air_monitor、temp_humidity_sensor、outdoor_sensor、weather_station、electricity_meter、smart_plug、water_meter、gas_meter、door_window_sensor、presence_sensor、leak_sensor、gas_sensor、smoke_sensor、router。
**状态各异**：空调 `{power, temperature, mode, fan_speed, swing}`；扫地机 `{power, battery, position{x,y}, cleaning_mode, status, dust_bin}`；门锁 `{power, locked, battery, auto_lock}`；表计 `{online, power_w, daily_energy_kwh, balance}`——这就是 JSON 存储的用武之地，前端每种类型一张卡片组件读取自己关心的字段。

### B7. users.family_id 与 families.owner_user_id 互相引用的设计？

**答案**：这是"**房主注册家庭**"的时序造成的双向引用：
1. 创建房主用户 `family_id=0`（占位）；
2. 创建家庭 `owner_user_id=user.id`；
3. 回填 `user.family_id = family.id`。
查询时：用户 → 自己的家庭用 family_id；家庭 → 房主信息用 owner_user_id。**uk_owner 唯一索引**保证一个用户只能是一个家庭的房主。

### B8. device_operation_logs 表？source 字段？

**答案**：设备操作审计表，字段：family_id、device_id、user_id、operation、**source（manual 手动 / agent AI / scheduler 调度）**、before_status、after_status（JSON）、description、created_at。
每次 `update_device_status` 都会写一条日志，记录变更前后状态——支持**审计、回滚、排障**（如"这台空调是谁在几点改的"）。这是"数据库为状态唯一来源"原则的支撑。

### B9. 删除家庭时先删业务数据再删用户的顺序？

**答案**：`family_service.delete_family` 顺序：
1. 删 conversations（会话）、uploaded_files（文件）、device_operation_logs（日志）——这些表 FK→users；
2. 删该家庭全部用户；
3. 家庭软删除（is_active=0）。
原因：conversations/uploaded_files 的外键是 `ON DELETE CASCADE`，但显式删除顺序更可控、可加日志；user_preferences 靠 CASCADE 兜底。删完后 families.owner_user_id 悬空（指向已删用户）——低风险已知项（P11）。

### B10. 如何保证"一个用户只能是一个家庭的房主"？

**答案**：families 表 `owner_user_id BIGINT NOT NULL, UNIQUE KEY uk_owner (owner_user_id)`——数据库唯一约束兜底，无论应用层逻辑怎么漏，都不会出现一个用户当两个家庭的房主。（注意：一个房主可以注册多个家庭，因为每个家庭用独立的 owner 账号。）

### B11. 新增"色温"字段要改哪些地方？

**答案**（扩展性考察，以灯光为例）：
1. `database/init.sql` 演示数据里 light 的 status JSON 加 `"color_temperature": 4000`；
2. `services/device_service.py::_default_status` 给 light 默认值加该字段；
3. `agent/rules/intent.py::_parse_attributes` 加"色温 4500"→ `attrs["color_temperature"]` 的解析分支；
4. 前端灯光卡片组件加滑块控件，`SmartDeviceCard.vue` 对应类型模板；
5. （可选）`scene` 面板的动作参数里加色温选项。
**答案要点**：改动集中在"演示数据 + 默认值 + 规则解析 + 前端卡片"四处，得益于 JSON 存储，**不需要改表结构**。

### B12. 万级设备下当前设计瓶颈？

**答案**：
1. **JSON 状态无法索引**：按状态字段过滤/排序只能全表扫。
2. **WebSocket 全量广播**：每次变更推给所有连接，O(连接数)，连接多时浪费。
3. **单表无分区**：device_operation_logs 会无限增长。
4. **无缓存**：设备列表每次查库。
**优化方向**：高频字段列化+索引；WS 按 family/房间订阅（后端过滤）；日志表按时间分区或归档；引入 Redis 缓存热点查询；消息队列削峰（广播异步化）。

---


---

## C. 后端与认证（10 问）

### C1. JWT 认证流程？token 载荷？过期怎么办？

**答案**：
- **登录**：`/api/auth/login` 校验用户名+密码 → `auth_service.create_jwt_token` 生成 JWT，payload 含 `user_id / username / role / family_id / exp`（默认 24 小时），前端存 localStorage。
- **请求认证**：前端请求头 `Authorization: Bearer <token>`；`api/deps.py::get_current_user` 用 Depends 注入，解析并校验签名与过期，返回用户 dict `{user_id, username, role, family_id}`。
- **过期处理**：`jwt.ExpiredSignatureError` → 抛 401，前端请求拦截器收到 401 清 token 跳登录页。
- **WebSocket 鉴权**：连接 URL 带 `token` 查询参数，ws 端点建立时解析一次，无效直接关闭。

**追问应对**：可补充——JWT 无状态（服务端不存会话），但**无法主动踢人**，演示项目可接受；生产可引入 refresh token 或短期 token。

### C2. 密码为什么明文存储？生产怎么办？

**答案**：README 明确声明：**演示模式密码明文保存，不做哈希与安全校验，仅用于本地体验**。开发文档 4.4.2 的示例实现是 bcrypt（`bcrypt.hashpw/checkpw`），但为了演示方便实际代码降级为明文。
**生产做法**：bcrypt/argon2 加盐哈希存储，校验用 `checkpw`；登录接口加限流防爆破；JWT 密钥用环境变量注入不硬编码。

**追问应对**：诚实承认这是"已知的演示取舍"，并主动给出生产方案——比掩饰更有说服力。

### C3. FastAPI 依赖注入？get_current_user 做了什么？

**答案**：FastAPI 的 `Depends()` 允许把"取用户"这类公共逻辑抽成依赖函数，路由声明 `current_user: dict = Depends(get_current_user)` 即可自动获得。
`get_current_user` 流程：① 取请求头 Authorization → 解析 Bearer token；② `jwt.decode` 校验；③ 返回用户信息 dict。`require_owner` / `require_owner_or_resident` 在其基础上追加角色校验，不通过抛 403。
**好处**：认证逻辑单点维护，每个受保护路由一行声明，测试时可替换依赖。

### C4. 家庭数据隔离在哪层实现？

**答案**：**接口层强制 + 数据层过滤**双层：
- 每个 `/api/families/{family_id}/xxx` 路由第一行调 `_ensure_family_access(family_id, current_user)`：`family_id != current_user["family_id"]` 直接 403。
- service 层查询全部带 family_id 条件（如 `list_devices_by_family(family_id)`、`get_scene_by_name(name, family_id)`）。
- 设备状态更新接口同理校验 device.family_id 与当前用户一致（`device_service` 内校验）。
- **修复项 P8**：`GET /api/families` 原先返回所有家庭概览（多家庭体验），已改为只返回当前用户所属家庭。

### C5. 上传文件为什么用 asyncio.create_task 异步处理？风险？

**答案**：文件解析（PDF/docx 文本提取）和向量化耗时长，不能阻塞上传接口返回。`api/file.py` 上传后立即返回 `{status:"processing"}`，后台 `asyncio.create_task(file_service.process_file_async(record.id, collection))` 异步处理，前端轮询 `/files/{id}/status` 直到 ready/failed。
**风险与对策**：① create_task 的任务在请求结束后仍运行，**必须内部 try/except**（process_file_async 已捕获异常并置 failed 状态）；② 进程重启任务丢失——启动时 `rebuild_file_vectors()` 全量重建兜底（代价是启动慢，P17）；③ 无任务重试/死信机制，属简化实现。

### C6. 文件类型/大小校验？

**答案**：`api/file.py` 上传接口：
- 扩展名白名单：`.pdf / .docx`（修复项 P6 移除了无法解析的 `.doc`）；
- 空文件检查（content 为空拒绝）；
- 大小限制 `len(content) > settings.max_file_size`（10MB）；
- 集合参数校验：仅 `user_documents` / `family_regulations`，后者要求房主。
**要点**：校验在接口层完成，service 层不重复校验但解析失败会置 failed 状态。

### C7. 配置管理？pydantic-settings 如何工作？

**答案**：`homemind/config.py` 定义 `class Settings(BaseSettings)`，字段如 `mysql_url`、`llm_provider`、`jwt_secret`、`upload_dir`、`chroma_path`、`max_file_size`。pydantic-settings 启动时自动读取 **环境变量 > .env 文件**，`settings` 全局单例，任何模块 `from app.config import settings` 使用。
**示例**：`.env` 里 `LLM_PROVIDER=deepseek`、`MYSQL_URL=mysql+aiomysql://root:root@localhost:3306/smart_home`。容器部署用环境变量覆盖（docker-compose environment）。

### C8. CORS 怎么处理？为什么 WebSocket 不受 CORS 限制？

**答案**：后端 `main.py` 挂 `CORSMiddleware`，`allow_origins` 含前端地址（开发 http://localhost:5173），`allow_methods/headers` 放开，前端跨端口调 REST 接口。
**WebSocket 不受 CORS 限制**：CORS 是浏览器对 **HTTP 请求**（XHR/fetch）的同源策略检查；WebSocket 握手协议不走 CORS 预检，所以前端 `ws://localhost:8000` 直连后端可以成功——这也是前端默认直连 8000 端口能工作的原因（P18 知识点）。

### C9. 错误处理规范？

**答案**：后端统一抛 `HTTPException(status_code, detail)` → FastAPI 返回 `{"detail": "..."}` JSON；业务异常（用户名已存在、无权访问、场景不存在）在接口层 catch 后转 HTTPException。
前端 `api/request.js` 封装 axios 拦截器：响应拦截统一 `ElMessage.error(detail)` 提示，401 时清登录态跳转。**错误文案双层都有**，用户感知一致。

### C10. 权限矩阵前后端如何配合？

**答案**：
- **前端**（`composables/usePermission.js`）：由 `userStore.isOwner/isGuest` 计算 `canControlDevice`（非访客）、`canManageDevices/Rooms/Users/Scenes`（仅房主）、`canUploadFile`（非访客），控制按钮显隐——**UI 体验层**。
- **后端**（`api/deps.py`）：`require_owner`、`require_owner_or_resident` 作为 Depends 强制校验——**安全边界**。
- 前端不传或伪造角色也没用，后端从 JWT 取 role/family_id 校验。
**答案要点**：明确"前端权限只做体验，后端校验才是安全"是本题得分点。

---

## D. Agent 核心（20 问 · D1–D10）

### D1. 画出 Agent 状态图：节点与路由？

**答案**（LangGraph StateGraph，`agent/graph.py`）：
```
START → intent_recognition
  ├─ 需要全屋状态且未取 → house_status → 各链路入口
  ├─ 不明确意图（needs_clarification）→ clarification → 回 intent / plan
  └─ 明确 → 多链路并发：
       chat（闲聊）            → result_aggregation
       knowledge（知识查询）    → rag_retrieval → rag_answer → result_aggregation
       report（报告）          → report_generation（内部补 RAG）→ result_aggregation
       control（控制/查询/场景）→ task_planning
            ├─ 需澄清 → clarification → 回 task_planning
            ├─ 需审批且 normal 模式 → approval（interrupt）→ task_planning 重入
            └─ 否则 → tool_execution → result_aggregation
result_aggregation → response_generation → task_execution → END
```
**路由实现**：`route_after_intent` / `route_after_plan` / `route_after_clarify` / `route_after_house_status` 等条件边函数，返回节点名（或列表实现并发扇出）。

### D2. LangGraph interrupt 机制？中断询问 vs 中断审批差异？

**答案**：
- **机制**：节点内调 `interrupt(data)` 会抛出 `__interrupt__`，LangGraph 暂停执行并保存断点；恢复时用 `Command(resume=resume_data)` 继续。
- **中断询问（clarification）**：`type: "clarification"`，数据含 `question`（如"请问想调哪个房间的空调？"）+ `options`（选项列表）；前端弹问答面板，用户回答后 resume，答案合并进 `user_clarification` 重新规划。
- **中断审批（approval）**：`type: "approval"`，数据含 `tasks`（待执行任务列表：description/expected_effect/risk_level）+ `risk_level`；前端弹审批面板（默认全选），用户勾选后传 `{approved, task_ids}`；approved=false 或未选中的任务被跳过。
**差异本质**：询问是"补充信息"，审批是"授权执行"，恢复后的处理分支不同（回 planning 重新规划 vs 直接放行选中的任务）。

### D3. 中断恢复流程？HTTP 与 WS 场景？

**答案**：
- **HTTP**：前端 `POST /api/agent/resume {thread_id, resume_data, provider, model}` → 后端用 `thread_id` 定位 MemorySaver 中的断点 → `agent_app.ainvoke(Command(resume=resume_data), config)` 从断点继续执行 → 返回最终结果（v2 已删除 `_resume_store` 快照路径，统一走 LangGraph 断点恢复）。
- **WebSocket**：前端发 `{type:'resume', thread_id, resume_data, ...}` → 后端 ws 端点同样走 `_resume_agent`，流式推回 agent_token/agent_done。
- **保存时机**：执行到 interrupt 时，runner 把当前 state 存入 `_resume_store[thread_id]`（线程安全 dict），恢复后清理。
**答案要点**：**thread_id 是恢复句柄**，前端在收到 interrupt 时记住它（AgentView 里 `setPendingInterrupt({...interrupt, thread_id})`）。

### D4. 意图识别为什么"规则 + LLM"双通道？

**答案**（核心设计题）：
- **规则引擎**（`rules/intent.py`）：关键词 + 别名表 + 正则，如"把客厅空调调到 26 度"解析出 device_type/room/temperature。优点：**确定性、零成本、可单测、无网络依赖**。
- **LLM 通道**：处理规则覆盖不到的**隐式意图**（"我感冒了"→ 安慰+调温+通风判断+烧热水）、复杂表达、多意图。
- **配合方式**：先跑规则，命中且明确度足够就用规则结果（省一次 LLM 调用）；否则调 LLM（`_llm_recognize`），失败/格式非法回退规则；规则也无结果落 `chat` 链路兜底。
**答案要点**："**确定性优先，LLM 补泛化，规则兜底**"——兼顾成本、延迟与可用性，是生产级意图识别的常见架构。

### D5. 规则引擎如何解析"把客厅空调调到 26 度"？

**答案**（`rules/intent.py` 解析流水线）：
1. **设备识别** `find_device_type`：遍历 `DEVICE_TYPE_ALIASES`，"空调"→ `air_conditioner`；
2. **房间识别** `find_room`：从该家庭房间表匹配"客厅"；
3. **属性解析** `_parse_attributes`：正则 `(\d{1,2})\s*度` → `temperature=26`；含"调" → `power=on`；
4. **意图组装**：`build_rule_intents` 生成 `{type:"device_control", device_type, room_name, attributes, clarity}`；
5. **链路判定** `compute_active_chains`：device_control → `control` 链路。
**兜底**：房间缺失且家庭有多房间有该设备 → clarity 降低 → 触发澄清询问"哪个房间"。

### D6. 别名表（DEVICE_TYPE_ALIASES / ROOM_ALIASES）？如何扩展？

**答案**：`rules/common.py` 维护：
- `DEVICE_TYPE_ALIASES`：中文口语 → 内部类型，如"空调/冷气"→air_conditioner、"扫地机/扫把"→robot_vacuum、"净化器"→air_purifier；
- `ROOM_ALIASES`："主卧/次卧"→卧室、"厕所/浴室"→卫生间；
- `normalize_room_name` / `find_device_type` 统一走别名归一化。
**扩展方式**：新增设备类型时在别名表加一行即可被意图识别命中；前端场景面板 `deviceOptions` 也要加对应选项。

### D7. 任务规划节点做什么？多房间歧义处理？

**答案**（`nodes/task_planning.py`）：
- **职责**：把意图列表转成可执行任务列表，每项 `{tool_name, arguments, needs_approval, risk_level, description, expected_effect}`。如 device_control → `set_device_state`；scene_trigger → `trigger_scene`；device_query → `get_device_state`/`list_room_devices`；时间/天气 → `get_current_time`/`get_weather`。
- **多房间歧义（v2 修正）**：**高级模式与普通模式都会澄清**——只要设备类型在多个房间都有且用户没指定房间，就触发"请问您想调整哪个房间的空调？当前有：1.客厅、2.卧室"。**高级/普通模式的差别只在于任务执行时是否需要审批**（高级直接执行，普通走审批），不影响澄清。
- **空属性处理**：高级模式对缺属性的控制任务用 `_default_attributes` 补默认值（如 robot_vacuum 默认 `{power:on, status:"cleaning"}`）。
- **权限模式**：normal 下控制任务 `needs_approval=True`；high 下直接执行。

### D8. 审批机制？普通/高级模式差异？risk_level 判定？

**答案**（`nodes/approval.py`）：
- **permission_mode=normal**：`needs_approval` 的任务触发 interrupt 审批，用户勾选确认才执行；`approved_ids` 为空则全部跳过。
- **permission_mode=high**：跳过审批，任务全部放行（前端开关控制，默认 normal——P7 修复）。
- **risk_level 判定**（`rules/planning.py`）：door_lock 类默认 `high`；`control_count > 1` 或含需审批任务时整体升级 `medium`；其余 `low`。修复项 P10 指出：该覆盖逻辑会把查询类任务也误标 medium（低风险已知项）。
- 前端 `AgentInterruptPanel`：默认全选、取消传 `{approved:false}`、确认传 `{approved:true, task_ids}`。

### D9. 多链路并发执行？结果如何聚合？

**答案**：
- **链路划分**：`compute_active_chains` 返回 chat/control/knowledge/report 的组合（可多条同时命中，如"我感冒了"同时触发 control+chat）。
- **并发**：LangGraph 条件路由函数返回**节点名列表**实现并发扇出（v2 已删除轻量执行器的 `asyncio.gather` 模拟，统一走 LangGraph）。
- **结果合并**：每条链路把结果写进 `state["chain_results"][链路名]`，该字段声明为 `Annotated[Dict, operator.or_]` reducer——并发节点写不同 key 自动合并，不会互相覆盖。
- **聚合**：`result_aggregation_node` 汇总各链路结果（tool_results 的成功/失败/跳过数），`response_generation_node` 按链路优先级生成最终回复。

### D10. 澄清循环如何防死循环？两级澄清与多选怎么实现？

**答案**（v2 完整版）：
1. **计数上限**：`state["clarification_attempts"]` 每次 +1，超过 `MAX_CLARIFICATION_ATTEMPTS = 2` 直接生成 `final_response` 结束——意图澄清与规划澄清共享计数，**最多问 2 次**，对话必然收敛。
2. **两级澄清**（v2）：模糊需求（感冒/冷/睡觉/热/天黑/吵）**第一级问方案**（"需要我帮您调低空调温度、关上窗户、烧壶热水吗？"，选项=家庭真实设备方案，不直接问房间）；用户确认要操作某类设备后，**第二级才问房间**（"想调哪个房间的空调？1.客厅、2.卧室"）。
3. **防循环的第三道闸**：澄清回答无具体设备词（"都行/都可以"）时**直接执行默认方案**，不再追问。
4. **多选**（v2）：规则引擎对含顿号的回答做**多段解析**（"调低空调温度、关上窗户"→ 空调+窗帘两个意图），前端澄清面板支持选项多选。
5. **取消**：用户点"取消"= 意图理解错误，退回闲聊链路由模型自然回应，不中断整个流程。

---

---

## D. Agent 核心（20 问 · D11–D20）

### D11. state 有哪些关键字段？为什么 chain_results 用 reducer？

**答案**（`agent/state.py`）关键字段分四组：
- **会话组**：user_input、user_id、family_id、user_role、session_id、messages（对话历史）、provider、model、permission_mode。
- **意图组**：intents、intent_clarity_score、needs_clarification、clarification_question、user_clarification、clarification_attempts。
- **任务组**：tasks、needs_approval、approved_ids、tool_results、chain_results。
- **输出组**：rag_context、rag_sources、is_knowledge_query、final_response、avatar_emotion、_interrupt（中断数据）。
**为什么 chain_results 用 `operator.or_` reducer**：多链路并发时每个节点返回 `{"chain_results": {"chat": ...}}`，LangGraph 默认"后写覆盖"，并发节点会互相覆盖；reducer 让每次更新按 key 合并（dict 更新），各链路结果共存。这是 LangGraph 并发场景的标准解法。

### D12. 工具调用如何转设备操作？权限校验在哪？

**答案**：
1. 任务规划产出 `{tool_name, arguments}`；`tool_execution_node` 逐个调用 `tools/device_tools.py::execute_tool`。
2. 工具映射：`set_device_state`（改状态）、`get_device_state`（查单设备）、`list_room_devices`（列房间设备）、`trigger_scene`（触发场景）。
3. **权限校验**：`_require_control_permission(user_role)`——owner/resident 才能执行 set_device_state / trigger_scene（guest 只读）；user_id 从 state 取，family_id 由后端注入（用户无法伪造）。
4. 执行细节：`set_device_state` 先 `get_room_by_name` 定位房间 → `get_device_by_room_and_type` 定位设备 → `update_device_status` 写库 + 广播 + 记日志。
5. 结果统一 `{success, message, ...}` 写回 tool_results；异常被捕获转失败消息，不影响主流程。

### D13. 场景触发和普通设备控制的区别？

**答案**：
- **普通控制**（set_device_state）：单台设备、单个属性集（如空调温度），先审批后执行。
- **场景触发**（trigger_scene）：`execute_scene` 批量执行 actions（`{"actions":[{device_type, room_name, attributes}...]}`），一次可能操作多台设备（回家模式：开灯+开空调+开窗帘）。
- **返回值差异**（修复项 P3 后）：普通控制返回单设备结果；场景返回 `{success, success_count, failed_count, message}`，全部失败才 success=False、部分失败给 message 提示前端 warning。
- **权限**：都要求 owner/resident；场景本身是"用户预定义的一键批量操作"，AI 触发时同样走审批。

### D14. 流式输出实现？agent_token / agent_step / agent_done？

**答案**：
- 后端执行时通过 `on_event` 回调（WS 场景）推送三种事件：
  - `agent_step`：`{node, label, status:"running", chain}` —— 节点开始执行，前端展示"正在规划任务…"；
  - `agent_token`：`{content}` —— 回复文本逐段/逐字推送，前端 `appendToken` 追加到最后一条 assistant 消息；
  - `agent_done`：`{content, avatar_emotion}` —— 最终完整回复，前端 `completeResponse` 收尾并切表情。
- 实现位置：`agent/graph.py::_emit_node_event` + `api/agent.py` 的 ws 循环；HTTP 场景直接返回完整结果（前端 handleAgentResult 整条显示）。
- 前端状态：`stores/agent.js` 的 streamSteps/currentStreamNode 维护节点进度，isThinking 控制"思考中"动画。

### D15. 对话历史 / session 机制？为何截断 12 条？

**答案**：
- session_id 由前端生成（`session_时间戳_随机`）持久化 localStorage，刷新页面后复用；后端 conversations 表按 `session_id + user_id` 存 user/assistant/tool 三类消息。
- 请求时 `get_session_conversations(session_id, limit=10)` 取最近历史 → `build_llm_messages` 取**最后 12 条**注入 LLM 上下文。
- **为什么截断**：控制上下文窗口长度、控制 token 成本；太长的历史会稀释当前指令。
- 页面刷新恢复：`GET /api/agent/history` 返回最近 200 条 user/assistant 消息供前端渲染（tool 消息不展示）。
- 重置：`POST /api/agent/reset` 删除该 session 全部记录；切换家庭自动重置（watch familyId → resetSession）。

### D16. RAG 上下文如何注入意图识别和回复生成？

**答案**：
- **检索时机**：knowledge 链路入口 `rag_retrieval_node` 按用户输入检索（user_documents + family_regulations 双集合），结果写入 `state["rag_context"]`（文本片段拼接）和 `rag_sources`（来源元数据）。
- **注入意图识别**：`build_llm_messages` 把 rag_context 拼进系统提示（"知识库上下文：..."），帮助 LLM 区分"查询制度" vs "控制设备"（如"空调温度有什么规定"→ 知识查询而非控制）。
- **注入回复生成**：knowledge 链路的 `rag_answer_node` 基于检索片段组织回答并标注来源；report 链路报告生成也引用 rag_context（修复项 P4 保证报告真正检索）。
- 无相关文档时置"（无相关文档片段）"，不影响其他链路。

### D17. 纯闲聊快速识别？为何省一次 LLM 调用？

**答案**：`intent_recognition_node` 先跑 `looks_like_pure_chat(text)` 快速判断：**不含任何设备/房间关键词、且不在 NON_CHAT_TRIGGERS 触发词表**（如"我感冒了/我有点冷"这类隐含控制意图）时，直接判定纯闲聊 → chat 链路，**不调用 LLM 意图识别**。
**原因**：闲聊是最常见输入（"你好""今天怎么样"），规则短路省掉一次高延迟、高成本的 LLM 调用；规则判断不了的（隐式意图）才走 LLM。**成本与延迟优化**是本题得分点。

### D18. LLM 不可用时系统如何兜底？

**答案**（可用性设计，v2 无 mock）：
1. **意图层**：`_llm_recognize` 抛异常/超时/无 Key → 回退 `build_rule_intents` 规则引擎结果；规则也没有 → chat 链路（普通回复）。
2. **任务层**：`_llm_plan_tasks` 失败 → 回退 `build_rule_tasks` 规则规划。
3. **回复层**：`build_rule_response` / `build_rule_chat` / `build_rule_rag_answer` 等规则生成确定性回复——**无 MockClient**（已删除），兜底输出也基于真实设备数据，不是假数据。
4. 各节点 try/except 包裹 LLM 调用，**任何单点失败都不让整轮对话崩掉**。
**答案要点**：三层兜底（规则意图 → 规则规划 → 规则回复）全部是**真实数据路径**——qwen 无 Key 时整条链路仍能完成设备控制/查询，只是"聪明程度"降级，不是"数据造假"。

### D19. 报告链路为何必须走 RAG？

**答案**：`report_generation_node` 的职责是生成"家庭情况报告/总结"（触发词：报告/总结/汇总/统计），它"内部补齐全屋状态与 **RAG**"——报告应结合家庭规章制度等知识库内容。
**修复项 P4**：原实现里 `rag_retrieval_node` 因意图类型不含 knowledge_query 直接短路（返回"（无需检索）"），导致报告从不检索知识库。修复后检索条件增加 `"report" in intent_types`，报告链路真正执行检索，rag_context 注入报告 prompt。
**v2 可见性修复**：报告检索传 `include_private=False`——**只检索家庭规章制度（family_regulations），不检索私人文档**。私人文件仅在普通问答时按本人检索，避免"家庭情况报告"混入个人作业/说明书等私人内容（曾出现检索到私人 PDF 的泄漏案例）。
**答案要点**：体现"代码行为与文档承诺对齐"的审查与修复能力，以及"家庭级数据与个人级数据按场景隔离"的权限意识。

### D20. 模拟器与 Agent 控制如何协同？

**答案**：
- **共用同一状态模型**：模拟器（`scheduler/simulators/vacuum_simulator.py`）和 Agent 工具（`device_tools.py`）都通过 `update_device_status` 读写同一个 status JSON，**数据库是唯一权威源**。
- **职责分工**：Agent 改"用户指令属性"（power/status/温度）；模拟器改"随时间演化的属性"（电量 battery、位置 position），互不覆盖。
- **条件执行**：模拟器只在 `status == "cleaning"` 且 `power == "on"` 时模拟（电量 -1~3、位置随机偏移），每 30 秒一次。
- **状态值一致性**（修复项 P1）：清扫中状态必须统一为 `cleaning`（规则侧曾误写 `running`，导致模拟器不工作、前端卡片显示"待命"）。
- 模拟器每次更新同样走 `broadcast_device_update` 推送前端，所以"清扫中电量下降"是实时可见的。

---

### D21. 时间/天气查询工具如何实现？为什么是"工具"而不是 LLM 直接回答？

**答案**（v2 新增）：
- **get_current_time**：`device_tools.py::_tool_get_current_time`（async）直接用 `datetime.now()` 取真实时间，格式化 `{datetime, weekday, season(春/夏/秋/冬), period(早晨/上午/中午/下午/傍晚/晚上/深夜), text}`——**真实数据源，不走 LLM、不 mock**。
- **get_weather**：`_tool_get_weather` 从**家庭设备**取数——优先 `weather_station`（气象站），其次 `outdoor_sensor`（室外温湿度传感器），返回温度/湿度/空气质量/PM2.5；**家庭没有气象设备时明确返回"无法查询"**，不编造天气。
- **为什么是工具**：设备数据/时间属于"事实型、必须真实"的信息，LLM 直接回答会幻觉（编日期/编天气）；走工具调用即"检索真实数据源→返回给模型→模型组织话术"，与设备控制同一套 execute_tool 分发。
- **落地方式**：意图"现在几点/几号/星期几"→ 任务规划生成 `tool_name=get_current_time` 的 device_query 任务（PLANNING_PROMPT 第 8 条强制规则）→ execute_tool 分发到 `_tool_get_current_time`；天气同理。规则路径（qwen 无 Key）也支持这两个显式工具任务。
- **每条聊天 prompt 注入时间**：`build_current_time_text()` 把当前时间/季节/时段拼进每条聊天与 RAG 的 system prompt，让模型回答带时间上下文（如"晚上好"）。

**追问应对**：对比"LLM 直接回答时间"的幻觉风险，体现"事实型信息必须走工具/检索、生成型信息才交给 LLM"的分层设计。

### D22. 用户画像如何做到"自由 JSON"？为什么不用固定字段？

**答案**（v2 重构）：
- **背景**：固定字段画像（作息/喜好/习惯各一列）无法表达"养小猫需定时投喂"这类自由信息，且睡眠时间等分析不出字段。
- **方案**：数据库用户表只保留 `profile_json` 一个 TEXT 字段；模型（闲聊/情感链路）根据聊天记录**自主输出中文键 JSON**（如 `{"养宠物":"养了一只猫，需定时投喂","作息":"平时晚上11点睡觉"}`），后端校验是合法 JSON 后**整体保存**；前端展示时直接 `JSON.parse` 后 v-for 动态渲染键值对，**兼容旧字段**（旧画像对象也存进 profile_json）。
- **更新策略**：多轮闲聊增量合并（新键覆盖旧键、保留未变信息），由模型从最近聊天 + 旧画像输出合并后的 JSON；避免"重复分析不出来"。
- **数据流**：`analyze_user_profile`（LLM）→ 校验 → 写库 → WebSocket 推画像变更 → 前端即时刷新。

**追问应对**：说明"**数据结构跟随模型输出**而非模型迁就固定表结构"的思路——画像字段天然是开放集合，固定列是过度建模；JSON 自由结构 + 前端动态渲染是更低耦合的方案。

---

## E. RAG 知识库（10 问）

### E1. RAG 整体流程？

**答案**（`rag/` 目录 + `services/file_service.py`）：
```
上传（api/file.py：校验扩展名/大小 → save_upload_file → create_file_record）
  → process_file_async（后台异步）
      ├─ parse_file：PDF 用 PyMuPDF(fitz) 提取、DOCX 用 python-docx 提取
      ├─ TextChunker.chunk_by_paragraph：按段落切片
      └─ vector_store.add_documents：embedder 向量化 → 写入集合（ChromaDB 或本地 JSON）
查询（rag/retriever.py::retrieve_relevant_docs）
  → 双集合检索（user_documents 按 user_id 过滤 + family_regulations 按 family_id 过滤）
  → 按相似度排序取 top_k → 拼 rag_context + rag_sources 注入 Agent
```
**关键设计**：写入与查询分离、向量集合按"个人 vs 家庭"隔离、检索失败不阻断主流程。

### E2. 为什么双集合 user_documents / family_regulations？

**答案**（`rag/vector_store.py` 常量 USER_COLLECTION / FAMILY_COLLECTION）：
- **user_documents（私人知识文档）**：按 **user_id** 隔离——只有上传者本人可见/可检索；元数据带 user_id，查询 where 过滤。
- **family_regulations（家庭规章制度）**：按 **family_id** 隔离——全家成员共享（如"空调温度限制 26 度"）；只有**房主**能上传（接口 403 校验），家庭所有成员可检索；**不同家庭之间互相隔离**（查询 where family_id）。
**v2 场景级隔离**：普通问答检索两者；**家庭报告只检索 family_regulations**（`include_private=False`）——家庭级报告不混入个人私有内容。
**隔离维度不同**：个人 vs 家庭；同一套检索接口按集合选择不同过滤字段；`_query_chroma` 对两个集合分别 `where` 过滤，本地 JSON 回退同样逐条校验。

### E3. ChromaDB 与本地 JSON 回退？为何降级？

**答案**：`vector_store._init_backend()` 优先 `import chromadb` + `PersistentClient(path=chroma_path)`；任何异常（未安装/损坏）→ `_load_local()` 读 `local_vector_store.json`（records 数组：文本 + 向量 + 元数据），查询时在内存做余弦相似度。
**为什么降级**：chromadb 在 requirements-optional（可选增强依赖）；缺失时 RAG 仍可用（本地 JSON 向量检索功能完整，只是规模受限）。
**v2.1 变化**：向量化**不再降级**——嵌入强制阿里云 `text-embedding-v2`（`dashscope_embedder.py`，1536 维），未配 Key/请求失败直接抛错（上传标 failed、检索报"暂不可用"）；本地 JSON 只是**存储后端**回退，不是"嵌入模型"回退。

### E4. 相似度计算？为何 score=1.0-distance 需要 cosine 度量？

**答案**（`vector_store.py`）：
- 本地 JSON 模式：`_cosine(vec_a, vec_b)` 直接算余弦相似度，范围 [-1,1]，score 即相似度。
- ChromaDB 模式：query 返回 `distance`，代码 `score = max(0, min(1, 1.0 - distance))`——这个公式**只在 distance 是余弦距离（cosine 空间）时才成立**（余弦距离 = 1 - 相似度）。
- **修复项 P9**：ChromaDB 集合创建时未指定度量，默认是 **L2（欧氏距离）**——L2 无上界，`1.0 - distance` 会得出负分/失真，被 min_score=0.35 过滤掉导致检索几乎为空。修复：`get_or_create_collection(name, metadata={"hnsw:space":"cosine"})`。
**v2.1 阈值校准**：text-embedding-v2（1536 维稠密向量）相关片段实测余弦 ≈0.54~0.69、不相关多数 <0.30，`MIN_SCORE` 从 0.35 提到 **0.45**。
**答案要点**：能讲清"距离度量和分数公式必须匹配"这个细节，是实打实的工程经验。

### E5. 切片策略？为什么按段落？

**答案**：`TextChunker.chunk_by_paragraph(text)`——按段落（空行分隔）切分，过滤空段。
**为什么按段落**：段落是语义完整的最小自然单元，切出来的 chunk 自包含、检索命中后上下文可读；句子级切分容易截断语义，固定字数切分可能把一句话切成两半。演示场景文档不大，段落级足够；工业场景会叠加滑动窗口/标题层级切分。

### E6. top_k / min_score 怎么定？结果如何合并排序？

**答案**：`vector_store.py` 常量 `TOP_K=3`、`MIN_SCORE=0.35`。
- 双集合（个人 + 家庭）各自检索，结果统一放进列表，按 score 降序排序，取前 top_k。
- min_score 过滤低相关片段，避免"强答"。
- 排序后 `_pack_result` 包装 `{content, score, metadata{user_id, family_id, file_id, filename, collection}}`，source 用于回复时标注来源（"来自《xxx.pdf》"）。

### E7. 支持哪些格式？.doc 为什么不行？

**答案**：支持 **PDF**（PyMuPDF `fitz.open` 提取文本）和 **DOCX**（python-docx 读取段落）。
**.doc 不支持**：旧版二进制 Word 格式（.doc）与 OOXML（.docx）不是同一种格式，python-docx 只能解析 .docx；传 .doc 会在解析阶段抛异常 → 文件状态 failed。**修复项 P6**：上传入口白名单已移除 .doc（只留 .pdf/.docx），前端 accept 与提示同步，从源头拒绝而非事后失败。

### E8. 上传后向量库如何更新？重复文件？

**答案**：
- 上传成功 → 记录 status=pending → `process_file_async` 置 processing → 解析切片向量化 → 写入集合 → 置 ready（chunk_count 记录切片数）；失败置 failed。
- 前端 `FileUploadView` 每 2 秒轮询文件列表，直到没有 processing/pending 的文件。
- **重复文件**：`compute_content_hash`（MD5）计算了内容哈希，但当前实现**未用于查重**，重复上传会重复建向量（已知简化项）；删除文件时 `vector_store.delete_by_file_id` 按 file_id 清理对应向量。

### E9. 启动时全量重建向量库的问题？

**答案**：`main.py` lifespan 里启动时调 `file_service.rebuild_file_vectors()`：
1. **先对账清理孤儿向量（v2）**：枚举向量库全部 file_id，删除 `uploaded_files` 表中**已不存在**的文件的向量——防止历史残留（开发期直接写入向量库、无 DB 记录的文件）被其他账号/家庭检索到（真实泄漏案例：LS55U71 说明书等孤儿向量曾出现在检索结果）；
2. 再遍历 uploaded_files 里 ready/failed 的记录，先 `delete_by_file_id` 清理再重新处理入库。
**问题（P17）**：每次启动都全量重跑所有文件的解析+向量化，文件多时启动耗时很长；且 failed 文件也会反复重试。
**改进方向**：按 content_hash 增量（跳过未变文件）、懒加载（首次检索时再建）、失败文件设置重试上限或人工触发。

### E10. 检索异常如何不破坏主流程？

**答案**：`rag_retrieval_node` 里 `retrieve_relevant_docs` 包在 try/except 中，异常只记日志 `logger.warning("RAG 检索异常: %s", exc)` 并返回空列表 → rag_context="（无相关文档片段）"、rag_sources=[] → 知识链路降级为普通回答，其他链路（控制/闲聊）完全不受影响。**RAG 是增强不是依赖**，检索失败绝不阻塞对话。

### E11. 模型如何"自主决定"检索知识库（RAG 工具化）？

**答案**（v2.1）：RAG 不再只靠意图识别预判（knowledge_query/report），模型在生成回复时若认为需要知识库，可**像工具调用一样主动检索**：
- 新增 `agent/tools/knowledge_tool.py`：`RETRIEVE_KNOWLEDGE_TOOL`（retrieve_knowledge，参数 query）+ `execute_retrieve_knowledge`（真实检索，family 隔离）+ `chat_with_knowledge_tool`（工具循环）。
- **工具循环**：`chat_with_tools(tools=[retrieve_knowledge])` → 模型返回 `tool_calls` 则执行检索，把结果作为 `role=tool` 消息回传 → 模型基于结果生成；最多 2 轮防死循环；模型不需要检索时单次调用即返回（开销与普通 chat 相同）。
- **接入点**：`chat_generation_node` 与 `response_generation_node` 的 LLM 调用改为 `chat_with_knowledge_tool`——覆盖"我家 WiFi 密码是什么"这类被漏判为闲聊的知识问题。
- **降级**：LLM 异常仍走原规则兜底；检索失败返回"知识检索暂时不可用"，不影响对话主流程。

**追问应对**：对比"意图预判检索"与"模型自主检索"——前者快但漏判率高，后者准但多一次函数调用；两者共存形成双通道，RAG 是增强而非依赖。

---

## F. 实时推送与设备模拟器（8 问）

### F1. WebSocket 连接如何鉴权？

**答案**：连接地址带 token 查询参数：`ws://host:8000/api/agent/ws?token=<JWT>`（`useWebSocket.js` 拼 URL）。后端 `api/agent.py` 的 ws 端点收到连接请求时解析 token 并校验，失败直接 `await websocket.close()`；成功后把 `{user_id, role, family_id}` 存入连接状态，后续消息直接使用，**不需要每条消息都重新鉴权**。
（安全性说明：token 放 query 有被日志记录的风险，演示项目可接受；生产应改用子协议头或短期 ws token。）

### F2. 心跳 / 断线重连机制？

**答案**（`useWebSocket.js`）：
- **心跳**：连接建立后每 30 秒发 `{type:"ping"}`，保活并探测连接。
- **重连**：`ws.onclose` 触发；若**非主动关闭**（登出时 `intentionalClose=true` 不走重连）且重试次数 < 5，则 3 秒后重连，`reconnectAttempts` 递增；成功重连后计数清零。
- **降级**：WS 未连接时 `sendAgentMessage` 返回 false，聊天自动走 HTTP（`chatWithAgent`），功能不中断。

### F3. 状态推送为何前端按家庭过滤？

**答案**：后端 `broadcast_device_update` 把设备变更**广播给所有连接**（不区分家庭）；前端 `useWebSocket.js::dispatch` 收到 `device_status_update` 时判断 `data.family_id === userStore.familyId`，是自己的家庭才更新卡片。
**为什么这么设计**：后端广播实现最简单（一次遍历连接池），把过滤逻辑放前端避免了"每个连接维护订阅关系"的复杂度。**代价**：连接多时广播带宽浪费（万级连接是瓶颈，见 B12 优化方向——后端按家庭订阅）。

### F4. 扫地机器人模拟器模拟什么？

**答案**（`scheduler/simulators/vacuum_simulator.py` + `scheduler/engine.py`）：
- `engine.py` 用 APScheduler 注册 `simulate_vacuum`，**每 30 秒**执行一次。
- 逻辑：查全部 robot_vacuum 设备 → 若 `power=="on"` 且 `status=="cleaning"` → 电量 `battery -= 1~3`（下限 0）、位置 `position{x,y}` 各随机偏移 ±0.5 → 写库 → 广播前端。
- 效果：AI 下达"开始清扫"后，前端能看到电量实时下降、坐标移动的"活态"演示。

### F5. 为什么状态值必须统一为 cleaning？

**答案**（修复项 P1，真实踩坑）：
- 前端 `VacuumCard` 判定清扫中：`status === 'cleaning'`；`deviceStore.cleaningCount` 统计同样看 cleaning；模拟器也只模拟 cleaning。
- 但规则意图识别 `_parse_attributes` 曾把"开始清扫"写成 `status="running"` → **AI 指令后：前端显示"待命"、统计不算、模拟器不工作**——同一状态字段出现两个值，是典型的"状态字典漂移"。
- 修复：规则侧统一为 `cleaning`（停止 → `idle`），并新增"停止/暂停/回充"分支；任务规划默认属性同步修正。
**答案要点**：能讲清"一个状态字段必须有唯一权威取值表，并在所有读写方同步"是工程质量意识的体现。

### F6. 设备模拟器现状？为什么只剩扫地机？

**答案（v2）**：**空调模拟器（`ac_simulator.py`）已删除**——它原本是空实现/占位（无逻辑），属于死代码，用户要求"删除所有死代码、mock"。当前只有 `vacuum_simulator.py` 一个**条件执行的完整实现**：仅在 `status=="cleaning"` 且 `power=="on"` 时推进电量/位置，每 30 秒一次，模拟"随时间演化的设备行为"；Agent 控制的属性（power/status/温度）由 `update_device_status` 写库，两者互不覆盖、数据库是唯一权威源。

### F7. 数据库作为状态唯一来源的好处？

**答案**：所有设备状态的权威值在 MySQL devices.status；WebSocket 推送只是"变更通知/镜像"。
好处：① 服务重启/前端刷新状态不丢（从 DB 拉）；② 每次变更有 device_operation_logs 审计，可追溯"谁在几点改的"；③ Agent、手动控制、模拟器三条写入路径都走同一个 `update_device_status`，避免路径间状态分叉；④ 便于对账与回滚。

### F8. 多客户端并发推送一致性？

**答案**：以"**写库 → 广播**"的顺序保证最终一致：update_device_status 先提交数据库，成功后 broadcast；所有客户端收到的都是同一份新 status。多个客户端同时操作同一设备时，最后一次写库生效（当前无锁，演示场景接受）；前端还以本地操作结果即时更新（`controlDevice` 先更新本地），WS 到达后同步为权威值。严格并发控制（乐观锁/队列）属于 H6 的改进方向。

---

---

## G. 前端（8 问）

### G1. Vue3 组合式 API + Pinia？各 store 职责？

**答案**：项目用 Vue 3 组合式 API（setup 语法）+ Pinia 状态管理 + Element Plus + TailwindCSS。
**Store 划分**（`stores/`）：
| Store | 职责 |
|---|---|
| user | 登录态 token、用户信息、当前家庭 familyId、角色（isOwner/isGuest）、权限模式 |
| agent | 对话消息列表、流式步骤（streamSteps）、正在思考状态、待审批中断（pendingInterrupt） |
| device | 设备列表、状态映射（statusMap）、cleaningCount、按类型/房间的过滤与排序 |
| room | 房间列表与缓存 |

**要点**：状态按领域拆分（用户/对话/设备/房间），组件通过 store 读写，跨组件共享（设备卡片与列表同源）且可持久化（user 状态存 localStorage）。

### G2. 审批面板实现？默认全选？取消？

**答案**（`components/AgentInterruptPanel.vue` + `stores/agent.js`）：
- 收到 `agent_interrupt` 消息：type==="approval" 时展示面板，数据含 tasks（每条 description/expected_effect/risk_level）+ risk_level 徽标。
- **默认全选**：`selectedTaskIds` 初始化 `tasks.map(t => t.id)`，并显示"全选/取消全选"开关。
- **确认**：`confirmTasks` → 发 `{type:'resume', thread_id, resume_data:{approved:true, task_ids:selectedTaskIds}}`；同时关闭面板、清 pendingInterrupt。
- **取消**：`cancelTasks` → resume_data `{approved:false}`，后端跳过全部任务。
- **差异化提示**：勾选后文本显示"将执行 N 项操作"；风险等级 high 的任务显示红色警示。
- **澄清型中断**（type==="clarification"）：同一面板组件切换为问答模式，question + options 单选，resume_data `{answer: option}`。

### G3. 权限模式切换如何影响后端？

**答案**（修复项 P7）：
- 前端：AgentView 顶部"高级模式"开关 → `userStore.permissionMode`（`"normal" | "high"`），随聊天/恢复请求一起发送（WS 消息与 HTTP body 都有 permission_mode 字段）。
- 后端：`approval_node` 读取 state.permission_mode——`high` 跳过 interrupt 直接放行全部任务；`normal` 对需要审批的任务触发审批。
- **默认值一致性**：前端 store 默认 `normal`，与后端 `AgentChatRequest.permissionMode` 默认 `normal` 对齐（原实现前端默认 high，导致用户没开开关也"免审批"，P7 已修正）。
**答案要点**：权限模式是**前后端同步传递的运行时参数**，两端默认值必须一致，否则出现"前端以为要审批、后端直接放行"的安全缺口。

### G4. 前端如何展示 Agent 思考步骤？

**答案**：`stores/agent.js` 维护 `streamSteps`（数组）+ `currentStreamNode` + `isThinking`；`AgentThinkingPanel` 渲染。
- 收到 `agent_step`（node/label/status/chain）：更新 currentStreamNode，把节点加入步骤流（去重），显示节点名称与"进行中"动画。
- 节点流转可视化：步骤条按执行顺序展示（意图识别 → 任务规划 → 审批确认 → 工具执行 → 回复生成），chain 标签区分链路。
- `agent_done`：isThinking=false，清 currentStreamNode，节点标记完成。
- 目的：让用户看到 AI"正在做什么"，提升对话透明度与信任感（也是状态图可观测性的前端呈现）。

### G5. WebSocket 消息分发？

**答案**（`composables/useWebSocket.js::dispatch`，switch 按 type）：
- `device_status_update`：校验 family_id 匹配 → `deviceStore.updateDeviceFromWS` 更新对应设备状态与卡片。
- `agent_step`：更新思考步骤。
- `agent_token`：appendToken 追加回复文本。
- `agent_done`：completeResponse（完整内容、表情）。
- `agent_error`：显示错误提示、恢复输入状态。
- `agent_interrupt`：setPendingInterrupt → 弹审批/澄清面板。
- `agent_status`：处理连接状态/心跳回执。
**要点**：单一入口按类型路由，消息处理与发送解耦；未知类型忽略并 console 提示。

### G6. Vite 代理 vs 直连 8000？

**答案**：`vite.config.js` 配置了 `/api` 代理到 `http://localhost:8000`（含 ws:true），开发时 REST 走代理避免 CORS。
但前端 **WebSocket 默认直连 `ws://host:8000/api/agent/ws`**（`useWebSocket.js` 从 `import.meta.env.VITE_WS_URL` 读，未配置时拼 8000 端口），HTTP Agent 请求也走 axios 直连 8000（baseURL 同样可配）。
**修复项 P18**：README 表述"Vite 代理已包含 WS"与实际默认直连不符，属于**文档与实现不一致**的低风险项——代理只在显式配置 VITE_WS_URL 时生效。
**要点**：能说清"开发时 REST 走代理、WS 默认直连、环境变量可切换"即可。

### G7. 家庭切换如何重置页面？

**答案**：家庭选择器（FamilySwitcher）改 `userStore.familyId` 后，多个页面用 `watch(() => userStore.familyId, ...)` 响应：
- AgentView：清空对话（resetSession）、重新加载 opening 文本与历史。
- DeviceView / RoomView / SceneView：重新拉取该家庭的设备/房间/场景列表。
- 目的：避免上一个家庭的数据残留到新家庭视图（数据隔离的前端配合）。

### G8. 设备卡片工厂如何扩展新设备？

**答案**（`components/device/DeviceCardFactory.vue`）：
- 按 `device.type` 分发：robot_vacuum → VacuumCard；light → LightCard；其余 → SmartDeviceCard（通用控件模板：开关 + 按类型渲染属性控件）。
- 扩展新设备类型：① 新建专用卡片组件（或在 SmartDeviceCard 加类型分支渲染专属属性控件）；② DeviceCardFactory 映射表加一行 type→component。
- 卡片内"手动控制"调用 `controlDevice` → REST 更新后端 → 写库 + 广播 → 前端 WS 回调统一刷新（本地即时 + 服务端权威双更新）。
- 场景面板 ScenePanel 的设备类型选项 `deviceOptions` 同步扩展（新增类型才能出现在场景动作里）。

---

---

## H. 部署、工程与深度追问（11 问）

### H1. Docker Compose 编排？为何 build 上下文是 backend/ 根目录？

**答案**（`backend/docker-compose.yml`，注意 compose 文件在 backend/ 目录内）：
- 两个服务：`mysql`（mysql:8.0，挂载 `database/init.sql` 到 `/docker-entrypoint-initdb.d/` 首次自动建库建表；数据卷持久化）+ `backend`（构建 Python 镜像，映射 8000 端口，环境变量注入 DB 连接与 LLM 配置）。
- 数据卷：`./uploads`（上传文件）、`./chroma_data`（向量库）挂载到容器内，重启不丢。
- **修复项 P2**：原 compose 里 `build: {context: .}` 相对于 backend/ 是正确的，但目录结构里 Dockerfile 的 COPY 依赖 homemind/ 等相对路径——修复点是确认 compose 文件位于 `backend/` 根、build context 指向 `backend/`（与 Dockerfile 所在目录一致），否则 `COPY homemind/` 会找不到文件导致构建失败。
**答案要点**：compose 的 build context 必须等于"Dockerfile 中相对路径的基准目录"。

### H2. 环境变量管理？开发/生产差异？

**答案**：
- 后端：`backend/.env`（本地，pydantic-settings 自动加载）+ docker-compose `environment` 注入（容器生产）；关键项：MYSQL_URL、LLM_PROVIDER/API_KEY/MODEL、JWT_SECRET、CHROMA_PATH、UPLOAD_DIR。
- 前端：`.env.development`（VITE_API_BASE、VITE_WS_URL）+ `.env.production`（打包地址），构建时由 Vite 注入 `import.meta.env`。
- 差异：开发用本地 .env 直连、LLM 可用 mock；生产用环境变量覆盖、要求真实密钥且不落库不提交（.gitignore 排除 .env）。
- 注意（v2.1）：`LLM_API_KEY` 为空 → 工厂**直接抛错**（MockClient 已删除），由节点层规则引擎兜底，不会出现假回复。

### H3. requirements 与 requirements-optional 的区别？

**答案**：`requirements.txt`（核心必装）：fastapi、uvicorn、sqlalchemy+aiomysql、pydantic-settings、openai、python-jose、passlib…——**缺了系统起不来**。
`requirements-optional.txt`（可选增强）：**chromadb**、**openai-whisper**、edge-tts 等——**缺了自动降级**：无 ChromaDB 用本地 JSON 向量、无 Whisper 语音识别直接报错（v2 已删除 STT 演示文本）、无 edge-tts 语音按钮提示不可用。**注意：langgraph 已是必装依赖**（v2 起唯一执行引擎，不再可选降级）。
**设计意图**：轻量部署（不带重型 AI 依赖）也能完整跑通核心链路；生产可按需取舍。

### H4. 项目有哪些已知缺陷（低严重度）？

**答案**（真实审查出的 9 项，展示自我认知与改进能力，按代码可追溯）：
| 编号 | 缺陷 | 位置 | 影响 |
|---|---|---|---|
| P10 | 规划里 control_count>1 会把查询类任务 risk_level 误覆盖为 medium | nodes/task_planning.py | 查询任务被错误标为中风险 |
| P11 | 删除家庭后 families.owner_user_id 悬空指向已删用户 | family_service | 房主信息引用失效 |
| P12 | requirements.txt 注释乱码（"Agent ״̬ͼ"） | requirements.txt | 文档可读性 |
| P13 | .env.example 的 DEEPSEEK_MODEL=deepseek-chat 已弃用 | .env.example | 新用户配置无效模型 |
| P14 | 开发文档示例 bcrypt vs 实际明文存储 | README/开发文档 | 文档与实现不一致（演示取舍） |
| P15 | `_average` 用 `or None` 把 0 值温度当缺失 | 统计工具函数 | 0 度被误判为无数据 |
| P16 | 以"回复含 JSON"判定 LLM 输出异常，合法 JSON 会被误判 | LLM 输出校验 | 偶发误判 |
| P17 | 本地向量库每次启动全量重建 | main.py lifespan | 文件多时启动慢 |
| P18 | 前端 WS 默认直连 8000，与 README"Vite 代理含 WS"表述不符 | useWebSocket.js/README | 文档误导 |

**答案要点**：H4 是高频深挖题，建议背下表格；回答时先归类（一致性/文档/边界），再说"哪些已修（P1-P9）、哪些待修（P10-P18）及优先级"。

### H5. 设备量上万的最大瓶颈？如何优化？

**答案**：
1. **数据库**：状态 JSON 无法索引（按属性过滤全表扫）；device_operation_logs 无限增长 → **高频字段列化 + 复合索引、日志按时间分区归档**。
2. **WebSocket 广播**：全量广播 O(连接数)，每次状态变化推给所有客户端 → **后端按家庭/房间订阅**（连接存 family_id 订阅表），或引入 Redis Pub/Sub 做跨实例广播。
3. **查询**：设备列表每次查库无缓存 → **Redis 缓存热点 + 失效策略**。
4. **Agent 并发**：无状态化（thread 内存存断点），多实例需共享存储（Redis）→ 水平扩容 + 消息队列削峰。
5. **模拟器**：每 30 秒全表扫设备 → 只扫"活跃家庭"或按需订阅。

### H6. 多用户并发控制同一设备？

**答案**：当前实现**无锁**——`update_device_status` 直接 UPDATE，最后写入者生效（演示接受）。
**改进方案**（回答给出即可）：
- **乐观锁**：devices 表加 `version` 列，UPDATE 带 `WHERE version = ?`，影响行数 0 则冲突重读重试。
- **悲观锁**：事务内 `SELECT ... FOR UPDATE` 锁定行再修改（写冲突频繁时）。
- **应用层串行化**：按 device_id 做 Redis 分布式锁 / 单机 asyncio.Lock 字典。
- 同时配合设备操作日志，冲突时可审计回放。

### H7. 场景执行的事务性？部分失败怎么处理？

**答案**（修复项 P3）：
- 场景由多条动作组成（回家模式=开灯+开空调+开窗帘）。原实现**遇到失败动作即中止**，且失败时不提示。
- 修复后 `execute_scene`：**逐条执行、失败不中断**，最终返回三种结果：
  - `success=True, failed_count=0`（全部成功）；
  - `success=True, failed_count=N>0`（部分失败，message 说明失败项）；
  - `success=False, failed_count=全部`（全部失败）。
- 前端 `ScenePanel.vue`：全部成功绿色提示；部分失败 `warning` 弹窗"N 项执行失败：xxx"；全失败 error。
- **为什么不整体回滚**：智能家居场景偏"尽力而为"（灯开了，窗帘失败不必把灯也关掉），失败项可重试；数据一致性靠状态 JSON 单设备原子更新保证。

### H8. 如何扩展一种新设备类型？

**答案**（全链路清单）：
1. `database/init.sql`：演示数据加设备行（family/room/type/status JSON 初值）。
2. `services/device_service.py::_default_status`：该类型默认状态结构。
3. `agent/rules/intent.py`：别名表加类型映射 + `_parse_attributes` 加属性解析（如"调到 50%"）。
4. `agent/rules/planning.py`（如需）：默认属性/风险等级。
5. 前端：新卡片组件或 `SmartDeviceCard.vue` 加类型分支渲染专属控件；`DeviceCardFactory` 映射；`ScenePanel` 的 deviceOptions。
6. （可选）`scheduler/simulators/`：加模拟器并在 engine.py 注册定时任务。
**答案要点**：强调"**JSON 存储免改表结构**，改动集中在默认值 + 规则解析 + 前端卡片三处"。

### H9. 安全性：SQL 注入 / XSS / JWT 泄露？

**答案**：
- **SQL 注入**：SQLAlchemy ORM 参数化查询（`select(...).where(...)` 自动绑定），无字符串拼 SQL，注入面基本关闭；唯一手写 SQL 是初始化脚本。
- **XSS**：前端 Vue 模板默认转义（插值 `{{ }}` 不解析 HTML），未用 v-html 渲染用户输入；LLM 输出按文本渲染。
- **JWT 泄露**：token 存 localStorage（有 XSS 则泄露风险，演示可接受；生产用 HttpOnly Cookie + CSRF 防护）；`jwt_secret` 来自环境变量不硬编码。
- **其他**：密码明文（C2 已述）、上传白名单校验、接口统一 403 家庭校验；生产还需 HTTPS 与限流。

### H10. 如果让你重构，第一件事做什么？

**答案**（给出优先级与理由，展示架构判断）：
1. **设备状态 Schema 化**：为每类设备定义 Pydantic 状态模型 + 迁移把 JSON 拆列/索引——这是**数据地基**，解决 B12 的瓶颈与 P1 类一致性问题的根源。
2. **认证加固**：bcrypt 密码、HttpOnly Cookie/refresh token、登录限流（安全隐患优先级最高）。
3. **WebSocket 订阅化**：后端按家庭/房间订阅替代全量广播（为规模化打基础）。
4. **Agent 状态外置**：把 MemorySaver/_resume_store 换成 Redis，支持多实例水平扩展。
5. 文档同步（P18 类）与测试补齐（当前无自动化测试是最大工程短板）。

### H11. 这个项目能上生产吗？还缺什么？

**答案**：**当前定位是演示/教学平台，直接上生产有风险**，缺以下能力：
- **安全**：HTTPS、密码哈希（bcrypt）、登录限流、JWT 密钥管理与轮换、上传内容安全扫描。
- **可靠性**：自动化测试（单元/集成）、数据库备份与迁移工具（Alembic）、任务队列与失败重试、日志与监控告警（Prometheus/Grafana、Sentry）。
- **性能**：缓存、索引优化、WS 订阅化、水平扩容。
- **合规**：隐私政策、数据留存策略（对话内容含用户偏好数据）。
- **产品**：多语言、无障碍、移动端适配完善。
**表达方式**：先肯定"核心链路完整、降级设计好"，再列缺口与优先级——既展示信心又体现冷静的工程判断。

---

## 附：面试官最爱追问 TOP5 速答卡

| 追问 | 一句话核心 |
|---|---|
| A3 完整链路 | "前端 → Agent 状态图（意图→规划→审批→工具执行）→ 数据库写状态 → WebSocket 广播 → 卡片刷新" |
| D1/D2 状态图+中断 | "LangGraph 状态图，interrupt 挂起审批/澄清，Command(resume) + thread_id 恢复；HTTP 与 WS 双通道都能恢复" |
| D4 双通道 | "规则保确定性零成本，LLM 补隐式意图，LLM 失败回退规则，都失败落 chat 兜底" |
| D8+C10 审批与权限 | "normal 审批 / high 放行；前端 usePermission 管 UI，后端 Depends 强制校验，前端权限不可信" |
| H4 已知缺陷 | "审查出 18 个问题，9 个已修（状态值一致性/构建路径/场景部分失败/RAG 余弦度量…），9 个低风险待修并列出优先级" |

> 注：本项目修复相关编号（P1–P18）为内部审查记录，面试讲述时建议用自然语言描述问题现象与修复方案，不要背编号。