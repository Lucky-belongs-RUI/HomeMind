"""用户模型配置的请求/响应模型。"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ModelProvider = Literal["qwen", "deepseek", "zhipu", "ollama"]


class ModelConfigCreate(BaseModel):
    """新增一个个人模型配置。"""

    name: str = Field(min_length=1, max_length=64, description="用户自定义名称")
    provider: ModelProvider
    model: str = Field(min_length=1, max_length=128)
    api_key: str | None = Field(default=None, max_length=1024)
    base_url: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_api_key(self):
        if self.provider != "ollama" and not (self.api_key or "").strip():
            raise ValueError("除本地 Ollama 外，API Key 不能为空")
        return self


class ModelConfigUpdate(BaseModel):
    """编辑模型配置；未传的字段保持不变，API Key 留空也保持不变。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    provider: ModelProvider | None = None
    model: str | None = Field(default=None, min_length=1, max_length=128)
    api_key: str | None = Field(default=None, max_length=1024)
    base_url: str | None = Field(default=None, max_length=255)


class ModelConfigItem(BaseModel):
    """模型配置列表项；只暴露是否配置 Key，不返回密文或明文。"""

    id: int
    name: str
    provider: str
    model: str
    base_url: str | None = None
    has_api_key: bool = False
    created_at: str | None = None
