# 后端与 Agent 架构评审

> 评审范围：`backend/app` 全部 91 个 Python 模块，重点为 `agent/`（LangGraph 状态图、节点、规则、工具）、`api/agent.py`（HTTP/WebSocket 双入口）、`llm/`、`rag/`、`services/`、`websocket/`。
> 结论按 **P0（正确性 / 安全，必须修）→ P1（架构 / 可靠性，应尽快修）→ P2（工程化，建议修）** 分级。

---

## 一、架构总体判断

整体设计是**站得住脚**的，几个关键决策明显优于常见的"一把梭 ReAct"写法：

- **意图优先、按需查库**：`intent_recognition` 先于任何 DB 检索，纯闲聊走 `looks_like_pure_chat` 快速路径，不加载设备上下文；`house_status` 只在 control/report 链路懒加载（`graph.py:110-123`）。这符合"并非所有任务都需要检索数据库"的要求。
- **多链路 fan-out**：`route_after_intent` 返回 list 做并发分发，四条链路各自写 `chain_results` 的不同 key，并用 `operator.or_` reducer 合并（`state.py:48`）。
- **双路降级**：LLM 不可用时，意图 / 规划 / 回复 / 报告全部有规则版兜底，且 `factory_errors` 把 LLM 异常转成用户可读的 `model_warning`，避免"静默假回复"。
- **家庭隔离贯穿到底**：`family_id` 一路透传到工具层，`update_device_status` 显式校验设备归属（`device_service.py:23-24`），只读设备（传感器/计量表）在工具层被硬拦（`device_tools.py:177-186`）。

问题不在"方向"，而在**并发语义、状态归属、边界校验**这三处细节上——它们恰好是 LangGraph 多链路架构最容易踩的地方。

---

## 二、P0：正确性与安全问题

### P0-1　并发链路写同一 channel，`avatar_emotion` 会直接抛异常

`AgentState` 中只有 `chain_results` 声明了 reducer，`avatar_emotion` 是普通字段。但三条链路节点都会写它：

| 节点 | 返回值 |
| --- | --- |
| `chat_generation.py:112` | `avatar_emotion = "caring" / "leisure"` |
| `rag_answer.py:66` | `avatar_emotion = "neutral"` |
| `report_generation.py:85` | `avatar_emotion = "working"` |
| `approval.py:58`（取消时） | `avatar_emotion = "idle"` |

当 `compute_active_chains` 同时激活两条以上链路（如"讲解一下家里的用电规定，顺便陪我聊聊天" → `["chat","knowledge"]`；或"我有点冷" → control + emotional_care），这几个节点在**同一 superstep 并发执行并写同一个无 reducer 的 channel**，LangGraph 会抛 `InvalidUpdateError: Can receive only one value per step`。

**影响**：多意图请求直接 500，而这正是本项目对外宣传的核心卖点。
**建议**：给 `avatar_emotion` 也加 reducer（如 `Annotated[str, lambda a, b: b or a]` 取后写者），或改为写进 `chain_results` 各链路内、由 `result_aggregation` 统一裁决（后者更符合现有设计）。**同时应把所有跨节点共享字段都过一遍 reducer 清单**，`final_response`、`tool_results`、`needs_clarification` 同理需要审计。

---

### P0-2　WebSocket 路径手工聚合 state，多链路结果会被覆盖

`_run_langgraph_stream` 用 `final_state.update(update)` 逐 chunk 累加（`api/agent.py:161`）。`stream_mode="updates"` 返回的是**每个节点的原始返回值**（增量），不是 reducer 合并后的结果。因此：

```
chat 分支   → {"chain_results": {"chat": {...}},      "avatar_emotion": "leisure"}
rag 分支    → {"chain_results": {"knowledge": {...}}, "avatar_emotion": "neutral"}
手工 update → chain_results 只剩 {"knowledge": {...}}   ← chat 结果被覆盖
```

LangGraph 内部的 `or_` reducer 在这条路径上被**完全绕过**。

**影响**：`POST /api/agent/chat`（走 `ainvoke`）结果正确，`WS /api/agent/ws`（走 `astream`）丢链路结果——**同一份 state 图，两个入口行为不一致**。这类不一致极难排查。
**建议**：不要手工累加。改为在流结束后用 `agent_app.aget_state(config)` 取最终合并态，或对 `chain_results` 在累加时做 `dict.update` 合并而非整体覆盖。更彻底的做法是统一走 `astream`，删除 `ainvoke` 分支，保证只有一条执行路径。

