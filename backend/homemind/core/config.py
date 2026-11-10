import logging
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mysql_url: str = "mysql+aiomysql://root:root@localhost:3306/smart_home"

    # LLM 配置（默认使用 Qwen）
    llm_provider: str = "qwen"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    # LLM 适配引擎：legacy = 原有自研客户端；langchain = LangChain ChatModel
    llm_engine: str = "legacy"

    # ===== Agent 运行时（LangChain + LangGraph）=====
    # 唯一在线链路：/api/agent/v2/* 与 /api/agent/ws
    # 路由用的便宜模型；留空则沿用当前 provider/model
    agent_router_model: str = ""
    # 最终回复用的模型；留空则沿用当前 provider/model
    agent_chat_model: str = ""
    # 可选的降级模型供应商（逗号分隔），例如 "deepseek,qwen"
    agent_fallback_providers: str = ""
    agent_llm_timeout_seconds: float = 30.0
    agent_tool_timeout_seconds: float = 20.0
    agent_max_reflections: int = 2
    agent_max_clarifications: int = 2
    # 一次规划最多拆出的子任务数，防止模型把一句话拆成过多并行分支
    agent_max_plan_tasks: int = 4
    # 会话历史注入的 token 预算（字符近似；超预算时做两级压缩，最近 6 轮原文保留）
    agent_context_token_budget: int = 2000
    # 生成内容显式标识（合规要求）
    agent_ai_label: bool = True

    # Qwen
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-flash"

    # 质谱 GLM
    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_model: str = "glm-4"

    # 本地 Ollama（OpenAI 兼容接口）
    ollama_api_key: str = "ollama"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:7b"

    # 向量库
    chroma_path: str = "./chroma_data"
    # 阿里云 DashScope 文本向量化（RAG 强制使用，禁止本地降级）
    embedding_model: str = "text-embedding-v2"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embed_batch_size: int = 10

    # 文件上传
    upload_dir: str = "./uploads"
    max_file_size: int = 10 * 1024 * 1024
    # 语音上传上限（与文档上传分开：音频体积更大，但同样必须设上限）
    max_audio_size: int = 25 * 1024 * 1024

    # LangGraph 持久化：Postgres checkpointer（中断态）+ Postgres Store（长期记忆）
    # 与业务库 MySQL 相互独立；LangGraph 官方无 MySQL 版 checkpointer。
    postgres_url: str = "postgresql://langgraph:langgraph@localhost:5432/langgraph"
    langgraph_persistence_enabled: bool = True
    langgraph_pool_max_size: int = 10

    # 语音
    whisper_model: str = "base"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"

    # WebSocket
    ws_heartbeat_interval: int = 30

    # JWT 认证
    jwt_secret: str = "smart-home-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    # 个人模型 API Key 的加密密钥；留空时回退到 JWT_SECRET
    model_config_secret: str = ""

    # 运行环境：development / production
    # production 下启用启动期安全校验（JWT 密钥仍为默认值时拒绝启动）
    app_env: str = "development"

    # CORS 允许来源（逗号分隔）；生产环境必须配置为真实前端域名
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"

    # 是否信任反向代理写入的 X-Forwarded-For
    # 只在部署于可信反向代理（Nginx 等）之后时开启；直连暴露时必须为 false，
    # 否则客户端可伪造该头绕过 IP 限流。
    trust_proxy_headers: bool = False

    # 启动选项
    enable_scheduler: bool = True

    # 可观测性：LangSmith 追踪（默认关闭）
    # 开启需要同时配置 langsmith_api_key，详见 _export_tracing_env()
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "smart-home-agent"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # ===== 派生属性（非配置字段，不参与环境变量解析）=====

    @property
    def cors_origin_list(self) -> list[str]:
        """把逗号分隔的 CORS 来源配置解析为列表。"""
        return [item.strip() for item in (self.cors_origins or "").split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return (self.app_env or "").strip().lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def _export_tracing_env() -> None:
    """把 LangSmith 追踪配置写入进程环境变量。

    为什么必须在这里做、而不是在 lifespan 里：langgraph / langchain 读取的是
    `os.environ`，而 `.env` 只会被 pydantic-settings 解析进 Settings 对象、
    **不会**进入环境变量。而 langchain 在导入时就可能缓存追踪开关，
    所以必须赶在它被导入之前写入。

    `config` 是几乎每个模块最先导入的模块，因此这里是唯一可靠的时机。
    """
    if not settings.langsmith_tracing:
        return
    if not settings.langsmith_api_key:
        logging.getLogger(__name__).warning(
            "已开启 LangSmith 追踪但未配置 LANGSMITH_API_KEY，追踪未生效"
        )
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint


_export_tracing_env()
