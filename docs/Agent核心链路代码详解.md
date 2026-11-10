# ZHJJ Agent 核心链路代码详解（逐行讲解 + 真实数据演示）

> 覆盖范围：
>
> `backend/homemind/agent/`
>
>  全部核心文件 + 入口 
>
> `api/agent.py`
>
>  \+ 
>
> `llm/factory.py`
>
> （讲解 "每一行代码有什么用、如何跳转"）。
> 阅读顺序建议：总览 → 入口层 → 状态层 → 编排层 → 节点层 → 规则引擎 → 真实数据演示。



***

## 一、总览：一条消息从进来到出去，代码是怎么走的

先记住这张**调用链全景图**，后面所有讲解都是它的展开：



```
用户输入

&#x20; │

&#x20; ▼

api/agent.py

&#x20; ├─ HTTP:  POST /api/agent/chat            （聊天）

&#x20; ├─ HTTP:  POST /api/agent/resume           （中断后恢复）

&#x20; └─ WS:    ws://host/api/agent/ws           （聊天 + 恢复 + 流式）

&#x20; │

&#x20; ├─ \_build\_initial\_state()     构造 AgentState 初始字典

&#x20; ├─ save\_conversation()        把用户消息写入 MySQL

&#x20; ├─ set\_llm\_choice()           注入本次请求选用的模型（contextvar）

&#x20; │

&#x20; ▼

\_run\_agent(state, on\_event)

&#x20; │

&#x20; ├─ HAS\_LANGGRAPH=True ?

&#x20; │     ├─ 是：agent\_app.astream/ainvoke(state, config={thread\_id})

&#x20; │     │      （LangGraph 状态图，支持 interrupt/resume、并发）

&#x20; │     └─ 否：agent\_app.ainvoke(state, on\_node\_event=...)

&#x20; │            （LightweightAgentRunner 手写循环，同样节点函数）

&#x20; │

&#x20; ▼

节点依次执行（同一套节点函数，两种执行器共用）：

&#x20; intent\_recognition →（需要时）house\_status → 多链路并发 →

&#x20; task\_planning → approval（中断）→ tool\_execution → result\_aggregation

&#x20; → response\_generation → task\_execution → END

&#x20; │

&#x20; ▼

\_api/agent.py 收尾

&#x20; ├─ \_save\_agent\_result()   保存 assistant 回复到 conversations 表

&#x20; └─ HTTP: \_build\_chat\_response() 返回 {response/interrupt}

&#x20;    WS:   \_stream\_agent\_state()  流式推送 agent\_token/agent\_done/agent\_interrupt
```

**核心结论（背下来）**：Agent 是一个**状态机**。所有数据装在一个叫 `state`（AgentState）的字典里，每个节点函数 `接收 state → 改 state → 返回 state`，执行器负责按路由规则决定 "下一个节点是谁"。**入口 API 只负责构造初始 state 和收尾保存，业务全在节点里。**



***

## 二、入口层：api/agent.py 逐段讲解

文件：`backend/homemind/api/agent.py`。它是一切对话的**大门**。下面按行讲解关键函数。

### 2.1 `_build_initial_state()` —— 构造 Agent 的 "出生证明"



```
def \_build\_initial\_state(user\_input, current\_user, session\_id, permission\_mode="normal", ...):

&#x20;   history = history or \[]

&#x20;   house\_status = house\_status or {}

&#x20;   return {

&#x20;       "user\_input": user\_input,                    # ① 用户这句话原文

&#x20;       "user\_id": current\_user\["user\_id"],          # ② 身份三件套

&#x20;       "user\_role": current\_user\["role"],           #    role: owner/resident/guest

&#x20;       "family\_id": current\_user\["family\_id"],      #    family\_id: 数据隔离的钥匙

&#x20;       "session\_id": session\_id,                    # ③ 会话 ID（前端生成，刷新恢复用）

&#x20;       "permission\_mode": permission\_mode if permission\_mode in ("high","normal") else "normal",

&#x20;       "thread\_id": f"thread\_{session\_id}",         # ④ 中断恢复的句柄（LangGraph 靠它找断点）

&#x20;       "provider": provider or settings.llm\_provider,  # ⑤ 本次请求选的模型

&#x20;       "model": model or "",

&#x20;       "house\_status": house\_status,                # ⑥ 全屋状态（默认空，懒加载！）

&#x20;       "messages": \[                                # ⑦ 对话历史 + 当前输入

&#x20;           \*\[{"role": item\["role"], "content": item\["content"]} for item in history],

&#x20;           {"role": "user", "content": user\_input},

&#x20;       ],

&#x20;       "rag\_context": None, "rag\_sources": \[], "is\_knowledge\_query": False,

&#x20;       "intents": \[], "intent\_clarity\_score": 1.0,

&#x20;       "needs\_clarification": False, "clarification\_question": "",

&#x20;       "clarification\_options": \[], "clarification\_attempts": 0, "clarify\_source": "intent",

&#x20;       "active\_chains": \[], "chain\_results": {},

&#x20;       "tasks": \[], "needs\_approval": False,

&#x20;       "approval\_granted": False, "approved\_task\_ids": \[],

&#x20;       "tool\_results": \[], "success\_count": 0, "failure\_count": 0, "skipped\_count": 0,

&#x20;       "final\_response": None, "avatar\_emotion": "idle", "iteration": 0,

&#x20;   }
```

**关键设计点**：



* **house\_status 默认是空字典而不是查库**。注释明说：只有设备控制 / 报告链路才需要全屋状态，由节点懒加载 ——"并非所有任务都需要检索数据库"（比如纯闲聊就不碰库）。

* **thread\_id 由 session\_id 派生**：`thread_{session_id}`。中断恢复时前端只要传 session\_id，后端就能找回同一个 LangGraph 线程。

* 所有字段都有**默认值**，保证 state 在任何时刻都是 "结构完整的字典"，节点随便取字段不会 KeyError。

### 2.2 `_run_agent()` —— 执行器的总开关（LangGraph）

```
async def _run_agent(state: dict, on_event=None) -> dict:

    from app.agent.graph import agent_app

    set_llm_choice(state.get("provider"), state.get("model"))   # 注入模型选择（contextvar）

    config = {"configurable": {"thread_id": state["thread_id"]}}

    if on_event is None:

        result = await agent_app.ainvoke(state, config=config)          # HTTP：整段跑完

    else:

        result = await _run_langgraph_stream(agent_app, state, config, on_event)  # WS：逐节点推送

    return _normalize_interrupt(result)      # 把 LangGraph 的 __interrupt__ 转成统一结构
```

**逐行作用**：

1. `set_llm_choice(provider, model)`：把本次请求选的模型写进 **contextvar**（按 asyncio 上下文隔离），后续所有节点调 `get_llm_client()` 时读取它 —— 解决 "并发请求互相串模型" 的问题。

2. `agent_app`：`graph.py` 模块级单例（`build_agent_graph()` 编译结果），HTTP 与 WebSocket 共用同一个 LangGraph 实例。

3. `agent_app.ainvoke(state, config)`：LangGraph 编译图的整段执行。`config` 里的 `thread_id` 是断点索引 —— MemorySaver 按它保存 / 恢复状态。

4. `_run_langgraph_stream(...)`：WS 场景用 `astream(stream_mode="updates")` 逐节点推送 `agent_step`（节点进度），见 2.6。

5. `_normalize_interrupt(result)`：LangGraph 中断时返回 `{"__interrupt__": [Interrupt(value=payload)]}`，这里把它转成 `{"_interrupt": payload}` 统一格式，后续 HTTP/WS 都能用同一种方式读取。

> **架构说明（v2）**：早期版本存在 "LangGraph + 轻量执行器" 双实现（可选依赖降级），现**已删除轻量执行器分支**——LangGraph 是唯一执行引擎，`graph.py` 顶部直接 `from langgraph.graph import ...`，不再 try import 探测。相关删除见 4.2 / 4.5 / 4.7。
### 2.3 `_resume_agent()` —— 中断后的 "续命术"

```
async def _resume_agent(thread_id, resume_data, on_event=None, provider=None, model=None):

    from app.agent.graph import agent_app

    from langgraph.types import Command

    set_llm_choice(provider or "", model or "")     # 恢复时同样注入模型选择

    config = {"configurable": {"thread_id": thread_id}}

    if on_event is None:

        result = await agent_app.ainvoke(Command(resume=resume_data), config=config)

    else:

        result = await _run_langgraph_stream(agent_app, Command(resume=resume_data), config, on_event)

    return _normalize_interrupt(result)
```

**恢复机制（LangGraph 原生）**：`Command(resume=resume_data)` 从**上次 interrupt 的断点继续执行**，resume_data 会成为 `interrupt()` 的返回值（节点里 `wait_user` 拿到它）。断点状态由 **MemorySaver** 按 `thread_id` 保存——恢复不需要重新传整个 state，只要 thread_id。

**resume_data 的两种形态**（由前端传）：
- 澄清：`{"answer": "卧室"}`（或用户手输的字符串）；
- 审批：`{"approved": true, "task_ids": ["task_1"]}`。

**注意**：MemorySaver 是纯内存，服务重启断点丢失（已知限制）。
### 2.4 WS 入口 `agent_ws()` —— 消息分发循环



```
@router.websocket("/ws")

async def agent\_ws(websocket: WebSocket):

&#x20;   await ws\_manager.connect(websocket)          # 注册进连接池（广播用）

&#x20;   token = websocket.query\_params.get("token")  # 鉴权：URL query 里的 JWT

&#x20;   current\_user = current\_user\_payload\_from\_query(token)

&#x20;   while True:

&#x20;       data = await websocket.receive\_json()

&#x20;       message\_type = data.get("type")

&#x20;       if message\_type == "ping":               # 心跳保活

&#x20;           await ws\_manager.send\_agent\_message(websocket, {"type": "pong"})

&#x20;           continue

&#x20;       if message\_type == "chat":               # 新对话

&#x20;           ... \_build\_initial\_state(...) → \_stream\_agent\_response(...)

&#x20;       elif message\_type == "resume":           # 恢复中断

&#x20;           ... \_resume\_agent(...) → \_stream\_agent\_state(...)
```

**要点**：WS 是长连接**事件循环**，一个连接处理多轮 `chat` 和 `resume`；每个 chat 都是 "构造 state → 跑图 → 流式推送" 的完整闭环。

### 2.5 流式推送 `_stream_agent_state()`



```
async def \_stream\_agent\_state(websocket, final\_state, session\_id):

&#x20;   interrupt = final\_state.get("\_interrupt")

&#x20;   if interrupt:   # 中断 → 推 agent\_interrupt（前端弹审批/澄清面板）

&#x20;       await ws\_manager.send\_agent\_message(websocket, {"type": "agent\_interrupt", "interrupt": {...}})

&#x20;       return

&#x20;   response = final\_state.get("final\_response", "") or ""

&#x20;   await ws\_manager.send\_agent\_message(websocket, {"type": "avatar\_state", "state": "speaking"})

&#x20;   step = 3

&#x20;   for index in range(0, len(response), step):   # 每 3 个字符切一段推送

&#x20;       await ws\_manager.send\_agent\_message(websocket, {"type": "agent\_token", "content": response\[index:index+step]})

&#x20;       await asyncio.sleep(0.02)                 # 每段间隔 20ms → 打字机效果

&#x20;   await ws\_manager.send\_agent\_message(websocket, {"type": "agent\_done", "content": response, "avatar\_emotion": avatar})
```

**要点**：`agent_token` 逐段推 + `agent_done` 收尾；`agent_step`（节点进度）则是在 `_run_langgraph_stream` 里由 `astream(stream_mode="updates")` 逐节点触发的（见 2.6）。

### 2.6 `_run_langgraph_stream()` —— 逐节点推送 agent\_step



```
async def \_run\_langgraph\_stream(agent\_app, graph\_input, config, on\_event):

&#x20;   async for chunk in agent\_app.astream(graph\_input, config=config, stream\_mode="updates"):

&#x20;       for node\_name, update in chunk.items():

&#x20;           if node\_name == "\_\_interrupt\_\_":     # 中断帧单独抓出来

&#x20;               interrupt\_value = update

&#x20;               continue

&#x20;           await on\_event({"type":"agent\_step","node":node\_name,"label":NODE\_LABELS\[node\_name],

&#x20;                           "chain":NODE\_CHAIN\[node\_name],"status":"running"})   # 节点开始

&#x20;           final\_state.update(update)            # 该节点返回的 state 增量合并

&#x20;           await on\_event({"type":"agent\_step","node":node\_name,...,"status":"completed"})  # 节点结束
```

**要点**：`astream(stream_mode="updates")` 按节点逐个吐出 `{节点名: state更新}`—— 这正是前端 "思考步骤面板" 的数据来源：每个节点跑起来前端都能看到 "正在意图识别→正在任务规划→…"。



***

## 三、状态层：state.py 逐段讲解

文件：`backend/homemind/agent/state.py`（整个 Agent 的 "数据结构总纲"）。



```
import operator

from typing import Annotated, Any, Dict, List, Optional

try:

&#x20;   from typing import TypedDict

except ImportError:

&#x20;   from typing\_extensions import TypedDict

class AgentState(TypedDict, total=False):
```

**TypedDict 是什么**：声明 "这个字典长什么样" 的类型注解。`total=False` 表示字段可以缺省 ——LangGraph 的节点可以只返回要改的字段。它不是运行时约束，而是给 IDE / 静态检查用的文档。

字段按**职责分 9 组**（面试常考 "state 里有什么"）：