---

### P0-3　`/agent/resume` 未校验线程归属，可越权恢复他人会话

`agent_resume` 直接把客户端传入的 `payload.thread_id` 交给 `_resume_agent`（`api/agent.py:331-336`），`current_user` 只用于事后保存结果，**没有校验该 thread 是否属于当前用户/家庭**。

而 `thread_id = f"thread_{session_id}"` 是确定性派生（`api/agent.py:65`），`session_id` 也由客户端提供。对比 `/agent/history` 严格带 `family_id + user_id` 过滤（`conversation_service.py:44-48`），`resume` 是这条链路上唯一没有隔离校验的入口。

**影响**：拿到（或猜中、从日志/分享链接泄露的）`session_id` 即可恢复他人中断态，读到 state 中的 `house_status`、工具结果，并**以对方身份继续执行**审批后的设备控制。
**建议**：在 checkpointer 的 `configurable` 中携带 `user_id`/`family_id` 并做校验，或在 resume 前用 `agent_app.aget_state()` 取回 state 后比对 `state["user_id"] == current_user["user_id"]`，不匹配直接 403。

---

### P0-4　路由函数里改 `state` 不生效，取消澄清后链路标记错乱

`route_after_clarify` 在路由函数体内直接写 `state["active_chains"] = ["chat"]`、`state["needs_clarification"] = False`（`graph.py:132-141`）。条件边函数只负责返回下一步节点名，**其副作用不会写回 channel**。同理 `_active_chains_from_state`（`graph.py:102`）里的 `state["active_chains"] = chains` 也是无效写入。

**影响**：用户点"取消澄清"后，`active_chains` 仍是澄清前的旧值（例如 `["control"]`）。`response_generation` 的"纯闲聊直通"分支（`len(active)==1 and active[0]=="chat"`，`response_generation.py:106`）因此不命中，回复会走一次多余的 LLM 二次生成，且可能对已取消的操作作出错误叙述。
**建议**：把这两个赋值从路由函数移到 `clarification_node` 的返回值里（节点返回值才是唯一合法的 state 写入口）。

---

### P0-5　热水器属性解析存在不可达分支，温度设置永久失效

`_parse_attributes` 中 `water_heater` 出现两次：

- `rules/intent.py:178-182`　处理"烧 / 关 / 停" → 只设 `power`
- `rules/intent.py:239-244`　处理 `(\d{1,2})\s*度` → 设 `temperature`

两者在同一个 `if/elif` 链中，前一个必然先命中，**第二个分支永远不会执行**（死代码）。

**影响**："把热水器调到 50 度"只会解析出 `power=on`，温度参数丢失；而下游 `_describe_effect` 与审批面板都会展示错误的效果预期。
**建议**：合并为单个 `water_heater` 分支，先解析温度再解析开关；并顺手清理该函数中其它重复的模式（如 `air_conditioner` 的 `power` 判断与末尾通用 `开/关` 兜底存在重叠）。

---

### P0-6　WebSocket 广播不分家庭，设备状态跨租户外泄

`WebSocketManager.broadcast_device_update` 向 `active_connections` **全量广播**（`websocket/manager.py:22-34`），注释写明"前端按 family_id 过滤"。

**影响**：A 家的设备 ID、类型、房间、状态会推送到 B 家用户的浏览器连接上。前端过滤不是隔离——数据已经出了服务端。这是家庭隔离设计（README 明确列为核心能力）上的一个实际破口。
**建议**：把 `active_connections` 改为 `dict[family_id, set[WebSocket]]`，`connect` 时记录 family，广播时按 family 定向；`disconnect` 同步清理。

---

## 三、P1：架构与可靠性

### P1-1　中断恢复强依赖进程内 `MemorySaver`，多进程/重启即失效

`build_agent_graph()` 用 `MemorySaver()` 编译（`graph.py:225`），注释也承认"服务重启后需重新发起对话"。但审批（`approval`）与澄清（`clarification`）**本质上是跨请求的等待**，用户思考几十秒后点确认是常态。

