"""HomeMind —— 智能家居大模型体验平台后端。

分层结构（依赖方向自上而下，不允许反向）：

    api/            HTTP / WebSocket 接口层：参数校验、鉴权依赖、响应模型
    agent/          Agent 编排层：LangGraph 运行时、规则引擎、设备工具
    services/       业务逻辑层：领域规则、事务边界
    repositories/   数据访问层：SQL 与 ORM 操作
    models/         ORM 模型
    schemas/        Pydantic 请求/响应模型
    core/           跨层基础设施：配置、数据库、异常体系、全局错误处理
    prompts.py      提示词集中管理（带版本号）
    llm/            LLM 供应商适配（Qwen / DeepSeek / Zhipu / Ollama）
    rag/            检索增强：分块、向量化、检索
    voice/          语音识别与合成
    websocket/      实时推送
    scheduler/      设备模拟调度

评测与测试（不在运行时代码内）：

    ../evals/       离线评测：数据集、指标、跑分脚本
    ../tests/       单元测试（零外部依赖）
"""