| 组       | 字段                                                                                                                                                                           | 谁写入                                             | 谁读取                             |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------- |
| 用户输入与身份 | user\_input / user\_id / user\_role / family\_id / session\_id / permission\_mode / thread\_id                                                                               | API 层 `_build_initial_state`                    | 几乎所有节点                          |
| 模型选择    | provider / model                                                                                                                                                             | API 层                                           | LLM 相关节点                        |
| 全屋状态    | house\_status                                                                                                                                                                | house\_status\_retrieval\_node                  | intent/task\_planning/response  |
| RAG     | rag\_context / rag\_sources / is\_knowledge\_query                                                                                                                           | rag\_retrieval\_node                            | rag\_answer / report / response |
| 意图      | intents / intent\_clarity\_score / needs\_clarification / clarification\_question / clarification\_options / user\_clarification / clarification\_attempts / clarify\_source | intent\_recognition\_node / clarification\_node | 路由函数 /task\_planning            |
| 多链路并发   | active\_chains / **chain\_results: Annotated\[Dict, operator.or\_]**                                                                                                         | 各链路节点                                           | result\_aggregation / response  |
| 任务与审批   | tasks / needs\_approval / approval\_granted / approved\_task\_ids                                                                                                            | task\_planning / approval                       | tool\_execution                 |
| 执行结果与回复 | tool\_results / success\_count / failure\_count / skipped\_count / final\_response / avatar\_emotion                                                                         | tool\_execution / aggregation / response        | API 收尾                          |
| 流程控制    | messages / iteration / \_interrupt / \_resume\_data                                                                                                                          | 各节点                                             | 执行器                             |

**最值得讲的一行**（面试高频）：



```
chain\_results: Annotated\[Dict\[str, Any], operator.or\_]
```



* 普通字段是 "后写覆盖"：节点 A 写了 key1，节点 B 写 key2，如果 B 返回整个 dict 会把 A 的 key1 覆盖掉。

* 加了 `operator.or_` reducer 后，LangGraph 合并方式变成 **dict 更新**（等价于 `{**old, **new}`）：并发链路各写各的 key（`chain_results["chat"]`、`chain_results["control"]`...），互不覆盖。

* 这就是**多链路并发结果共存**的底层机制 —— 没有它，并发执行的 chat/control/knowledge 会互相踩掉对方的结果。



***



***

## 四、编排层：graph.py 逐段讲解

文件：`backend/homemind/agent/graph.py`。它是 Agent 的**地图 + 交通警察**：声明有哪些节点、节点之间怎么跳。

### 4.1 节点常量：13 个节点的 "身份证"



```
NODE\_INTENT = "intent\_recognition"

NODE\_CLARIFY = "clarification"

NODE\_HOUSE\_STATUS = "house\_status\_retrieval"

NODE\_CHAT = "chat\_generation"

NODE\_RAG = "rag\_retrieval"

NODE\_RAG\_ANSWER = "rag\_answer"

NODE\_REPORT = "report\_generation"

NODE\_PLAN = "task\_planning"

NODE\_APPROVAL = "approval"

NODE\_TOOLS = "tool\_execution"

NODE\_AGGREGATE = "result\_aggregation"

NODE\_RESPONSE = "response\_generation"

NODE\_TASK = "task\_execution"
```

配套三张映射表：



```
NODE\_LABELS = {NODE\_INTENT: "意图识别", ...}   # 节点名 → 中文名（前端展示）

NODE\_CHAIN = {NODE\_INTENT: "意图识别", NODE\_TOOLS: "设备控制", ...}  # 节点 → 所属链路（前端分组）

CHAIN\_ENTRY = {"chat": NODE\_CHAT, "knowledge": NODE\_RAG,

&#x20;              "control": NODE\_PLAN, "report": NODE\_REPORT}  # 链路名 → 入口节点
```

**为什么用常量字符串**：LangGraph 的节点名必须是字符串，且边路由靠名字匹配。集中定义避免魔法字符串散落各处。

### 4.2 依赖说明：LangGraph 是唯一执行引擎（原 HAS_LANGGRAPH 已移除）

**v2 变更**：早期 `graph.py` 用 `try: import langgraph` 探测可选依赖，缺失时降级到手写轻量执行器（`HAS_LANGGRAPH` 布尔开关）。**用户明确要求完全实现 LangGraph**，该分支与降级代码已全部删除：

- `graph.py` 顶部直接 `from langgraph.checkpoint.memory import MemorySaver` / `from langgraph.graph import END, START, StateGraph`——**导入失败即服务启动失败**，不再静默降级；
- `nodes/_base.py` 直接 `from langgraph.types import interrupt`，`wait_user` 就是它的薄封装；
- `requirements` 中 langgraph 是**必装依赖**（不再放 requirements-optional）。

**为什么保留单一引擎**：双执行器意味着同一套中断/恢复/并发语义要实现两遍，行为易分叉（轻量执行器没有真正的断点续跑，是"快照重放"近似）；统一到 LangGraph 后，interrupt/resume/并发扇出只有一条实现路径，代码更可靠、更易维护。
### 4.3 四个路由函数：交通警察的 "指挥手册"

**①&#x20;**`route_after_intent`**（意图识别之后往哪走）**



```
def route\_after\_intent(state: dict):

&#x20;   if state.get("needs\_clarification"):      # 意图不明确（分<阈值）→ 先问清楚

&#x20;       return NODE\_CLARIFY

&#x20;   chains = \_active\_chains\_from\_state(state)  # 读/算激活链路

&#x20;   if \_needs\_house\_status(chains) and not state.get("house\_status"):

&#x20;       return NODE\_HOUSE\_STATUS               # 控制/报告链路且还没全屋状态 → 先查库

&#x20;   return \[CHAIN\_ENTRY\[chain] for chain in chains]   # 否则：并发进入所有链路入口
```

**关键**：**返回值是列表 = 并发扇出**。比如 "我有点冷"（emotional\_care → chat + device\_control → control），返回 `["chat_generation", "task_planning"]`，两个链路同时跑。

**②&#x20;**`route_after_house_status`**（全屋状态补齐后）**



```
def route\_after\_house\_status(state: dict) -> list:

&#x20;   chains = \_active\_chains\_from\_state(state)

&#x20;   return \[CHAIN\_ENTRY\[chain] for chain in chains]
```

全屋状态取回来后，还是要进各链路 —— 所以 house\_status 是一个 "必经的中转站"。

**③&#x20;**`route_after_clarify`**（澄清回答之后）**



```
def route\_after\_clarify(state: dict) -> str:

&#x20;   if state.get("final\_response"):           # 澄清超限（2次）已直接结束

&#x20;       return END

&#x20;   if state.get("clarify\_source") == "plan": # 规划阶段触发的澄清 → 回规划

&#x20;       return NODE\_PLAN

&#x20;   return NODE\_INTENT                          # 意图阶段触发的澄清 → 回意图重新识别
```

**关键**：`clarify_source` 字段标记 "这次澄清是谁发起的"—— 意图识别发起的回答后要**重新识别意图**（把用户补充的话拼进去），规划发起的回答后**直接回规划**（只差房间 / 参数信息）。

**④&#x20;**`route_after_plan`**&#x20;/&#x20;**`route_after_approval`



```
def route\_after\_plan(state: dict) -> str:

&#x20;   if state.get("needs\_clarification"):      # 多房间歧义/缺参数 → 再澄清

&#x20;       return NODE\_CLARIFY

&#x20;   return NODE\_APPROVAL                        # 否则进审批

def route\_after\_approval(state: dict) -> str:

&#x20;   if state.get("approval\_granted"):         # 审批通过 → 执行工具

&#x20;       return NODE\_TOOLS

&#x20;   return NODE\_AGGREGATE                       # 取消 → 直接去汇总（保留其他链路结果）
```

### 4.4 `_emit_node_event`：节点运行状态上报



```
async def \_emit\_node\_event(on\_node\_event, node: str, status: str) -> None:

&#x20;   if on\_node\_event is None:

&#x20;       return

&#x20;   await on\_node\_event({"type": "agent\_step", "node": node,

&#x20;       "label": NODE\_LABELS.get(node, node), "chain": NODE\_CHAIN.get(node, "执行链路"),

&#x20;       "status": status})
```

该函数在 v2 已随轻量执行器一并移除；`agent\_step` 事件统一由 api/agent.py 的 `_run_langgraph_stream`（astream updates）逐节点推送。

### 4.5 ~~LightweightAgentRunner~~（已删除）

**v2 变更**：`LightweightAgentRunner`（手写状态图：`while True` 澄清循环 + `asyncio.gather` 模拟并发 + `_resume_store` 快照重放）**已整体删除**。用户明确要求"必须完全实现 LangGraph，删除相关代码和参数"。

被删除的内容包括：
- `graph.py` 的 `LightweightAgentRunner` 类、`HAS_LANGGRAPH` 探测、`create_agent_runner()` 工厂切换；
- `api/agent.py` 的 `_resume_store` 快照字典与"重放"恢复路径；
- `nodes/_base.py` 的 `is_interrupted()` / `_resume_data` 轻量执行器适配。

删除后所有中断恢复都走 **LangGraph 原生 interrupt + Command(resume) + MemorySaver**，行为单一、无分叉。
### 4.6 NODE\_FUNCS 注册表 + build\_agent\_graph ()：LangGraph 版构建



```
NODE\_FUNCS = {NODE\_INTENT: intent\_recognition\_node, ...}   # 节点名 → 函数

def build\_agent\_graph():

&#x20;   workflow = StateGraph(AgentState)            # ① 用 AgentState 声明图

&#x20;   for name, func in NODE\_FUNCS.items():

&#x20;       workflow.add\_node(name, func)            # ② 注册 13 个节点

&#x20;   entry\_map = {CHAIN\_ENTRY\[c]: CHAIN\_ENTRY\[c] for c in CHAIN\_ENTRY}

&#x20;   workflow.add\_edge(START, NODE\_INTENT)        # ③ 起点固定进意图识别

&#x20;   workflow.add\_conditional\_edges(              # ④ 条件边：意图 → 澄清/全屋/各链路

&#x20;       NODE\_INTENT, route\_after\_intent,

&#x20;       {NODE\_CLARIFY: NODE\_CLARIFY, NODE\_HOUSE\_STATUS: NODE\_HOUSE\_STATUS, \*\*entry\_map},

&#x20;   )

&#x20;   workflow.add\_conditional\_edges(NODE\_HOUSE\_STATUS, route\_after\_house\_status, entry\_map)

&#x20;   workflow.add\_conditional\_edges(NODE\_CLARIFY, route\_after\_clarify,

&#x20;       {NODE\_INTENT: NODE\_INTENT, NODE\_PLAN: NODE\_PLAN, END: END})

&#x20;   workflow.add\_edge(NODE\_CHAT, NODE\_AGGREGATE)               # 聊天 → 汇总

&#x20;   workflow.add\_edge(NODE\_RAG, NODE\_RAG\_ANSWER)               # 检索 → 回答

&#x20;   workflow.add\_edge(NODE\_RAG\_ANSWER, NODE\_AGGREGATE)         # 回答 → 汇总

&#x20;   workflow.add\_edge(NODE\_REPORT, NODE\_AGGREGATE)             # 报告 → 汇总

&#x20;   workflow.add\_conditional\_edges(NODE\_PLAN, route\_after\_plan,

&#x20;       {NODE\_CLARIFY: NODE\_CLARIFY, NODE\_APPROVAL: NODE\_APPROVAL})

&#x20;   workflow.add\_conditional\_edges(NODE\_APPROVAL, route\_after\_approval,

&#x20;       {NODE\_TOOLS: NODE\_TOOLS, NODE\_AGGREGATE: NODE\_AGGREGATE})

&#x20;   workflow.add\_edge(NODE\_TOOLS, NODE\_AGGREGATE)              # 工具 → 汇总

&#x20;   workflow.add\_edge(NODE\_AGGREGATE, NODE\_RESPONSE)           # 汇总 → 回复

&#x20;   workflow.add\_edge(NODE\_RESPONSE, NODE\_TASK)                # 回复 → 收尾

&#x20;   workflow.add\_edge(NODE\_TASK, END)                          # 收尾 → 结束

&#x20;   return workflow.compile(checkpointer=MemorySaver())        # ⑤ 编译 + 断点存储

agent\_app = build\_agent\_graph()   # 模块级单例：HTTP 与 WS 共用同一个图
```

**三种边**（LangGraph 概念，面试常考）：



* `add_edge(A, B)`：**无条件边**——A 结束必去 B（如 rag\_retrieval → rag\_answer）。

* `add_conditional_edges(A, route_func, mapping)`：**条件边**—— 运行 `route_func(state)`，返回值在 mapping 里查下一个节点（如 intent → 澄清 / 全屋 / 链路）。

* **路由返回列表 = 并发边**：去多个节点同时执行（`route_after_intent` 返回 `["chat_generation", "task_planning"]`）。

**MemorySaver 的作用**：编译时挂 checkpointer，LangGraph 在执行每个节点前自动把 state 按 thread\_id 存入内存；中断时断点可查；`Command(resume=...)` 恢复时从断点继续。**注意**：MemorySaver 是纯内存，服务重启断点丢失（已知限制，前端会提示重新发起对话）。

### 4.7 执行器架构小结（面试必背）

**当前架构**：LangGraph **唯一**执行引擎（v2 已删除轻量执行器双实现）。关键结论：

| 维度 | LangGraph 实现 |
| ---- | ---- |
| 中断 | `langgraph.types.interrupt` 原生（节点里 `wait_user` 封装） |
| 恢复 | `Command(resume=data)` + MemorySaver（按 thread_id 断点） |
| 并发 | 条件路由函数返回**节点名列表** = 并发扇出 |
| 节点函数 | 13 个 `NODE_FUNCS` 注册表（唯一的节点实现） |
| 依赖 | langgraph 必装（requirements 主清单） |
| 断点存储 | MemorySaver 内存级（重启丢失） |