**影响**：`uvicorn --workers 4` 或 Docker 多副本下，resume 请求有 3/4 概率落到没有该 checkpoint 的进程 → 审批链路随机失败；重启即丢。`docker-compose` 单副本掩盖了这个问题，一旦横向扩容立刻暴露。
**建议**：换 `AsyncSqliteSaver` / `AsyncPostgresSaver`（项目已有 MySQL，可考虑 Postgres 或直接用 Redis 存 checkpoint）。这是让 Agent 真正可上线的关键一步。

### P1-2　工具执行结果不回灌模型，"Agent"实际是"计划-执行"流水线

`tool_execution_node` 把每条结果以 `role="tool"` 追加进 `messages`（`tool_execution.py:80-87`），但 `build_llm_messages` 只保留 `user` / `assistant` 两种角色（`_base.py:81-83`）——**tool 消息被过滤掉**，模型永远看不到自己调用的结果。

`response_generation` 之所以还能汇报结果，是因为它绕开 messages、改用 `_tool_summary(state)` 从 `tool_results` 直接拼文本。

**影响**：这不是 ReAct 循环，而是一次性"规划 → 执行 → 模板化汇报"。执行失败时模型无法自主重试、改参、换设备——而这恰恰是 Agent 与工作流的区别。tool 消息写进 DB 也只是存档冗余。
**建议**：要么明确承认这是流水线（把 tool 消息从 messages 里去掉，降低噪音），要么补齐闭环——让 `tool_execution` 之后回到一个 `reflect` 节点，把 tool 结果喂回模型判断是否重试/补动作（可设最大轮次）。`knowledge_tool.py` 里的 `chat_with_knowledge_tool` 已经实现了这个模式，可以复用。

### P1-3　流式与进度都是"事后回放"

- **假流式**：`_stream_agent_state` 把**已经完整生成**的 response 按 3 字符切片 + `sleep(0.02)` 推送（`api/agent.py:505-515`）。首字延迟等于整个 Agent 链路的耗时。
- **假进度**：`_run_langgraph_stream` 在 `astream(stream_mode="updates")` 拿到某节点的 update **之后**，才补发该节点的 `status: "running"` 事件（`api/agent.py:151-171`）。前端看到的"节点正在运行"永远是过去式。
- `BaseLLMClient.stream_chat` 已定义并被各客户端实现（`llm/base.py:30-35`、`qwen_client.py:102-119`），但**整条 Agent 链路没有任何地方调用它**。

**建议**：`response_generation` 改用 `stream_chat` 边生成边推 token；节点进度改用 `astream(stream_mode="debug")` 或 LangGraph callback 拿真实的节点进入/退出事件。

### P1-4　LLM 调用无超时、无重试、无并发预算

所有节点都是裸 `await client.chat(...)`，没有 `timeout`、没有指数退避重试、没有整体时间预算。一轮对话串行调用 2~4 次 LLM（意图 → 规划 → 回复），延迟线性叠加。

**影响**：上游抖动时单次请求可能挂几十秒；任一环节失败即降级为规则回复，用户体感是"AI 突然变笨"而非"服务异常"。
**建议**：在 `factory` 层统一注入 `timeout` 与重试策略；对可重试错误（429/5xx/超时）做 2 次退避重试，对 401/402 直接快速失败并复用现有 `model_warning` 通道。

### P1-5　会话历史有两个来源，状态会漂移

历史上下文同时来自：
1. MySQL `conversations` 表（`_build_initial_state` 注入最近 10 条，`api/agent.py:288-303`）
2. LangGraph checkpointer 里的 `messages`

**影响**：`/agent/reset` 只删 DB（`api/agent.py:386-391`），**不清 checkpoint**。用户"清空对话"后，若接着走 resume 路径，模型上下文里仍带着已删除的历史。两套来源的截断长度也不一致（DB 10 条 vs `build_llm_messages` 12 条）。
**建议**：明确单一事实来源。推荐以 DB 为准（每轮重建 messages），checkpoint 只用于保存中断态所需的控制字段。

### P1-6　同一请求内重复查库，事务边界缺失

一轮设备控制请求的查库次数：

