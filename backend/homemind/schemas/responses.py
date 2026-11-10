"""API 响应模型。

## 为什么需要它

原先 51 个路由里只有 1 个声明了 `response_model`，导致两个后果：

1. `/docs` 里所有响应结构都是空的 `{}`——接口文档实际上不可用；
2. 返回结构没有契约约束，改动返回字段时前端只能靠"跑起来试试"发现。

## 使用注意（重要）

FastAPI 会用 `response_model` **过滤**实际返回值：模型里没声明的字段会被丢掉。
因此这里的模型必须与实际返回结构严格一致，**少写一个字段就等于前端拿不到它**。
新增返回字段时，务必同步更新对应模型。

## 命名约定

- `XxxItem`：列表中的单个元素
- `XxxResponse`：某个接口的完整响应
- 通用壳（如 `SuccessResponse`）集中在文件末尾
"""

from typing import Any

from pydantic import BaseModel, Field

# ============================================================
# 认证
# ============================================================


class AuthUser(BaseModel):
    """登录/注册返回的用户信息。"""

    id: int
    username: str
    nickname: str
    role: str
    family_id: int


class FamilyBrief(BaseModel):
    """家庭简要信息。"""

    id: int
    name: str
    description: str | None = None


class AuthResponse(BaseModel):
    """登录 / 注册响应。"""

    token: str
    user: AuthUser
    family: FamilyBrief | None = None


class CurrentUserResponse(BaseModel):
    """`GET /auth/me` 响应。

    注意字段名是 `user_id`（而非 `id`）——与鉴权依赖返回的身份结构保持一致，
    这样前端可以把两者当作同一个对象处理。
    """

    user_id: int
    username: str
    role: str
    family_id: int


class SubAccountResponse(BaseModel):
    """房主创建子账户后的响应。"""

    id: int
    username: str
    nickname: str
    role: str


# ============================================================
# 通用
# ============================================================


class SuccessResponse(BaseModel):
    """只表示"操作成功"的简单响应。"""

    success: bool = True


class ErrorResponse(BaseModel):
    """统一错误响应结构（由 app/core/handlers.py 产出）。

    声明出来主要是为了让 OpenAPI 文档能展示错误格式，
    实际返回由全局异常处理器直接构造。
    """

    detail: str = Field(description="面向用户的错误说明")
    code: str = Field(description="稳定的机器可读错误码，前端按它分支")
    details: dict[str, Any] | None = Field(default=None, description="补充上下文，例如冲突的字段名")


class MessageListResponse(BaseModel):
    """会话历史响应。"""

    session_id: str
    messages: list[dict[str, Any]]


class ResetChatResponse(BaseModel):
    """重置会话响应。"""

    session_id: str
    deleted: int


class OpeningResponse(BaseModel):
    """开场白响应：已存在会话时 opening 为 None。"""

    session_id: str
    opening: str | None = None