**面试口径**：① 为什么删轻量执行器——用户要求完全 LangGraph 化，且双实现让中断/恢复语义分叉、维护成本翻倍；② LangGraph 的核心价值——interrupt/resume 原生跨请求状态、条件边并发扇出、reducer 合并并发写、MemorySaver 断点。## 五、节点公共层：nodes/\_base.py 逐段讲解

文件：`backend/homemind/agent/nodes/_base.py`。**所有节点都 import 它**，是最底层的公共工具。

### 5.1 中断适配：wait_user（LangGraph 原生）+ 时间文本工具

```
from langgraph.types import interrupt as langgraph_interrupt

def wait_user(state, payload):

    """触发 LangGraph 中断并返回用户恢复数据。"""

    return langgraph_interrupt(payload)
```

节点代码只需调用 `wait_user(state, payload)`：LangGraph 运行时**抛出中断**、挂起整条执行链，state 由 MemorySaver 按 thread_id 落盘；用户回答后 `Command(resume=data)` 恢复，`interrupt()` 的返回值就是 `data`——**跨 HTTP/WS 请求的状态保持由框架完成**，节点不感知。早期 `is_interrupted()` / `_resume_data` 轻量执行器适配已删除。

**新增公共工具（v2）——每条聊天 prompt 注入真实时间**：

```
WEEKDAY_LABELS = ["星期一", ..., "星期日"]
SEASON_BY_MONTH = {1: "冬季", ..., 9: "秋季", ...}

def _season_label(month): ...   # 月份 → 季节
def _period_label(hour): ...    # 小时 → 早上/上午/中午/下午/晚上/凌晨

def build_current_time_text() -> str:
    """生成真实日期时间描述：'2026年9月12日 17:30，星期六，秋季下午'"""
    now = datetime.now()
    return (f"{now.strftime('%Y年%m月%d日')} {now.strftime('%H:%M')}，"
            f"{WEEKDAY_LABELS[now.weekday()]}，{_season_label(now.month)}{_period_label(now.hour)}")
```

**注入位置**：`chat_generation`（CHAT_PROMPT 首行"当前时间：{current_time}" + 回复要求"结合当前时间回应时段问候/作息建议"）、`response_generation`（RESPONSE_PROMPT）、`rag_answer`（RAG_ANSWER_PROMPT）。效果：闲聊回复会带时段问候（"周六傍晚了，秋季早晚温差大…"）。
### 5.2 恢复数据解析：extract\_answer /extract\_decision



```
def extract\_answer(resume\_data, field="answer"):

&#x20;   # 澄清：用户回答可能是字符串或 {"answer": "卧室"}

&#x20;   if isinstance(resume\_data, str): return resume\_data

&#x20;   if isinstance(resume\_data, dict): return resume\_data.get(field) or resume\_data.get("text") or ""

&#x20;   return ""

def extract\_decision(resume\_data):

&#x20;   \# 审批：{"approved": True/False, "task\_ids": \[...]}

&#x20;   if isinstance(resume\_data, dict): return resume\_data

&#x20;   return {}
```

两种中断恢复数据的 "解码器"：澄清取 `answer` 字段，审批取 `approved`+`task_ids`。

### 5.3 build\_llm\_messages：给 LLM 的 "对话历史胶囊"



```
def build\_llm\_messages(state, extra\_text=""):

&#x20;   from app.llm.message import Message

&#x20;   history = \[]

&#x20;   for item in state.get("messages") or \[]:

&#x20;       if item.get("role") in ("user", "assistant"):

&#x20;           history.append(Message(role=item\["role"], content=item.get("content") or ""))

&#x20;   history = history\[-12:]                    # ★只保留最近 12 条（控制上下文长度）

&#x20;   text = (state.get("user\_input") or "").strip()

&#x20;   if extra\_text:

&#x20;       text = f"{text} {extra\_text}".strip()  # 澄清回答拼在输入后面

&#x20;   if history and history\[-1].role == "user":

&#x20;       history\[-1] = Message(role="user", content=text)   # 替换最后的 user 消息

&#x20;   else:

&#x20;       history.append(Message(role="user", content=text))

&#x20;   return history
```

**关键**：只收 user/assistant（过滤 tool 消息，避免把工具 JSON 塞给模型）；**截断 12 条**；当前输入 "顶替" 最后一条 user 消息（因为初始 state 已把当前输入放进 messages，防止重复）。

### 5.4 log\_node\_run 装饰器：节点运行日志



```
def log\_node\_run(func):

&#x20;   label = NODE\_LABELS.get(func.\_\_name\_\_, func.\_\_name\_\_)

&#x20;   if inspect.iscoroutinefunction(func):

&#x20;       @functools.wraps(func)

&#x20;       async def async\_wrapper(\*args, \*\*kwargs):

&#x20;           logger.info("%s节点正在运行", label)

&#x20;           result = await func(\*args, \*\*kwargs)

&#x20;           logger.info("%s节点运行结果：%s", label, result)

&#x20;           return result

&#x20;       return async\_wrapper

&#x20;   \# ... 同步版同理
```

**装饰器模式**：所有节点函数 `@log_node_run` 包一层 —— 进节点打日志 "正在运行"，出节点打 "运行结果"，方便排障（看后端日志能追到每个节点进出）。兼容同步 / 异步函数（`inspect.iscoroutinefunction` 判断）。



***

## 六、意图识别节点：nodes/intent\_recognition.py 逐段讲解

**这个节点回答 "用户这句话是什么意思"**，是整个 Agent 的第一道门。

### 6.1 常量与 prompt



```
INTENT\_TYPES = ("device\_control", "device\_query", "scene\_trigger", "knowledge\_query",

&#x20;               "emotional\_care", "chat", "report", "clarification")
```

**8 种意图类型**：控制 / 查询 / 场景 / 知识 / 情感 / 闲聊 / 报告 / 澄清。

`INTENT_PROMPT` 是给 LLM 的系统提示，几个关键设计：



* "只输出 JSON"—— 方便 `extract_json` 解析；

* **隐式意图必须结合当前家庭状态动态判断，不套用固定操作**—— 如 "我有点冷" 要结合空调是否存在、当前温度决定动作；

* 明确了意图明确度评分规则：`>=0.8 直接执行 / 0.6-0.8 可执行需审批 / <0.6 中断询问`。

### 6.2 `_load_family_context`：加载家庭房间和设备



```
async def \_load\_family\_context(family\_id: int):

&#x20;   from app.services.device\_service import list\_devices\_by\_family

&#x20;   from app.services.room\_service import list\_rooms\_by\_family

&#x20;   rooms = await list\_rooms\_by\_family(family\_id)

&#x20;   devices = await list\_devices\_by\_family(family\_id)

&#x20;   room\_map = {room.id: room.name for room in rooms}

&#x20;   device\_context = \[

&#x20;       {"room\_name": room\_map.get(device.room\_id, ""), "type": device.type}

&#x20;       for device in devices

&#x20;   ]

&#x20;   return rooms, device\_context
```

**函数内部 import service**（延迟导入，避免循环依赖）。device\_context 是 `[{"room_name":"客厅","type":"air_conditioner"}, ...]`—— 只给 LLM 家庭真实设备清单，防止它编造不存在的设备。

### 6.3 节点主函数：intent\_recognition\_node（逐行）



```
@log\_node\_run

async def intent\_recognition\_node(state: dict) -> dict:

&#x20;   state = dict(state)                                    # 浅拷贝，不污染外层

&#x20;   user\_input = state.get("user\_input", "")

&#x20;   effective\_input = f"{user\_input} {state.get('user\_clarification', '')}".strip()

&#x20;   \# 澄清回答并入原输入，再识别（设计文档 3.3.3）

&#x20;   permission\_mode = state.get("permission\_mode", "normal")
```

**第一步：拼澄清回答**。"把空调调到 26 度" + 用户补充 "卧室" → "把空调调到 26 度 卧室"。



```
&#x20;   \# 纯闲聊快速路径

&#x20;   if looks\_like\_pure\_chat(effective\_input):

&#x20;       state\["intents"] = \[{"type": "chat", "description": "日常聊天或情感陪伴", "clarity": 1.0}]

&#x20;       state\["intent\_clarity\_score"] = 1.0

&#x20;       state\["needs\_clarification"] = False

&#x20;       ...

&#x20;       state\["active\_chains"] = compute\_active\_chains(state\["intents"])

&#x20;       return state
```

**第二步：闲聊短路**（省一次 LLM 调用，见 F17）。`looks_like_pure_chat` 在 rules/intent.py：不含设备词 / 房间词 / 知识关键词 / 触发词 → True。命中就直接构造 chat 意图返回，**不查库、不调 LLM**。



```
&#x20;   rooms, device\_context = await \_load\_family\_context(state\["family\_id"])

&#x20;   system = INTENT\_PROMPT.format(

&#x20;       device\_context=json.dumps(device\_context, ensure\_ascii=False) if device\_context else "（暂无设备）",

&#x20;       rag\_context=state.get("rag\_context") or "（此阶段不预检索，按需处理）",

&#x20;       house\_status=build\_house\_status\_text(state.get("house\_status") or {}),

&#x20;   )
```

**第三步：拼 LLM 系统提示**—— 把家庭设备、RAG 上下文、全屋状态三样 "背景知识" 塞给模型。



```
&#x20;   parsed = None

&#x20;   try:

&#x20;       client = get\_llm\_client()

&#x20;       response = await client.chat(

&#x20;           messages=build\_llm\_messages(state, state.get("user\_clarification", "")),

&#x20;           system=system, temperature=0.2, max\_tokens=1200,

&#x20;       )

&#x20;       parsed = extract\_json(response.content)

&#x20;   except Exception as exc:

&#x20;       logger.warning("意图识别 LLM 调用异常: %s", exc)   # 异常不中断，走规则兜底
```

**第四步：LLM 通道**。`get_llm_client()`（见第九节）按 contextvar 选模型；`extract_json` 从输出里抠 JSON。**任何异常都 catch 住**——LLM 挂了下文走规则。



```
&#x20;   if parsed and parsed.get("intents"):

&#x20;       intents = \_normalize\_intents(parsed)      # 清洗 LLM 输出（过滤非法类型）

&#x20;       score = float(parsed.get("intent\_clarity\_score", 0.9))

&#x20;       question = str(parsed.get("clarification\_question") or "")

&#x20;       options = \[...]

&#x20;   else:

&#x20;       rule\_result = build\_rule\_intents(

&#x20;           effective\_input, state.get("rag\_context") or "",

&#x20;           \[room.name for room in rooms], device\_context,

&#x20;           season=(state.get("house\_status") or {}).get("season", ""),

&#x20;       )

&#x20;       intents = rule\_result.get("intents") or \[]        # 规则通道（见第八节）

&#x20;       ...
```

**第五步：双通道融合**——LLM 出结果用 LLM（`_normalize_intents` 清洗）；LLM 失败 / 无结果回退规则引擎 `build_rule_intents`。**规则引擎还负责给 LLM 无法处理的隐式场景兜底**（如 "我感冒了" 规则直接给出情感 + 调温意图）。



```
&#x20;   threshold = 0.4 if permission\_mode == "high" else 0.6

&#x20;   needs\_clarification = score < threshold

&#x20;   if needs\_clarification and not question:

&#x20;       question = "您的指令还不够明确，请补充一下：..."

&#x20;   state\["intents"] = intents

&#x20;   state\["intent\_clarity\_score"] = score

&#x20;   state\["needs\_clarification"] = needs\_clarification

&#x20;   state\["clarification\_question"] = question

&#x20;   state\["clarification\_options"] = options

&#x20;   state\["clarify\_source"] = "intent"           # ★标记澄清来源=意图识别

&#x20;   state\["active\_chains"] = compute\_active\_chains(intents)   # ★算激活链路

&#x20;   return state
```

**第六步：明确度裁决 + 写回 state**。普通模式阈值 0.6、高级模式 0.4（高级模式更敢直接执行）；`clarify_source="intent"` 让澄清后路由回意图节点；`compute_active_chains` 把意图翻译成链路列表（chat/knowledge/control/report）。



***

## 七、全屋状态节点：nodes/house\_status.py

**职责**：把家庭房间、设备、环境、时间季节汇总成一个 "家庭快照"，注入 LLM 让模型能动态判断。

### 7.1 collect\_house\_status（数据采集）



```
async def collect\_house\_status(family\_id: int) -> Dict\[str, Any]:

&#x20;   rooms = await list\_rooms\_by\_family(family\_id)

&#x20;   devices = await list\_devices\_by\_family(family\_id)

&#x20;   environment = await get\_family\_environment(family\_id)   # 环境服务：温度/湿度/空气质量/天气

&#x20;   room\_map = {room.id: room.name for room in rooms}

&#x20;   device\_rows = \[{"name": d.name, "type": d.type, "type\_label": device\_label(d.type),

&#x20;                   "room": room\_map.get(d.room\_id, ""), "status": dict(d.status or {})}

&#x20;                  for d in devices]

&#x20;   now = datetime.now()

&#x20;   return {

&#x20;       "datetime": now.strftime("%Y-%m-%d %H:%M"),

&#x20;       "weekday": WEEKDAY\_LABELS\[now.weekday()],

&#x20;       "season": \_season(now.month),          # 月份 → 季节（SEASON\_BY\_MONTH 常量表）

&#x20;       "period": \_period\_label(now.hour),     # 小时 → 早上/上午/中午/下午/晚上/凌晨

&#x20;       "environment": environment,

&#x20;       "rooms": \[{"name": r.name, "device\_count": sum(1 for d in devices if d.room\_id == r.id)} for r in rooms],

&#x20;       "devices": device\_rows,

&#x20;   }
```