| 位置 | 查询 |
| --- | --- |
| `intent_recognition.py:91-92` | `list_rooms_by_family` + `list_devices_by_family` |
| `task_planning.py:244-245` | `list_rooms_by_family` + `list_devices_by_family` |
| `house_status.py:96-98` | 再来一遍 + `get_family_environment` |

即**同一份房间/设备数据在一轮内被查 3 次**。且 `services/` 层每个函数各开一个 `get_db_session()`（`device_service.py` 全文），一次 Agent 请求会开十几个 session，无事务边界，`update_device_status` 与 `save_conversation` 之间也没有原子性。

**建议**：引入请求级上下文缓存（`contextvars` 存 house_status，或直接把 `house_status` 在入口处一次性算好传给下游——注意这与"按需懒加载"的取舍，可只对 control/report 链路预加载）；服务层改为接收 `session` 参数，由调用方控制事务范围。

### P1-7　权限模型：审批可被客户端自行绕过，高风险任务无强制审批

`permission_mode` 完全由前端 payload 决定（`schemas/agent.py` → `api/agent.py:298`），`approval_node` 只要看到 `"high"` 就无条件把全部任务标记 `approved`（`approval.py:35-41`）。

**影响**：任何住户都能通过构造 `permission_mode: "high"` 免掉审批面板。虽然 `_require_control_permission` 挡住了访客（`device_tools.py:157-160`），但**门锁上锁、摄像头开关这类 `risk_level=medium/high` 的操作，在 high 模式下同样跳过确认**——风险等级字段实际上没有参与决策。
**建议**：把"高级模式"变成后端可校验的授权（角色白名单 + 服务端存储），并在 `approval_node` 增加硬规则：`risk_level == "high"` 的任务**任何模式都必须中断确认**。

### P1-8　工具串行执行、无幂等、无补偿

`tool_execution_node` 用 `for task in tasks` 串行 `await`（`tool_execution.py:19`），多设备场景延迟线性增长；批量执行中部分失败不回滚（`scene_service.execute_scene` 明确只返回"部分动作失败"，`scene_service.py:216-236`）。

**建议**：独立任务用 `asyncio.gather` 并发（注意 `set_device_state` 内部有 WS 广播，需评估连接写入的并发安全）；对同一设备的重复控制做幂等合并；对场景类批量操作引入"失败即补偿"或至少把 `failed_count` 提升为前端强提示。

### P1-9　循环保护是未完成的半成品

`graph.py:32` 定义了 `MAX_ITERATIONS = 5`，**全项目无任何引用**；`AgentState.iteration` 字段从未被递增；`messages` 字段也没有 reducer。

实际的循环保护只靠 `MAX_CLARIFICATION_ATTEMPTS = 2`（`clarification.py:8`），而 `route_after_clarify` → `NODE_INTENT` → 可能再次澄清这条路径依赖该计数器，一旦未来新增其它回边（如 P1-2 建议的 reflect 节点）就会失控。

**建议**：删掉死常量，或把它真正接进 `route_*` 函数作为全局步数上限；补上 `iteration` 的递增与 `messages` 的 reducer 声明。

---

## 四、P2：工程化与可维护性

