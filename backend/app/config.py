from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置：环境变量与 .env 文件均可覆盖（环境变量优先）。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库：默认连接本地 MySQL 8.0（smart_home 库由 database/init.sql 创建）
    mysql_url: str = "mysql+aiomysql://root:root@localhost:3306/smart_home"

    # LLM 配置（默认使用 Qwen）
    llm_provider: str = "qwen"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048

    # Qwen
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-pro"

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
    embedding_model: str = "text-embedding-v2"

    # 文件上传
    upload_dir: str = "./uploads"
    max_file_size: int = 10 * 1024 * 1024

    # 语音
    whisper_model: str = "base"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"

    # WebSocket
    ws_heartbeat_interval: int = 30

    # JWT 认证
    jwt_secret: str = "smart-home-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # 启动选项
    enable_scheduler: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