**数据从哪来**：三个 service（room/device/environment）+ datetime。**season/period 是本地算的**—— 让 LLM 知道 "现在是夏天晚上"，才能合理判断 "该开空调还是关窗帘"。

### 7.2 build\_house\_status\_text（prompt 化）



```
def build\_house\_status\_text(status) -> str:

&#x20;   if not status: return "暂无家庭状态数据。"

&#x20;   env = status.get("environment") or {}

&#x20;   lines = \[f"当前时间：{status.get('datetime','')}，{status.get('weekday','')}，{status.get('season','')}，{status.get('period','')}。",

&#x20;            f"室内温度：{env.get('indoor\_temperature') or '无数据'}℃，室内湿度：{...}%，空气质量：{...}；室外温度：{...}℃，天气：{...}。"]

&#x20;   devices = status.get("devices") or \[]

&#x20;   if devices:

&#x20;       lines.append("家庭设备：" + "；".join(\_device\_brief(item) for item in devices))

&#x20;   issues = \_collect\_issues(status)     # 安防异常：未上锁/门窗开/漏水/燃气/烟雾

&#x20;   if issues: lines.append("异常提示：" + "；".join(issues) + "。")

&#x20;   return "\n".join(lines)
```

`_device_brief` 把每台设备压成一行：`客厅空调(客厅空调)[power=on,temperature=26,mode=cool]`——**控制 prompt 长度**的关键。`_collect_issues` 是安防巡检：门未锁、窗户开、漏水、燃气泄漏、烟雾告警都会列成 "异常提示"（这是 report 链路 "安全告警务必指出" 的数据来源）。

### 7.3 house\_status\_retrieval\_node（节点入口，懒加载）



```
async def house\_status\_retrieval\_node(state: dict) -> dict:

&#x20;   current = dict(state)

&#x20;   if current.get("house\_status"):     # API 层已注入就复用（避免重复查库）

&#x20;       return current

&#x20;   family\_id = current.get("family\_id")

&#x20;   if not family\_id:

&#x20;       current\["house\_status"] = {}

&#x20;       return current

&#x20;   current\["house\_status"] = await collect\_house\_status(family\_id)

&#x20;   return current
```

**懒加载**：state 里已有 house\_status（比如上一轮对话带过来）就不查库；没有才采集。这就是 "并非所有任务都需要检索数据库" 的实现。

### 7.4 generate\_opening\_message（顺带：开场白）



```
async def generate\_opening\_message(family\_id, nickname):

&#x20;   status = await collect\_house\_status(family\_id)

&#x20;   try:

&#x20;       client = get\_llm\_client()

&#x20;       result = await client.chat(messages=\[Message(role="user", content="请生成开场白")],

&#x20;           system=OPENING\_PROMPT.format(house\_status=build\_house\_status\_text(status), nickname=nickname),

&#x20;           temperature=0.8, max\_tokens=240)

&#x20;       text = (result.content or "").strip()

&#x20;       if text: return text

&#x20;   except Exception as exc:

&#x20;       logger.warning("开场白生成失败，使用规则回退: %s", exc)

&#x20;   return \_rule\_opening(status, nickname)   # 规则版：按时段问候+设备状态+天气关怀
```

被 `api/agent.py` 的 `POST /agent/opening` 调用（首次进聊天页）。**同样的 "LLM 优先 + 规则兜底" 模式**。



***

## 八、澄清节点：nodes/clarification.py

**职责**：意图或规划不明确时，中断问用户。**v2 演进**：① 模糊需求改为"设备方案确认"式澄清（先确认要不要做，而不是直接问哪个房间）；② 澄清回答支持**多选**（顿号合并）；③ 用户点"取消"视为意图错误，退回闲聊。

```
MAX_CLARIFICATION_ATTEMPTS = 2    # ★防死循环上限

@log_node_run
async def clarification_node(state: dict) -> dict:

    if not state.get("needs_clarification"): return state

    if state.get("clarification_attempts", 0) >= MAX_CLARIFICATION_ATTEMPTS:

        state["final_response"] = "抱歉，我还是没能完全理解您的需求，请换个说法试试。"

        state["avatar_emotion"] = "sad"

        state["needs_clarification"] = False

        return state                      # 超限：直接结束（不再问）

    question = state.get("clarification_question") or "请补充说明您的需求。"

    payload = {"type": "clarification", "question": question,

               "options": state.get("clarification_options") or [],

               "thread_id": state.get("thread_id", "")}

    resume_data = wait_user(state, payload)    # ★LangGraph 中断：等用户回答

    if state.get("clarification_cancelled"):

        # 用户点"取消" = 意图理解错误 → 退回闲聊链路（route_after_clarify 处理）
        return state

    answer = extract_answer(resume_data)       # 取回答（字符串或 {"answer": "..."}）

    previous = (state.get("user_clarification") or "").strip()

    state["user_clarification"] = f"{previous} {answer}".strip() if previous else answer

    state["clarification_attempts"] = state.get("clarification_attempts", 0) + 1

    state["needs_clarification"] = False       # 回答后清零，路由回意图/规划

    return state
```

**防死循环机制**（面试题 D10）：`clarification_attempts` 每次 +1，达到 2 次不再问，直接给 final_response 结束。**对话必然收敛**。

**回答怎么用**：合并进 `user_clarification`。意图节点把它拼到 effective_input 重新识别；规划节点用 `find_room(user_clarification)` 提取房间。**多选回答**（"调低空调温度、关上窗户"）由规则引擎按顿号切分逐段解析（见 14.2 多段解析）。

**取消语义（v2 修复）**：前端点"取消"传 `{"cancelled": true}` → `clarification_cancelled=True` → `route_after_clarify` 把 intents 重置为 chat、`active_chains=["chat"]`、退回闲聊链路——由模型自然回应（如"好的，那就不调整了，有需要随时喊我"），**不会中断整个流程无任何回答**。
## 九、任务规划节点：nodes/task\_planning.py 逐段讲解

**职责**：把 "意图" 翻译成 "可执行任务"，并解决多房间歧义、补默认参数。

### 9.1 默认值辅助函数



```
def \_default\_attributes(device\_type: str) -> dict:

&#x20;   defaults = {

&#x20;       "air\_conditioner": {"power": "on"},

&#x20;       "light": {"power": "on"},

&#x20;       "curtain": {"position": 100},

&#x20;       "speaker": {"volume": 30},

&#x20;       "tv": {"power": "on"},

&#x20;       "robot\_vacuum": {"power": "on", "status": "cleaning"},   # ★P1：必须 cleaning

&#x20;       ...

&#x20;   }

&#x20;   return defaults.get(device\_type, {"power": "on"})
```

高级模式下 "只说设备没说参数" 时补默认值。注意 `robot_vacuum` 默认 `status:"cleaning"`—— 这是 P1 修复后统一的取值（前端 / 模拟器都认 cleaning）。



```
def \_default\_tool(intent\_type, device\_type) -> str:

&#x20;   if intent\_type == "scene\_trigger": return "trigger\_scene"

&#x20;   if intent\_type == "device\_query": return "get\_device\_state" if device\_type else "list\_room\_devices"

&#x20;   return "set\_device\_state"
```

意图类型 → 工具名的规则映射。

### 9.2 `_llm_plan_tasks`：LLM 规划通道（失败返回 None）



```
async def \_llm\_plan\_tasks(state: dict) -> list | None:

&#x20;   try:

&#x20;       client = get\_llm\_client()

&#x20;       system = PLANNING\_PROMPT.format(

&#x20;           house\_status=build\_house\_status\_text(state.get("house\_status") or {}),

&#x20;           intents=json.dumps(state.get("intents", \[]), ensure\_ascii=False),

&#x20;           permission\_mode=state.get("permission\_mode", "normal"),

&#x20;       )

&#x20;       result = await client.chat(messages=\[Message(role="user", content="请根据意图生成任务列表")],

&#x20;                                  system=system, temperature=0.2, max\_tokens=1600)

&#x20;       data = extract\_json(result.content)

&#x20;       raw\_tasks = data.get("tasks") if isinstance(data, dict) else None

&#x20;       if not raw\_tasks: return None

&#x20;       tasks = \[]

&#x20;       for index, raw in enumerate(raw\_tasks, 1):

&#x20;           task = \_normalize\_llm\_task(raw, index)

&#x20;           if task: tasks.append(task)

&#x20;       return tasks or None

&#x20;   except Exception as exc:

&#x20;       logger.warning("任务规划 LLM 调用异常: %s", exc)

&#x20;       return None
```

PLANNING\_PROMPT 里给了意图 JSON + 全屋状态 + 权限模式，要求只输出 `{"tasks":[...]}`，且 "房间不确定且家庭中该设备仅出现在一个房间时自动补全；多个房间时 room\_name 留空"——**房间补全规则写在 prompt 里让 LLM 做**。

**PLANNING_PROMPT v2 要点**（时间/天气查询工具的落点）：
- task 字段的 `tool_name` 枚举新增 `get_current_time` / `get_weather`；
- 第 8 条强制规则：**用户询问时间/日期/几点/几号/星期 → 必须输出 `tool_name=get_current_time` 的 device_query 任务；询问天气/气温/室外温度 → 必须输出 `tool_name=get_weather` 的 device_query 任务**，不允许用 get_device_state 代替。

`_normalize_llm_task` v2 新增**显式工具分支**：

```
explicit_tool = raw.get("tool_name")
if explicit_tool in ("get_current_time", "get_weather"):
    return {
        "task_id": task_id,
        "intent_type": "device_query",
        "description": description or ("查询当前日期与时间" / "查询家庭室外天气"),
        "tool_name": explicit_tool,          # 真实数据源工具
        "arguments": {},                     # 无需房间/设备
        "priority": "low",
        "risk_level": "low",
        ...
    }
```

规则路径（`rules/planning.py::build_rule_tasks`）同样支持 `intent.get("tool_name")` 为这两个值时生成显式工具任务——**LLM 与规则双通道都走真实时间/天气**。

### 9.3 `_normalize_llm_task`：LLM 输出规范化


把 LLM 的 task 字典规范成统一结构（`task_id = f"task_{index}"`）。三个分支：



* **device\_control** → `tool_name:"set_device_state"`，`needs_approval:True`，`risk_level` 默认 low、**door\_lock 强制 medium**（第 106-107 行：`if risk_level=="low" and device_type=="door_lock": risk_level="medium"`），`expected_effect` 由 `_describe_effect` 生成中文描述。

* **scene\_trigger** → `trigger_scene`，risk\_level medium。

* **device\_query**（有 device\_type → get\_device\_state；无 → list\_room\_devices）→ `needs_approval:False`，risk low。

### 9.4 节点主函数：task\_planning\_node（逐行）



```
@log\_node\_run

async def task\_planning\_node(state: dict) -> dict:

&#x20;   from app.services.device\_service import list\_devices\_by\_family

&#x20;   from app.services.room\_service import list\_rooms\_by\_family

&#x20;   state = dict(state)

&#x20;   permission\_mode = state.get("permission\_mode", "normal")

&#x20;   tasks = await \_llm\_plan\_tasks(state)          # ① LLM 规划

&#x20;   if not tasks:

&#x20;       tasks = build\_rule\_tasks(state.get("intents", \[]), permission\_mode)  # ② 失败回退规则
```

**第一步：LLM 优先、规则兜底**。`build_rule_tasks` 在 rules/planning.py（见第十一节）。



```
&#x20;   rooms = await list\_rooms\_by\_family(state\["family\_id"])

&#x20;   devices = await list\_devices\_by\_family(state\["family\_id"])

&#x20;   room\_map = {room.id: room.name for room in rooms}

&#x20;   device\_rows = \[{"room\_name": room\_map.get(device.room\_id, ""), "type": device.type} for device in devices]

&#x20;   available\_types = {device.type for device in devices}

&#x20;   tasks = \[task for task in tasks

&#x20;            if task.get("intent\_type") != "device\_control" or task.get("device\_type") in available\_types]
```

**第二步：校验设备真实性**—— 把 "控制不存在的设备" 的任务过滤掉（LLM 可能编造）。



```
&#x20;   needs\_clarification = False; question = ""; clarification\_options = \[]

&#x20;   user\_clarification = state.get("user\_clarification") or ""

&#x20;   for task in tasks:

&#x20;       device\_type = task.get("device\_type")

&#x20;       if not device\_type: continue

&#x20;       \# 从澄清回答中提取房间

&#x20;       if not task.get("room\_name") and user\_clarification:

&#x20;           room\_from\_answer = find\_room(user\_clarification)   # "卧室" → 卧室

&#x20;           if room\_from\_answer:

&#x20;               task\["room\_name"] = room\_from\_answer

&#x20;               task\["arguments"]\["room\_name"] = room\_from\_answer

&#x20;       if task.get("room\_name") not in (None, "", "all"):

&#x20;           continue

&#x20;       candidates = sorted({row\["room\_name"] for row in device\_rows

&#x20;                            if row\["type"] == device\_type and row\["room\_name"]})

&#x20;       if len(candidates) == 1:                 # 全屋唯一 → 自动补全房间

&#x20;           task\["room\_name"] = candidates\[0]

&#x20;           task\["arguments"]\["room\_name"] = candidates\[0]

&#x20;       elif len(candidates) > 1:                # 多房间 → 高级模式取第一个，普通模式澄清

&#x20;           if permission\_mode == "high":

&#x20;               task\["room\_name"] = candidates\[0]

&#x20;               task\["arguments"]\["room\_name"] = candidates\[0]

&#x20;           else:

&#x20;               needs\_clarification = True

&#x20;               option\_text = "、".join(f"{i}.{r}" for i, r in enumerate(candidates\[:6], 1))

&#x20;               clarification\_options = candidates\[:6]

&#x20;               action\_word = "查看" if task.get("intent\_type") == "device\_query" else "调整"

&#x20;               question = f"请问您想{action\_word}哪个房间的{device\_label(device\_type)}？当前有：{option\_text}"
```