| 编号 | 问题 | 证据 | 建议 |
| --- | --- | --- | --- |
| P2-1 | **规则引擎过重**：`rules/intent.py` 740 行关键词分支，与 LLM 职责重叠，同一语义三处判定（`intent_recognition` 的 `KNOWLEDGE_QUERY_KEYWORDS` 兜底、`rag_retrieval` 的 `KNOWLEDGE_MARKERS`、`chat_generation` prompt 里要求调 `retrieve_knowledge`） | `rules/intent.py`、`rag_retrieval.py:9-13`、`chat_generation.py:35-37` | 把"是否需要检索"收敛成单一函数，意图识别与 RAG 检索共用；规则层只保留 LLM 完全无法覆盖的确定性场景（时间/天气/设备枚举） |
| P2-2 | **异常处理过宽**：满屏 `except Exception` 把 `KeyError`/`AttributeError` 这类编程错误也吞成"规则兜底"，真实 bug 被掩盖 | `intent_recognition.py:175`、`task_planning.py:90`、`rag_answer.py:55` 等 20+ 处 | 区分"可降级"（网络/API/超时）与"不可降级"（代码错误）；后者应 `logger.exception` 并向上抛 |
| P2-3 | **日志泄露且爆炸**：`log_node_run` 把整个节点返回值 `%s` 打进日志 | `_base.py:118-120`、`125-130` | 改为只记录关键字段与耗时；引入请求级 `trace_id` |
| P2-4 | **无可观测性**：无 tracing（LangSmith/OTel）、无 token 用量落库（`LLMResponse.usage` 拿到即丢）、无链路耗时统计 | `llm/qwen_client.py:43-46` | 至少把 usage 与节点耗时写进一张 `agent_traces` 表，为成本与性能优化提供依据 |
| P2-5 | **无自动化测试**：`backend/` 下无 `tests/`，只有根目录 `_check_rules.py`、`_test_intent.py` 两个临时脚本 | 项目布局 | 优先补三类：意图路由单测（纯函数、零依赖）、规则解析单测（能立刻抓出 P0-5 这类死分支）、图结构测试（验证 fan-out 不会并发写同一 channel） |
| P2-6 | **安全默认值**：`jwt_secret` 硬编码兜底值；CORS 写死 localhost；README 自述"演示密码明文保存、不做哈希" | `config.py:61`、`main.py:50-60`、`README.md:110` | 生产前：密钥强制从环境注入且缺失即启动失败；CORS 走配置；密码接 bcrypt |
| P2-7 | **向量库单例在 import 时初始化**：`vector_store = VectorStore()` 是模块级语句，会立刻创建 Chroma `PersistentClient`（文件锁）；`_init_backend` 用裸 `except Exception` 静默降级到本地 JSON | `vector_store.py:286`、`53-54` | 改为懒加载单例；降级时 `logger.warning` 明确告知，避免"以为在用 Chroma，其实在跑 JSON" |
| P2-8 | **embedder 无降级**（设计选择，但风险集中）：`get_embedder()` 失败即抛，DashScope Key 缺失会导致上传与检索全链路失败，而启动时 `rebuild_file_vectors` 的异常被吞 | `rag/embedder.py`、`main.py:30-34` | 启动自检：embedding 不可用时在 `/` 健康检查里明确暴露状态 |
| P2-9 | **WebSocket 鉴权方式**：token 走 URL query（会进 access log / 浏览器历史 / Referer）；未认证连接只回一条提示、**不关闭**，可无限发消息 | `api/agent.py:555-573` | 改首帧鉴权消息或 `Sec-WebSocket-Protocol`；鉴权失败直接 `close(code=1008)` |
| P2-10 | **checkpoint 与会话无 TTL**：`MemorySaver` 只增不减，`/agent/reset` 不清理 checkpoint | `graph.py:225`、`api/agent.py:379-391` | 换持久化 saver 时同步实现 TTL 清理（如 24h 未活跃即删） |

---

## 五、建议的改进顺序

**第一步（1 周内，止血）**
1. `avatar_emotion` 加 reducer 或改由 `result_aggregation` 统一裁决 —— 否则多意图请求会直接报错（P0-1）
2. 修 WebSocket 路径的 state 聚合，让两个入口行为一致（P0-2）
3. `resume` 增加归属校验（P0-3）
4. 修 `water_heater` 死分支（P0-5）
5. 广播按 family 分组（P0-6）
6. 把 `route_after_clarify` 里的 state 写入挪回节点（P0-4）

**第二步（2~3 周，可上线）**

7. checkpoint 换持久化后端（P1-1）
8. 补 LLM 超时/重试（P1-4）
9. 统一会话历史来源（P1-5）
10. 高风险任务强制审批 + 高级模式服务端授权（P1-7）
11. 补图结构与规则单测（P2-5，能顺手守住上面所有修复）

**第三步（持续）**

12. 真流式 + 真进度（P1-3）
13. 决定是否把"计划-执行"升级为带反思的闭环（P1-2）
14. 请求级缓存与事务治理（P1-6）、可观测性（P2-4）、规则层瘦身（P2-1）

---

## 六、一句话总结

这套 Agent 的**骨架设计是对的**——意图优先、多链路并发、双路降级、家庭隔离贯穿工具层，这些是很多同类项目做不到的。真正卡住它的是 **LangGraph 的并发语义没有被完全吃透**：`avatar_emotion` 缺 reducer、WebSocket 路径绕过 reducer、路由函数误当节点用，三处都属于"单链路测试全绿、多链路一跑就崩"的典型盲区。把 P0 六项修掉，这个架构就能从"能演示"跨到"能上线"。