**第三步：多房间歧义处理（面试题 D7 重点）**。逐个任务检查：房间已定就跳过；没房间就找该类型设备出现的所有房间 ——**唯一则自动补全、多个则高级模式直接选第一个、普通模式触发澄清**（"请问您想调整哪个房间的空调？当前有：1. 客厅 2. 卧室"）。



```
&#x20;       if task.get("intent\_type") == "device\_control" and not task.get("attributes"):

&#x20;           if permission\_mode == "high":

&#x20;               task\["attributes"] = \_default\_attributes(device\_type)

&#x20;               task\["arguments"]\["attributes"] = task\["attributes"]

&#x20;           else:

&#x20;               needs\_clarification = True

&#x20;               question = question or f"请问您想对{device\_label(device\_type)}执行什么操作？"
```

**第四步：空参数处理**。控制任务没属性：高级模式补默认值，普通模式澄清 "您想做什么操作"。



```
&#x20;   state\["tasks"] = tasks

&#x20;   state\["needs\_approval"] = any(task.get("needs\_approval") for task in tasks)

&#x20;   state\["needs\_clarification"] = needs\_clarification

&#x20;   state\["clarification\_question"] = question

&#x20;   state\["clarification\_options"] = clarification\_options

&#x20;   if needs\_clarification:

&#x20;       state\["clarify\_source"] = "plan"        # ★澄清来源=规划（回答后回规划而非意图）

&#x20;   return state
```

**第五步：写回 state**。`needs_approval` 只要有任一任务需要审批就 True；`clarify_source="plan"` 让 `route_after_clarify` 回答后回 `NODE_PLAN` 重新规划（只差房间 / 参数，不用重新识别意图）。



***

## 十、审批节点：nodes/approval.py 逐段讲解

**职责**：普通模式中断等用户勾选；高级模式直接放行。

### 10.1 `_approval_payload`：构造给前端的审批面板数据



```
def \_approval\_payload(state: dict) -> dict:

&#x20;   tasks = \[{"task\_id": t\["task\_id"], "description": t.get("description",""),

&#x20;             "tool\_name": t.get("tool\_name",""), "arguments": t.get("arguments",{}),

&#x20;             "expected\_effect": t.get("expected\_effect",""), "risk\_level": t.get("risk\_level","low")}

&#x20;            for t in state.get("tasks", \[]) if t.get("needs\_approval")]

&#x20;   risk\_levels = {t.get("risk\_level") for t in tasks}

&#x20;   risk\_level = "high" if "high" in risk\_levels else ("medium" if "medium" in risk\_levels else "low")

&#x20;   return {"type": "approval", "tasks": tasks, "risk\_level": risk\_level,

&#x20;           "thread\_id": state.get("thread\_id", "")}
```

**risk\_level 聚合规则**：只要有一个 high → high；否则有 medium → medium；全 low → low。前端按它显示 "高风险操作" 警示。

### 10.2 节点主函数：approval\_node（逐行）



```
@log\_node\_run

async def approval\_node(state: dict) -> dict:

&#x20;   state = dict(state)

&#x20;   tasks = state.get("tasks", \[])

&#x20;   approval\_tasks = \[t for t in tasks if t.get("needs\_approval")]

&#x20;   if state.get("permission\_mode") == "high" or not approval\_tasks:

&#x20;       state\["approval\_granted"] = True                          # 高级模式/无需审批 → 直接放行

&#x20;       state\["approved\_task\_ids"] = \[t\["task\_id"] for t in tasks]

&#x20;       for task in tasks: task\["status"] = "approved"

&#x20;       return state
```

**分支一：高级模式或无审批任务 → 直接放行**。所有任务 status="approved"。



```
&#x20;   resume\_data = wait\_user(state, \_approval\_payload(state))     # ★中断：弹审批面板等用户

&#x20;   decision = extract\_decision(resume\_data)                     # {"approved":..., "task\_ids":\[...]}

&#x20;   approved = bool(decision.get("approved", True))

&#x20;   approved\_ids = decision.get("task\_ids") or \[]

&#x20;   state\["approval\_granted"] = approved

&#x20;   chain\_results = dict(state.get("chain\_results") or {})

&#x20;   if not approved:                                              # 用户点取消

&#x20;       for task in tasks:

&#x20;           if task.get("needs\_approval"): task\["status"] = "skipped"

&#x20;       chain\_results\["control"] = {"cancelled": True, "message": "好的，已取消本次操作。"}

&#x20;       state\["chain\_results"] = chain\_results

&#x20;       state\["avatar\_emotion"] = "idle"

&#x20;       return state
```

**分支二：用户取消** → 所有需审批任务标 skipped；`chain_results["control"]={"cancelled":True}` 让回复生成节点知道 "用户取消了"（会回 "好的，已取消本次操作"）。路由 `route_after_approval` 看到 `approval_granted=False` → 去汇总（不执行工具）。



```
&#x20;   approved\_set = set(str(item) for item in approved\_ids)       # 用户勾选的部分任务

&#x20;   state\["approved\_task\_ids"] = list(approved\_set)

&#x20;   for task in tasks:

&#x20;       if not task.get("needs\_approval"): task\["status"] = "approved"   # 查询类任务默认放行

&#x20;       elif task\["task\_id"] in approved\_set: task\["status"] = "approved" # 勾中的执行

&#x20;       else: task\["status"] = "skipped"                                  # 没勾的跳过

&#x20;   state\["chain\_results"] = chain\_results

&#x20;   return state
```

**分支三：用户勾选确认** → 精确到 **task\_id 粒度**放行：勾中的 approved、没勾的 skipped、本来就不需要审批的（查询类）直接 approved。

**审批粒度设计**（面试题 D8）：前端默认全选，用户可取消个别高风险任务；后端按 task\_id 精确放行 ——"部分执行、部分跳过" 是批量控制场景的合理交互。



***

## 十一、工具调用节点：nodes/tool\_execution.py

**职责**：遍历 approved 任务，逐个执行工具，收集结果。



```
@log\_node\_run

async def tool\_execution\_node(state: dict) -> dict:

&#x20;   state = dict(state)

&#x20;   tasks = state.get("tasks", \[])

&#x20;   results = \[]

&#x20;   for task in tasks:

&#x20;       task\_id = task.get("task\_id", "")

&#x20;       description = task.get("description", "")

&#x20;       if task.get("status") != "approved":           # 非 approved（skipped）不执行

&#x20;           if task.get("needs\_approval"):

&#x20;               results.append({"task\_id": task\_id, "status": "skipped",

&#x20;                               "description": description,

&#x20;                               "data": {"success": False, "error": "用户未勾选该任务"}})

&#x20;           continue

&#x20;       tool\_name = task.get("tool\_name")

&#x20;       if not tool\_name:

&#x20;           results.append({"task\_id": task\_id, "status": "skipped", ...})

&#x20;           continue

&#x20;       try:

&#x20;           result = await execute\_tool(tool\_name=tool\_name,

&#x20;                                       arguments=task.get("arguments", {}),

&#x20;                                       user\_id=state\["user\_id"],

&#x20;                                       user\_role=state\["user\_role"],

&#x20;                                       family\_id=state\["family\_id"])

&#x20;       except Exception as exc:                        # 单任务异常不影响其他任务

&#x20;           logger.warning("工具执行异常 %s: %s", tool\_name, exc)

&#x20;           result = {"success": False, "error": f"工具执行异常: {exc}"}
```

**核心**：`execute_tool` 是设备工具总入口（见第十二节）。**身份三件套（user\_id/user\_role/family\_id）从 state 传入**—— 工具内部用它做权限校验和数据隔离。单个任务异常 catch 住，不影响后续任务。



```
&#x20;       if result.get("success"):

&#x20;           results.append({"task\_id": task\_id, "status": "success", "description": description,

&#x20;                           "message": result.get("message",""), "data": result})

&#x20;       else:

&#x20;           results.append({"task\_id": task\_id, "status": "failed", "description": description,

&#x20;                           "error": result.get("error","未知错误"), "data": result})

&#x20;       result\_text = json.dumps(result, ensure\_ascii=False)

&#x20;       state\["messages"].append({"role": "tool", "content": result\_text,

&#x20;                                 "tool\_call\_id": task\_id, "name": tool\_name})   # 工具结果进对话历史

&#x20;       await save\_conversation(..., role="tool", content=result\_text,

&#x20;                               tool\_call\_id=task\_id, tool\_name=tool\_name)       # 且持久化到库

&#x20;   state\["tool\_results"] = results                      # ★汇总结果列表

&#x20;   chain\_results = dict(state.get("chain\_results") or {})

&#x20;   chain\_results\["control"] = {"tool\_results": results} # 控制链路结果

&#x20;   state\["chain\_results"] = chain\_results

&#x20;   return state
```

**两处保存**：结果塞进 `state["messages"]`（对话历史，后续 LLM 回复能看到 "工具做了什么"）+ `save_conversation` 写库（tool 消息持久化，刷新页面后完整保留）。最终把控制链路结果写进 `chain_results["control"]`。



***

## 十二、设备工具：tools/device\_tools.py 逐段讲解

**职责**：Agent 操作设备的 "手"。所有工具强制带 family\_id 做数据隔离。

### 12.1 TOOL\_DEFINITIONS：给 LLM 看的工具说明书



```
TOOL\_DEFINITIONS = \[

&#x20;   ToolDefinition(name="set\_device\_state", description="设置智能设备的状态。当用户要求控制设备时调用此工具。...",

&#x20;                  parameters={"type":"object",

&#x20;                              "properties":{"room\_name":{...}, "device\_type":{..., "enum":\[...13 种可控设备...]},

&#x20;                                            "attributes":{..., "additionalProperties": True}},

&#x20;                              "required":\["room\_name","device\_type","attributes"]}),

&#x20;   ToolDefinition(name="get\_device\_state", description="查询设备当前状态与实时指标...", ...),

&#x20;   ToolDefinition(name="list\_room\_devices", description="列出某房间的所有设备...", ...),

&#x20;   ToolDefinition(name="trigger\_scene", description="触发预设场景，批量控制多个设备。如回家模式、睡眠模式。", ...),

&#x20;   ToolDefinition(name="get\_current\_time", description="获取当前真实日期与时间（年月日/星期/时分/季节/时段）。用户问现在几点、几月几号、星期几时调用。", ...),

&#x20;   ToolDefinition(name="get\_weather", description="查询家庭室外天气（优先气象站，其次室外温湿度传感器）。返回温度/湿度/空气质量/PM2.5；家庭无气象设备时返回无法查询。", ...),

]
```

这是 **function calling 风格**的工具定义（OpenAI 兼容格式），留给未来 LLM 直接调用工具的扩展点。当前实现里工具调用是节点显式做的（不经 LLM 选工具），定义仍保留供参考。

### 12.2 execute\_tool：总入口



```
async def execute\_tool(tool\_name, arguments, user\_id, user\_role, family\_id):

&#x20;   try:

&#x20;       if tool\_name == "set\_device\_state":   return await \_tool\_set\_device\_state(arguments, user\_id, user\_role, family\_id)

&#x20;       if tool\_name == "get\_device\_state":   return await \_tool\_get\_device\_state(arguments, user\_id, user\_role, family\_id)

&#x20;       if tool\_name == "list\_room\_devices":  return await \_tool\_list\_room\_devices(arguments, user\_id, user\_role, family\_id)

&#x20;       if tool\_name == "trigger\_scene":      return await \_tool\_trigger\_scene(arguments, user\_id, user\_role, family\_id)

&#x20;       if tool\_name == "get\_current\_time":  return await \_tool\_get\_current\_time()

&#x20;       if tool\_name == "get\_weather":       return await \_tool\_get\_weather(arguments, family\_id)

&#x20;       return {"success": False, "error": f"未知工具: {tool\_name}"}

&#x20;   except (ValueError, PermissionError) as exc:

&#x20;       return {"success": False, "error": str(exc)}

&#x20;   except Exception as exc:

&#x20;       return {"success": False, "error": f"工具执行异常: {exc}"}
```

按工具名分发；**任何异常都转成&#x20;**`{"success": False}`**&#x20;返回**—— 工具永远不抛给上层（tool\_execution\_node 的 try/except 是双保险）。

### 12.3 `_require_control_permission`：权限闸门



```
def \_require\_control\_permission(user\_role: str) -> None:

&#x20;   if user\_role not in ("owner", "resident"):

&#x20;       raise PermissionError("需要房主或住户权限")
```

**访客（guest）禁止控制**—— 控制类工具第一行就调它。用户角色来自 JWT 解析（API 层注入 state），无法伪造。

### 12.4 `_tool_set_device_state`：核心工具（完整链路）



```
async def \_tool\_set\_device\_state(arguments, user\_id, user\_role, family\_id):

&#x20;   \_require\_control\_permission(user\_role)                    # ① 权限校验

&#x20;   from app.services.device\_service import get\_device\_by\_room\_and\_type, update\_device\_status

&#x20;   from app.services.room\_service import get\_room\_by\_name

&#x20;   from app.websocket.manager import broadcast\_device\_update

&#x20;   room\_name = arguments\["room\_name"]; device\_type = arguments\["device\_type"]

&#x20;   attributes = dict(arguments\["attributes"])

&#x20;   CONTROLLABLE\_TYPES = {"air\_conditioner","light","robot\_vacuum","curtain","speaker","tv",

&#x20;                         "air\_purifier","humidifier","water\_heater","washer","fridge","door\_lock","camera"}

&#x20;   if device\_type not in CONTROLLABLE\_TYPES:                 # ② 只读设备保护

&#x20;       return {"success": False, "error": f"设备类型 {device\_type} 为数据采集/安防设备，仅支持查看状态"}

&#x20;   if device\_type == "air\_conditioner" and "temperature" in attributes and "power" not in attributes:

&#x20;       attributes\["power"] = "on"                             # ③ 空调设温度自动开机（产品约定）

&#x20;   room = await get\_room\_by\_name(room\_name, family\_id)        # ④ 找房间（带 family 隔离）

&#x20;   if not room: return {"success": False, "error": f"家庭中未找到房间: {room\_name}"}

&#x20;   device = await get\_device\_by\_room\_and\_type(room.id, device\_type, family\_id)   # ⑤ 找设备

&#x20;   if not device: return {"success": False, "error": f"家庭中 {room\_name} 未找到设备: {device\_type}"}

&#x20;   updated = await update\_device\_status(device\_id=device.id, attributes=attributes,

&#x20;                                        user\_id=user\_id, source="agent", family\_id=family\_id)  # ⑥ 写库+审计

&#x20;   await broadcast\_device\_update({                           # ⑦ WebSocket 广播

&#x20;       "type": "device\_status\_update", "device\_id": device.id, "family\_id": device.family\_id,

&#x20;       "room\_id": room.id, "device\_type": device.type, "status": updated.status})

&#x20;   summary = "、".join(f"{k}={v}" for k, v in attributes.items())

&#x20;   return {"success": True, "message": f"已将{room.name}的{device.name}更新为: {summary}",

&#x20;           "device": device.name, "status": updated.status}   # ⑧ 返回结果
```

**七步链路**（面试题 A3 的 "工具执行" 环节）：



1. 权限：owner/resident 才让控制；

2. 只读保护：传感器 / 表计 / 路由器不能被人为改状态（防 AI 误控）；

3. 产品约定：调空调温度自动开机（开发者文档约定）；

4. 找房间：`get_room_by_name(room_name, family_id)` —— **family\_id 条件防止跨家庭访问**；

5. 找设备：`get_device_by_room_and_type(room.id, device_type, family_id)` —— 房间 + 类型定位（场景动作同理）；

6. 写库：`update_device_status(..., source="agent")` —— 更新 status JSON + 写 device\_operation\_logs 审计（source 区分 manual/agent/scheduler）；

7. 广播：`broadcast_device_update` 推给所有 WS 连接（前端按 family 过滤）。

### 12.5 其余三个工具（简述）

* `_tool_get_device_state`：有 room\_name 按房间 + 类型精确查；无 room\_name 时全屋查该类型 ——**只有一台直接返回状态，多台返回设备列表**。

* `_tool_list_room_devices`：room\_name="all" 列全屋，否则列指定房间。

* `_tool_trigger_scene`：`_require_control_permission` + `execute_scene(scene_name, family_id, user_id, source="agent")` —— 场景批量执行（P3 修复后返回 success/success\_count/failed\_count）。

**v2 新增两个真实数据工具**：
- `_tool_get_current_time`（async）：`datetime.now()` 读真实时间，返回 `{success, data:{datetime, weekday, season, period, text}}`——"现在几点了"的**真实数据源**，不走 LLM、不 mock；
- `_tool_get_weather`（async）：从家庭 `weather_station`（优先）或 `outdoor_sensor` 读天气/温度/湿度/空气质量/PM2.5；**家庭无气象设备时明确返回"家庭中未安装气象站或室外温湿度传感器，无法查询天气"**（已按 family_id 隔离）。
- 两者均为 device_query 任务、low 风险、不需要审批；规则路径（qwen 降级）与 LLM 路径（deepseek）都验证过返回真实数据。

## 十三、其余链路节点（chat /rag/report / 收尾）

### 13.1 聊天链路：nodes/chat\_generation.py



```
CHAT\_PROMPT = """你是智能家居助理，正在与用户进行日常聊天或情感关怀。..."""

def build\_rule\_chat(state: dict) -> str:

&#x20;   user\_input = state.get("user\_input", "")

&#x20;   intent\_types = {item.get("type") for item in state.get("intents") or \[]}

&#x20;   if "emotional\_care" in intent\_types:     # 情感意图 → 关怀话术

&#x20;       return "看到您状态不太好，我有点担心。您先别急，需要我帮您做点什么，比如调整一下室温、播放舒缓的音乐，随时告诉我。"

&#x20;   return f"收到，我一直在呢。关于“{user\_input}”，您还需要我帮您做点什么吗？"

@log\_node\_run

async def chat\_generation\_node(state: dict) -> dict:

&#x20;   state = dict(state)

&#x20;   system = CHAT\_PROMPT.format(user\_input=..., intents=..., house\_status=build\_house\_status\_text(...))

&#x20;   text = ""

&#x20;   try:

&#x20;       client = get\_llm\_client()

&#x20;       result = await client.chat(messages=build\_llm\_messages(state), system=system,

&#x20;                                  temperature=0.8, max\_tokens=512)

&#x20;       text = (result.content or "").strip()

&#x20;   except Exception as exc:

&#x20;       logger.warning("聊天链路 LLM 调用异常: %s", exc)

&#x20;   if not text or extract\_json(text):       # LLM 失败/输出 JSON → 规则版聊天

&#x20;       text = build\_rule\_chat(state)

&#x20;   chain\_results = dict(state.get("chain\_results") or {})

&#x20;   chain\_results\["chat"] = {"text": text, "intents": state.get("intents", \[])}   # ★写入链路结果

&#x20;   state\["chain\_results"] = chain\_results

&#x20;   state\["avatar\_emotion"] = "caring" if "emotional\_care" in {...} else "leisure"

&#x20;   return state
```

**注意&#x20;**`extract_json(text)`**&#x20;的用途**：LLM 被要求 "不要输出 JSON"，万一它输出 JSON 结构（被误判为异常，P16 已知项），就用规则版文本兜底。结果写 `chain_results["chat"]`。

### 13.2 知识检索链路：nodes/rag\_retrieval.py



```
KNOWLEDGE\_MARKERS = KNOWLEDGE\_QUERY\_KEYWORDS + \["有什么规定", "是什么政策"]

def \_is\_knowledge\_query(user\_input: str) -> bool:

&#x20;   return any(marker in user\_input for marker in KNOWLEDGE\_MARKERS)

@log\_node\_run

async def rag\_retrieval\_node(state: dict) -> dict:

&#x20;   from app.rag.retriever import retrieve\_relevant\_docs

&#x20;   state = dict(state)

&#x20;   user\_input = state.get("user\_input", "")

&#x20;   intent\_types = {item.get("type") for item in state.get("intents") or \[]}

&#x20;   need\_retrieval = (bool(state.get("is\_knowledge\_query"))

&#x20;                     or "knowledge\_query" in intent\_types

&#x20;                     or "report" in intent\_types)          # ★P4：报告链路必须检索

&#x20;   if not need\_retrieval:

&#x20;       state\["rag\_context"] = "（无需检索）"

&#x20;       state\["rag\_sources"] = \[]

&#x20;       return state

&#x20;   # 家庭报告只检索家庭规章制度，不检索个人私人文件；普通问答两者都可检索

&#x20;   is\_report = "report" in intent\_types

&#x20;   try:

&#x20;       docs = await retrieve\_relevant\_docs(query=user\_input, user\_id=state\["user\_id"],

&#x20;                                           family\_id=state\["family\_id"], top\_k=3,

&#x20;                                           include\_private=not is\_report)

&#x20;   except Exception as exc:                                 # RAG 异常不破坏主流程

&#x20;       logger.warning("RAG 检索异常: %s", exc)

&#x20;       docs = \[]

&#x20;   sources = \[{"source": doc.get("source") or ..., "file\_id": ..., "collection": ...,

&#x20;               "score": doc.get("score"), "content": doc.get("content","")} for doc in docs]

&#x20;   state\["rag\_context"] = "\n".join(f"\[{src}] {doc}" for ...) if docs else "（无相关文档片段）"

&#x20;   state\["rag\_sources"] = sources

&#x20;   state\["is\_knowledge\_query"] = \_is\_knowledge\_query(user\_input) or bool(sources)

&#x20;   return state
```

**P4 修复的落点**：`need_retrieval` 条件里 `"report" in intent_types`—— 报告链路也强制走 RAG。检索异常只记日志、返回空结果，绝不中断对话（E10）。

### 13.3 知识回答链路：nodes/rag\_answer.py



```
RAG\_ANSWER\_PROMPT = """你是智能家居知识助手，请基于检索到的知识库内容回答用户问题。..."""

def build\_rule\_rag\_answer(state: dict) -> str:

&#x20;   sources = state.get("rag\_sources") or \[]

&#x20;   context = state.get("rag\_context") or ""

&#x20;   if sources:

&#x20;       source\_names = "、".join(dict.fromkeys(s.get("source") or "知识库" for s in sources))

&#x20;       return f"根据《{source\_names}》：{context}"          # 标注来源

&#x20;   if context and context not in ("（无需检索）", "（无相关文档片段）"):

&#x20;       return f"根据知识库：{context}"

&#x20;   return "暂未找到相关规定或偏好内容，您可以上传规章制度或偏好文档供我学习。"

@log\_node\_run

async def rag\_answer\_node(state: dict) -> dict:

&#x20;   ...  # LLM 生成回答（temperature=0.3 低随机度，忠实于知识库）

&#x20;   chain\_results = dict(state.get("chain\_results") or {})

&#x20;   chain\_results\["knowledge"] = {"text": text, "sources": state.get("rag\_sources") or \[]}

&#x20;   state\["chain\_results"] = chain\_results

&#x20;   state\["avatar\_emotion"] = "neutral"

&#x20;   return state
```

知识回答**必须标注来源**（《文件名》），找不到就说 "暂未找到"—— 不编造（RAG 的核心原则）。

### 13.4 报告链路：nodes/report\_generation.py



```
REPORT\_PROMPT = """你是智能家居家庭管家，请根据当前家庭状态生成一份简洁的家庭情况报告。

报告结构：① 环境概览 ② 设备与房间状态 ③ 异常或建议 ④ 结语 ..."""

@log\_node\_run

async def report\_generation\_node(state: dict) -> dict:

&#x20;   state = dict(state)

&#x20;   if not state.get("house\_status"):                       # 报告需要全屋状态

&#x20;       from app.agent.nodes.house\_status import house\_status\_retrieval\_node

&#x20;       state = await house\_status\_retrieval\_node(state)    # 内部补齐

&#x20;   if not state.get("rag\_context") or state.get("rag\_context") in ("（无需检索）","（无相关文档片段）"):

&#x20;       state = await rag\_retrieval\_node(state)             # 内部补 RAG（P4）

&#x20;   ...  # LLM 生成 → build\_rule\_report 兜底

&#x20;   chain\_results = dict(state.get("chain\_results") or {})

&#x20;   chain\_results\["report"] = {"text": text, "sources": state.get("rag\_sources") or \[]}

&#x20;   state\["chain\_results"] = chain\_results

&#x20;   state\["avatar\_emotion"] = "working"

&#x20;   return state
```

**节点内调用其他节点函数**（house\_status\_retrieval\_node、rag\_retrieval\_node）——LangGraph 里节点函数也是普通 Python 函数，可以互相调用，这是 "报告链路自包含" 的实现：不管图路由怎么走，报告节点自己保证全屋状态 + RAG 就绪（P4）。

**v2 可见性修复**：报告链路检索时 `include_private=False`——**只检索家庭规章制度，不检索私人文档**。私人文件（user_documents）仅在普通问答（knowledge 链路）时按本人检索，避免"家庭情况报告"混入个人作业/说明书等内容。

### 13.4.1 RAG v2.1：嵌入强制阿里云 text-embedding-v2 + 模型自主检索工具

**嵌入模型（v2.1 强制，禁止降级）**：
- 新增 `homemind/llm/dashscope_embedder.py`：直连阿里云 DashScope OpenAI 兼容接口（dashscope_base_url，model=text-embedding-v2），输出 **1536 维**稠密向量；分批调用（embed_batch_size=10）、单条超长截断（2000 字符）；
- `rag/embedder.py::get_embedder()` 改为返回 DashScopeEmbedder（不再取 LLM 客户端）；`file_service.process_file_async` 同步改用；
- **任何失败直接 raise（不降级）**：未配 Key / 请求失败 → 上传文件标记 failed、检索返回"知识检索暂时不可用"，绝无本地 n-gram 降级；
- 已删除死代码：`llm/embed_utils.py`（本地 64 维哈希向量）、四个 LLM 客户端的 `embed()` 方法与 `BaseLLMClient.embed` 抽象方法；
- **MIN_SCORE 校准**：1536 维稠密向量相关片段实测余弦 ≈0.54~0.69、不相关多数 <0.30，阈值从 0.35 提到 **0.45**；
- **维度迁移**：启动 `rebuild_file_vectors` 先 `clear_all()` 清空两集合（Chroma 同集合混维会报错），再按 uploaded_files 逐文件重建——旧 64 维向量全部被 1536 维替换，孤儿向量一并清除。

**模型自主检索（v2.1，RAG 不再只靠意图预判）**：
- 新增 `homemind/agent/tools/knowledge_tool.py`：`RETRIEVE_KNOWLEDGE_TOOL`（retrieve_knowledge，参数 query）+ `execute_retrieve_knowledge`（真实检索，family 隔离）+ `chat_with_knowledge_tool`（工具循环：chat_with_tools → 模型请求检索则执行并回传 tool 消息 → 再生成；最多 2 轮防死循环）；
- `chat_generation_node` / `response_generation_node` 的 LLM 调用改为 `chat_with_knowledge_tool`——**模型在闲聊/回复生成时若认为需要查阅知识库，可像工具调用一样主动检索**（如"我家 WiFi 密码是什么"这类被漏判为闲聊的知识问题）；
- 模型不需要检索时单次调用即返回，开销与普通 chat 相同；LLM 异常仍走原规则兜底。