---

## 七、修复记录（2026-10-11）

本轮实施范围：**仅 P0 六项 + LangGraph Postgres 持久化 + Store 接口预留**。业务逻辑（意图判定、链路路由、审批交互、回复生成）未做任何语义变更。

### 已修复

| 编号 | 问题 | 主要改动 |
| --- | --- | --- |
| P0-1 | `avatar_emotion` 并发写冲突 | `state.py`：声明 reducer `_merge_avatar_emotion`（后写非空者优先）。最终值仍由末尾串行的 `response_generation` 裁决，单链路行为不变 |
| P0-2 | WebSocket 手工聚合丢链路结果 | `api/agent.py`：新增 `_merge_reducer_updates`，按 `chain_results` / `avatar_emotion` 的 reducer 语义合并，替代 `final_state.update()` 的整体覆盖 |
| P0-3 | `/agent/resume` 越权 | `api/agent.py`：新增 `_assert_thread_owner`，恢复前用 `aget_state` 读回该 thread 的 `user_id` / `family_id` 比对；HTTP 与 WebSocket 两个入口都已接入 |
| P0-4 | 路由函数改 state 无效 | `clarification.py` 取消分支改为在**节点返回值**里写 `intents` / `active_chains`；`graph.py` 的 `route_after_clarify` 与 `_active_chains_from_state` 改为纯读取 |
| P0-5 | 热水器温度解析不可达 | `rules/intent.py`：合并两个 `water_heater` 分支，删除死代码 |
| P0-6 | WebSocket 广播跨家庭 | `websocket/manager.py`：连接按 `family_id` 分组，广播只发同家庭；家庭 ID 取自消息体已有字段，**四个调用方零改动** |
| P1-1 | 中断态持久化 | 新增 `agent/persistence.py`（`AsyncPostgresSaver` + `AsyncPostgresStore` + psycopg 异步池）；`main.py` 在 lifespan 初始化并注入图；失败自动降级为 `MemorySaver` 且不阻断启动 |
| — | 长期记忆接口预留 | 新增 `agent/memory.py`：命名空间 `("user_memory", family_id, user_id)` 与画像读写接口；**未接入**任何现有画像逻辑 |

配套改动：`config.py` 增加 `POSTGRES_URL` / `LANGGRAPH_PERSISTENCE_ENABLED` / `LANGGRAPH_POOL_MAX_SIZE`；`requirements.txt` 增加 `langgraph-checkpoint-postgres`、`psycopg[binary,pool]` 并把 `langgraph` 提到 `>=0.2.53`；`docker-compose.yml` 增加 `postgres` 服务与健康检查；`.env.example` 增加对应配置；`graph.py` 改为 `get_agent_app()` / `set_agent_app()` 运行时实例管理。

### 本轮未做（按所选范围）

P1-2 工具结果回灌模型、P1-3 真流式输出、P1-4 LLM 超时重试、P1-5 会话历史统一、P1-6 重复查库缓存、P1-7 权限模型、以及 P2 全部。按约定也不新增自动化测试。

### 已知影响与注意事项

1. **`/agent/resume` 新增 403 / 404 返回**：线程不存在或不属于当前用户时不再继续执行。前端正常回传服务端下发的 `thread_id` 不受影响。
2. **`langgraph` 版本需 ≥ 0.2.53**：`compile(store=...)` 与 Postgres checkpointer 依赖较新版本；升级前建议先确认现有图行为无回归。
3. **多副本部署**：`checkpointer.setup()` 会执行 DDL，应改为在发布流程中单独跑一次；同时保证 `副本数 × LANGGRAPH_POOL_MAX_SIZE < Postgres max_connections`。
4. **Postgres 不可用时**：服务仍可启动，但会降级为进程内 checkpointer，重启后中断态丢失——`GET /` 的 `persistence.backend` 字段可用于确认实际生效的后端。
5. **前端冗余逻辑**：设备状态广播已改为服务端按家庭定向，前端原有的 `family_id` 过滤成为冗余（无害，可后续清理）。