### 13.5 结果汇总：nodes/result\_aggregation.py



```
@log\_node\_run

async def result\_aggregation\_node(state: dict) -> dict:

&#x20;   state = dict(state)

&#x20;   results = state.get("tool\_results", \[])

&#x20;   state\["success\_count"] = sum(1 for item in results if item.get("status") == "success")

&#x20;   state\["failure\_count"] = sum(1 for item in results if item.get("status") == "failed")

&#x20;   state\["skipped\_count"] = sum(1 for item in results if item.get("status") == "skipped")

&#x20;   state.setdefault("chain\_results", {})

&#x20;   return state
```

一句话节点：统计工具执行三类结果数。数据供回复生成 prompt 用（"成功 X，失败 Y，跳过 Z"）。

### 13.6 回复生成：nodes/response\_generation.py



```
@log\_node\_run

async def response\_generation\_node(state: dict) -> dict:

&#x20;   state = dict(state)

&#x20;   chain\_results = state.get("chain\_results") or {}

&#x20;   active = state.get("active\_chains") or \[]

&#x20;   if len(active) == 1 and active\[0] == "chat":             # 纯闲聊：直接用聊天文本

&#x20;       text = (chain\_results.get("chat") or {}).get("text") or ""

&#x20;       if text:

&#x20;           state\["final\_response"] = text

&#x20;           state\["avatar\_emotion"] = build\_rule\_avatar\_emotion(state)

&#x20;           return state

&#x20;   system = RESPONSE\_PROMPT.format(

&#x20;       user\_input=..., intents=json.dumps(state.get("intents",\[]), ensure\_ascii=False),

&#x20;       chain\_texts=\_chain\_texts(state),                     # 各链路结果文本化

&#x20;       success\_count=..., failure\_count=..., skipped\_count=...,

&#x20;       tool\_results=\_tool\_summary(state))                   # 工具执行明细

&#x20;   response\_text = ""

&#x20;   try:

&#x20;       client = get\_llm\_client()

&#x20;       result = await client.chat(messages=build\_llm\_messages(state), system=system,

&#x20;                                  temperature=0.5, max\_tokens=1024)

&#x20;       response\_text = (result.content or "").strip()

&#x20;   except Exception as exc:

&#x20;       logger.warning("回复生成 LLM 调用异常: %s", exc)

&#x20;   if not response\_text or extract\_json(response\_text):     # 防 LLM 误输出 JSON

&#x20;       response\_text = \_merge\_chain\_response(state)         # 规则版合并

&#x20;   state\["final\_response"] = response\_text or \_merge\_chain\_response(state)

&#x20;   state\["avatar\_emotion"] = build\_rule\_avatar\_emotion(state)

&#x20;   return state
```

**两条捷径**：



1. **纯闲聊直接透传**：只有 chat 一条链路时，不用再调 LLM 生成回复（避免 "你好" 被回复成啰嗦两遍），直接用 chat 链路的文本。

2. **规则合并兜底**：`_merge_chain_response` 按 "知识 > 报告 > 聊天 > 控制结果" 拼接各链路已有文本；LLM 不可用或输出 JSON 时用它。

`_chain_texts` 把 `chain_results` 里的 chat/knowledge/report/control 转成 `[情感/闲聊] xxx\n[知识问答] xxx` 文本；`_tool_summary` 把 tool\_results 转成 `[成功] 调整客厅空调：数据：{...}`。

### 13.7 收尾节点：nodes/task\_execution.py



```
@log\_node\_run

async def task\_execution\_node(state: dict) -> dict:

&#x20;   """保存 assistant 对话；预留场景联动、定时任务与结果推送扩展点。"""

&#x20;   state = dict(state)

&#x20;   \# 场景联动：场景触发任务已在工具执行节点通过 trigger\_scene 完成

&#x20;   \# 定时任务：后续可基于 tasks 中的 time 字段注册 APScheduler 任务

&#x20;   \# 结果推送：由 API 层保存 assistant 回复并根据 avatar\_emotion 推送 WebSocket

&#x20;   return state
```

**占位节点**：实际收尾（保存 assistant 消息、WS 推送）在 API 层做。这里留三个扩展点注释（场景联动 / 定时任务 / 结果推送）—— 架构上 "节点层不管 IO 收尾"。



***

## 十四、规则引擎（rules/ 目录）

**为什么需要规则引擎**（面试题 D4 核心）：LLM 有延迟 / 成本 / 不可用风险；规则引擎确定性、零成本、可单测。项目里它干三件事：**意图识别兜底**（rules/intent.py）、**任务规划兜底**（rules/planning.py）、**公共别名表**（rules/common.py）。

### 14.1 common.py：别名表与工具函数



```
DEVICE\_TYPE\_ALIASES = {"空调": "air\_conditioner", "扫地机器人": "robot\_vacuum",

&#x20;                      "灯": "light", "门锁": "door\_lock", "摄像头": "camera", ...}

DEVICE\_LABELS = {"air\_conditioner": "空调", ...}    # 反向：内部类型 → 中文名（回复展示用）

ROOM\_ALIASES = {"主卧":"卧室", "次卧":"卧室", "浴室":"卫生间", "厕所":"卫生间", ...}

KNOWLEDGE\_QUERY\_KEYWORDS = \["规定","制度","规则","偏好","习惯","要求","几点下班",...]

COLOR\_MAP = {"红":"#FF4D4F", ...}                   # 灯光颜色词 → 色值

def find\_device\_type(text):   # 遍历别名表，命中返回内部类型

def find\_room(text):          # 遍历房间别名，返回标准房间名

def device\_label(t):          # 类型 → 中文名

def extract\_json(text):       # 从 LLM 输出抠 JSON（兼容 markdown 代码块）
```

**扩展方式**（面试题 D6）：新增设备 / 房间词 → 在别名表加一行即可被规则引擎命中。

### 14.2 intent.py：规则版意图识别（build\_rule\_intents）

**触发优先级**（从上往下，先到先得；`build_rule_intents(text, devices, has_clarification_answer)`——`has_clarification_answer=True` 表示这是澄清回答后的重新识别）：

1. **模糊生活场景 → 两级澄清（v2 核心）**：
   - 第一级 **方案确认**（clarity=0.55 触发中断）："感冒/发烧"→"需要我帮您调低空调温度、关上窗户、烧壶热水吗？"（选项仅含家庭**真实存在**的设备）；"冷"→调高空调+关窗帘；"睡觉"→关灯+睡眠模式+关窗帘；"吵"→关窗帘+降音量；"天黑"→开灯+关窗帘；"热"→调低空调+开窗帘+补水提醒；
   - **有澄清回答且含明确设备/操作词** → 返回 None 继续向下解析 → 走到设备控制分支**第二级：问哪个房间**（只有确认要操作某类设备才问房间）；
   - 有澄清回答但无具体设备（"都行"）→ 直接执行默认方案（防死循环）；
2. **澄清回答多选 → 多段解析（v2）**：`has_clarification_answer` 且文本含顿号/逗号时，按 `[、，,；;]` 拆分逐段匹配设备+属性，生成**多个控制意图**（如"调低空调温度、关上窗户、烧壶热水"→ 空调 24℃ + 窗帘关闭 + 热水器开启 3 个 intent）。放在设备查询分支**之前**，避免"温度"等指标词误判为查询；
3. "回家" → scene_trigger 回家模式；"出门/离家" → 关灯+关空调+关窗帘+锁门；
4. 时间/天气查询（v2）：`NON_CHAT_TRIGGERS` 新增"几点/几号/星期/天气/气温"等词；专用分支返回 `{"type":"device_query", "tool_name":"get_current_time"/"get_weather", ...}` 显式意图；
5. 报告触发词 → report 意图；
6. 知识查询关键词 → knowledge_query 意图；
7. 场景名匹配（回家/睡眠/离家/观影/会客/晨起模式）→ scene_trigger；
8. 查询动作词 / 问句 / 指标词 → device_query；
9. "有哪些设备 / 设备列表" → device_query 列设备；
10. **设备控制**（`find_device_type` 命中）→ `_parse_attributes` 解析属性 + 房间补全 + 明确度评分：
    - 房间+属性都有 → clarity 0.9；
    - 有房间无属性 → 0.55，问"想调整到什么状态"；
    - 无房间有属性 → 单房间 0.9 / 多房间 0.5（问"哪个房间"）；
    - 都无 → 0.5；
11. "调一下 / 设置一下"（没指明设备）→ clarification 意图（列设备选项）；
12. 都没命中 → 空 intents（普通闲聊）。

`_parse_attributes` 是**正则 + 关键词**解析器（面试题 D5），按设备类型分支：



* 空调：`(\d{1,2})\s*度` 抓温度；"调高 / 调低"→ 28/24；"制冷 / 制热 / 除湿 / 送风 / 睡眠"→ mode；"打开 / 关闭"→ power；

* 灯：`(\d{1,3})\s*%` 抓亮度；"调亮 / 调暗"→100/30；COLOR\_MAP 抓颜色；"开灯 / 关灯"→ power；

* 窗帘：拉开→100、拉上→0、一半→50；

* 音箱：音量正则、播放 / 静音；电视：音量 / 频道 / 开关；门锁：锁 / 解锁；扫地机：**停止 / 暂停 / 回充→idle，清扫→cleaning**（P1）；净化器 / 加湿器 / 热水器：开关 / 温度。

`looks_like_pure_chat(text)`（闲聊短路）：



```
def looks\_like\_pure\_chat(text):

&#x20;   if find\_device\_type(text) or find\_room(text): return False      # 提到设备/房间 → 不是闲聊

&#x20;   if any(k in text for k in KNOWLEDGE\_QUERY\_KEYWORDS): return False  # 提到知识词 → 不是

&#x20;   return not any(k in text for k in NON\_CHAT\_TRIGGERS)            # 无触发词 → 纯闲聊
```

`NON_CHAT_TRIGGERS` 是个大元组（打开 / 关闭 / 调整 / 查询 / 报告 / 感冒 / 好冷 / 回家… 约 80 个词）——**命中任一就值得走完整链路**。

`compute_active_chains(intents)`（链路计算）：



```
def compute\_active\_chains(intents):

&#x20;   chains = \[]

&#x20;   for item in intents or \[]:

&#x20;       t = item.get("type")

&#x20;       if t in ("emotional\_care","chat"):        chains.append("chat")

&#x20;       elif t == "knowledge\_query":              chains.append("knowledge")

&#x20;       elif t in ("device\_control","device\_query","scene\_trigger"): chains.append("control")

&#x20;       elif t == "report":                       chains.append("report")

&#x20;   if not chains: chains = \["chat"]              # 兜底：至少走聊天

&#x20;   return chains
```

### 14.3 planning.py：规则版任务规划与回复

`build_rule_tasks(intents, permission_mode)`：把意图转任务（结构与 LLM 版一致）：



* device\_control → set\_device\_state（risk：door\_lock=medium 否则 low）；

* scene\_trigger → trigger\_scene（risk medium）；

* device\_query → get\_device\_state /list\_room\_devices（risk low，不需审批）。



```
&#x20;   needs\_approval = any(task.get("needs\_approval") for task in tasks)

&#x20;   risk\_level = "medium" if control\_count > 1 or needs\_approval else "low"

&#x20;   for task in tasks:

&#x20;       if task.get("risk\_level") == "low":

&#x20;           task\["risk\_level"] = risk\_level        # ★P10 已知项：会把查询任务也升 medium
```

**P10 的由来**：最后这段把 "低风险" 任务统一升级为整体 risk\_level——control\_count>1 或需审批时，查询类任务也被标 medium（低严重度已知缺陷，可讲）。

`build_rule_response(state)`：规则版最终回复 —— 知识查询先答知识；有工具结果按成功 / 失败 / 跳过逐条汇报；情感关怀给关怀话术；否则提示用户。

`build_rule_avatar_emotion(state)`：虚拟形象动作决策树 —— 情感→caring；安防词 / 安防异常→security；执行失败→sad；场景名→sleeping/energy\_saving/controlling；成功控制→security/controlling；查询→working；知识→neutral；默认 idle。



***

## 十五、LLM 工厂：llm/factory.py（模型怎么选、怎么降级）



```
\_current\_provider: contextvars.ContextVar   # 当前请求选的 provider（按 asyncio 上下文隔离）

\_current\_model: contextvars.ContextVar     # 当前请求选的 model

def set\_llm\_choice(provider, model):       # API 层注入

&#x20;   \_current\_provider.set(...); \_current\_model.set(...)

def get\_llm\_client(provider=None, model=None):

&#x20;   if provider: p = provider.lower(); m = model or settings 里的默认

&#x20;   else: p, m = \_resolve\_choice()          # contextvar → 全局配置 → 供应商默认模型

&#x20;   if p not in SUPPORTED\_PROVIDERS or not \_provider\_api\_key(p):

&#x20;       raise RuntimeError(f"LLM 供应商未配置 API Key")  # ★无 Key 直接抛错（v2 已删 Mock）

&#x20;   try:

&#x20;       return \_build\_client(p, m)          # qwen/deepseek/zhipu/ollama 对应 Client

&#x20;   except Exception:

&#x20;       raise RuntimeError(f"LLM 客户端构建失败")  # 构建失败直接抛错（v2 已删 Mock）
```

**三级模型决策**（面试题 D18 的 "LLM 不可用兜底" 依据）：



1. 请求上下文（前端选的 provider/model，contextvar 隔离防并发串扰）；

2. 全局配置 settings.llm\_provider/llm\_model；

3. 供应商默认模型表 PROVIDER\_DEFAULT\_MODELS。

**降级条件（v2 已删 Mock）**：provider 不在支持列表 / 没有对应 API Key / 客户端构建失败 → **直接抛 RuntimeError**，由节点层 try/except 回退规则引擎（build_rule_intents / build_rule_tasks / build_rule_response 等）。**不存在 Mock 客户端**——兜底输出全部基于真实设备数据。



***

## 十六、真实数据演示（三个完整 demo）

> 以下演示基于演示数据库（家庭 1：用户名 demo/owner，含客厅、卧室等房间与全套设备），普通模式（permission_mode=normal）。state 用缩略 JSON 展示关键字段变化。

### Demo 1：普通模式 "把客厅空调调到 26 度"（完整链路 + 审批中断 + 恢复）

**第 1 步：API 构造初始 state**（HTTP POST /api/agent/chat）



```
{

&#x20; "user\_input": "把客厅空调调到26度",

&#x20; "user\_id": 1, "user\_role": "owner", "family\_id": 1,

&#x20; "session\_id": "session\_abc", "thread\_id": "thread\_session\_abc",

&#x20; "permission\_mode": "normal", "provider": "qwen", "model": "qwen-plus",

&#x20; "house\_status": {}, "messages": \[{"role":"user","content":"把客厅空调调到26度"}],

&#x20; "intents": \[], "tasks": \[], "chain\_results": {}, "final\_response": null, ...

}
```

**第 2 步：intent\_recognition\_node**



* `looks_like_pure_chat` → "空调" 命中设备别名 → False（不是闲聊）。

* 加载家庭上下文：rooms=\[客厅，卧室，...]，devices=\[{客厅，air\_conditioner},...]。

* LLM 通道（或规则回退）返回：



```
"intents": \[{"type":"device\_control","description":"调整客厅空调温度","clarity":0.9,

&#x20;            "room\_name":"客厅","device\_type":"air\_conditioner",

&#x20;            "attributes":{"temperature":26,"power":"on"}}],

"intent\_clarity\_score": 0.9, "needs\_clarification": false
```



* `compute_active_chains` → `["control"]`。

**第 3 步：route\_after\_intent 路由**



* needs\_clarification=false；chains=\["control"] 需要全屋状态且 house\_status 为空 → **先去 house\_status\_retrieval\_node**。

* house\_status 补齐后 `route_after_house_status` → `["task_planning"]`。

**第 4 步：task\_planning\_node**



* LLM 规划（或规则 build\_rule\_tasks）：



```
"tasks": \[{"task\_id":"task\_1","intent\_type":"device\_control","tool\_name":"set\_device\_state",

&#x20;          "arguments":{"room\_name":"客厅","device\_type":"air\_conditioner",

&#x20;                       "attributes":{"temperature":26,"power":"on"}},

&#x20;          "needs\_approval":true,"risk\_level":"low","priority":"high",

&#x20;          "description":"调整客厅空调","expected\_effect":"客厅空调：电源开启，温度设为 26 度",

&#x20;          "status":"pending"}]
```



* 房间已指定 → 不触发澄清；`needs_approval=True`。

* `route_after_plan` → `approval`。

**第 5 步：approval\_node（中断！）**



* permission\_mode=normal 且有需审批任务 → `wait_user(state, payload)`：



```
{"type":"approval","tasks":\[{"task\_id":"task\_1","description":"调整客厅空调",

&#x20; "expected\_effect":"客厅空调：电源开启，温度设为 26 度","risk\_level":"low"}],

&#x20;"risk\_level":"low","thread\_id":"thread\_session\_abc"}
```



* LangGraph：抛 `__interrupt__`；API 层 `_normalize_interrupt` → 响应：



```
{"response": null, "thread\_id": "thread\_session\_abc",

&#x20;"interrupt": {"type":"approval","tasks":\[...],"risk\_level":"low","thread\_id":"thread\_session\_abc"}}
```



* 前端弹审批面板（默认勾选 task\_1）→ 用户点 "确认"。

**第 6 步：POST /api/agent/resume（恢复）**



* 请求体：`{"thread_id":"thread_session_abc","resume_data":{"approved":true,"task_ids":["task_1"]}}`

* LangGraph `Command(resume={...})` 从断点继续 → approval\_node 读到决策：


  * approved=true，task\_1 命中 → status="approved"。

* `route_after_approval` → `tool_execution`。

**第 7 步：tool\_execution\_node → \_tool\_set\_device\_state**



* `_require_control_permission("owner")` → 通过（owner 可控制）。

* air\_conditioner 可控；attributes 已有 power=on。

* `get_room_by_name("客厅", 1)` → room(id=1)。

* `get_device_by_room_and_type(1, "air_conditioner", 1)` → device (id=5, 客厅空调)。

* `update_device_status(...)` 写库：status JSON 变为 `{"power":"on","temperature":26,"mode":"cool",...}`，并写 device\_operation\_logs（source="agent"）。

* `broadcast_device_update` 推 WS：`{"type":"device_status_update","device_id":5,"family_id":1,...,"status":{...}}` → 前端卡片实时变 26 度。

* 返回 `{"success":true,"message":"已将客厅的客厅空调更新为: temperature=26, power=on",...}`。

**第 8 步：result\_aggregation\_node**



* tool\_results=\[{status:"success",...}] → success\_count=1, failure\_count=0, skipped\_count=0。

**第 9 步：response\_generation\_node**



* LLM 生成：`"好的，已为您将客厅空调温度调至 26 度，空调已自动开启。还有什么需要帮忙的吗？"`

* avatar\_emotion → "controlling"。

**第 10 步：task\_execution\_node（占位）→ API 收尾**



* `_save_agent_result` 写 assistant 消息到 conversations 表。

* HTTP 响应：`{"response":"好的，已为您将客厅空调温度调至 26 度...","avatar_emotion":"controlling","interrupt":null}`。



***

### Demo 2："我有点冷"（两级澄清 + 多链路并发 + 审批恢复）

**完整交互（deepseek LLM 路径，真实链路）**：

```
第1轮 POST /api/agent/chat   {"message": "我有点冷"}
  → intent: emotional_care + device_control → 澄清（方案确认）
  → interrupt: {"type":"clarification",
      "question":"需要我帮您调高客厅或卧室空调温度、关闭窗户、拉上客厅窗帘，或开启厨房热水器烧点热水吗？",
      "options":["调高客厅空调温度","调高卧室空调温度","关闭客厅窗户","拉上客厅窗帘","开启厨房热水器烧热水","都不用，谢谢"]}

第2轮 POST /api/agent/resume {"resume_data":{"answer":"调高空调温度"}}
  → 重识别：明确要调空调 → 设备控制分支 → 房间歧义（空调在客厅+卧室）
  → interrupt: {"type":"clarification",
      "question":"您想调高哪个房间的空调温度呢？",
      "options":["客厅空调","卧室空调"]}        ← 第二级：只问房间

第3轮 POST /api/agent/resume {"resume_data":{"answer":"卧室"}}
  → 规划：卧室空调调高 → 普通模式审批
  → interrupt: {"type":"approval","tasks":[{...卧室空调 temperature:28, mode:heat...}]}

第4轮 POST /api/agent/resume {"resume_data":{"approved":true,"task_ids":["task_1"]}}
  → 工具执行 → 真实写库 + 广播
  → response: "好的，卧室空调已经调到 28 度制热了。现在外面才 12℃，注意别着凉……"
```

**多选变体（v2）**：第 2 轮如果多选 `{"answer":"调高卧室空调温度、开启厨房热水器烧热水"}`，规则引擎多段解析 → **2 个任务**同时进入审批（task_1 卧室空调 27℃/heat、task_2 厨房热水器开启），审批通过后一并执行。**前端澄清面板支持多选**：选项按钮可切换选中/取消，选中项以顿号合并进回答。

**规则路径（qwen 无 Key 降级）等价**："我感冒了" → 方案确认"听到您身体不适，需要我帮您调低空调温度、关上窗户、烧壶热水吗？" → 答"调低空调吧" → "请问您想调整哪个房间的空调？当前有：1.客厅、2.卧室" → 答"卧室" → 执行。
### Demo 3：纯闲聊 "你好呀"

**第 1 步**：初始 state。

**第 2 步：intent\_recognition\_node**



* `looks_like_pure_chat("你好呀")` → 无设备 / 房间词、无知识词、无触发词 → True → **快速路径**：



```
"intents":\[{"type":"chat","description":"日常聊天或情感陪伴","clarity":1.0}],

"active\_chains":\["chat"]
```



* **不查库、不调 LLM**（省一次模型调用）。

**第 3 步**：路由 → chat\_generation\_node → LLM 回复 `"你好呀！今天过得怎么样？需要我帮忙调整家里的设备，或者聊聊天气吗？"` → chain\_results\["chat"]。

**第 4 步：response\_generation\_node**：active 只有 chat → **直接透传**聊天文本（不再调 LLM）→ final\_response = "你好呀！今天过得怎么样？..."

**全程 4 个节点、零数据库查询**—— 这就是 "纯闲聊快速识别" 的价值。



***

### Demo 4：知识查询 "空调温度有什么规定吗"

**第 1 步**：初始 state。

**第 2 步：intent\_recognition\_node**



* 命中 KNOWLEDGE\_QUERY\_KEYWORDS 的 "规定"→ 非闲聊。

* LLM 或规则 → `intents=[{"type":"knowledge_query","clarity":0.9}]`，`active_chains=["knowledge"]`。

**第 3 步**：路由 → rag\_retrieval\_node（need\_retrieval=True）



* `retrieve_relevant_docs(query="空调温度有什么规定吗", user_id=1, family_id=1, top_k=3)` → 双集合检索（user\_documents + family\_regulations）。

* 命中《家庭用电节能公约》：`"空调温度建议设置不低于26度"`（score 0.87）→



```
"rag\_context": "\[家庭用电节能公约] 空调温度建议设置不低于26度",

"rag\_sources": \[{"source":"家庭用电节能公约","collection":"family\_regulations","score":0.87,...}],

"is\_knowledge\_query": true
```

**第 4 步**：rag\_answer\_node → `"根据《家庭用电节能公约》：空调温度建议设置不低于26度。"`

**第 5 步**：response → 直接使用知识回答（标注来源）。



***

### Demo 5：报告链路 "生成一份家庭情况报告"

**第 1 步**：意图识别 → `intents=[{"type":"report","clarity":0.9}]`，`active_chains=["report"]`。

**第 2 步**：路由 → report\_generation\_node：



* house\_status 为空 → 内部调 house\_status\_retrieval\_node 补齐（全屋 20+ 设备状态、环境、时间季节）；

* rag\_context 为空 → 内部调 rag\_retrieval\_node（need\_retrieval 因 "report" in intent\_types = True，**P4 保证报告走 RAG**）；

* LLM 生成四段式报告：



```
【家庭情况报告】

① 环境概览：当前时间 2026-09-11 20:30 星期五，秋季，晚上。室内温度 26℃，湿度 45%，空气质量 优；室外 24℃，多云。

② 设备与房间状态：客厅空调（运行中，26℃ 制冷）；卧室灯（关闭）；扫地机器人（待命，电量 78%）...

③ 异常或建议：卧室门锁未上锁，建议开启离家模式自动锁门；依据《家庭用电节能公约》，空调建议不低于 26℃，当前设置符合。

④ 结语：如需进一步操作，随时告诉我。
```

**第 3 步**：chain\_results \["report"] → response 直接采用报告内容 → avatar\_emotion="working"。



***

## 十七、跳转关系总表（背下来就能讲清楚 "如何跳转"）



| 当前节点                     | 条件                          | 下一节点                     |
| ------------------------ | --------------------------- | ------------------------ |
| intent\_recognition      | needs\_clarification=true   | clarification            |
| intent\_recognition      | 需要全屋状态（control/report）且无    | house\_status\_retrieval |
| intent\_recognition      | 否则                          | 各链路入口（列表 = 并发）           |
| house\_status\_retrieval | 恒                           | 各链路入口（列表 = 并发）           |
| clarification            | 回答后 clarify\_source=plan    | task\_planning           |
| clarification            | 回答后 clarify\_source=intent  | intent\_recognition      |
| clarification            | 超 2 次 / 已有 final\_response  | END                      |
| chat\_generation         | 恒                           | result\_aggregation      |
| rag\_retrieval           | 恒                           | rag\_answer              |
| rag\_answer              | 恒                           | result\_aggregation      |
| report\_generation       | 恒                           | result\_aggregation      |
| task\_planning           | needs\_clarification=true   | clarification            |
| task\_planning           | 否则                          | approval                 |
| approval                 | approval\_granted=true      | tool\_execution          |
| approval                 | approval\_granted=false（取消） | result\_aggregation      |
| tool\_execution          | 恒                           | result\_aggregation      |
| result\_aggregation      | 恒                           | response\_generation     |
| response\_generation     | 恒                           | task\_execution          |
| task\_execution          | 恒                           | END                      |

**并发说明**：intent 后如果激活多条链路，除 control 外（chat/knowledge/report）并发执行；control 链路单独顺序走（因可能中断审批/澄清）。LangGraph 版靠条件路由返回"节点名列表"实现并发扇出。

**一句话总结整个 Agent**：`输入 → 意图识别（规则+LLM）→ [澄清] → 全屋状态（懒加载）→ 多链路并发（闲聊/知识/报告） + 设备链路（规划→审批→执行）→ 汇总 → 生成回复 → 收尾保存`。每一层都有规则兜底，每一步都不让异常中断主流程。