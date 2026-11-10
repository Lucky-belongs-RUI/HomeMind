from typing import Any

from pydantic import BaseModel

# ============================================================
# 请求模型
# ============================================================


class UserUpdate(BaseModel):
    """更新用户资料请求。"""

    nickname: str | None = None
    avatar_url: str | None = None


# ============================================================
# 响应模型
# ============================================================


class UserItem(BaseModel):
    """家庭成员资料（不含密码）。"""

    id: int
    username: str
    nickname: str
    role: str
    family_id: int
    avatar_url: str | None = None


class UserPreferencesResponse(BaseModel):
    """用户偏好画像。

    `preferences` 的键由模型根据对话内容自主决定（不套固定模板），
    因此这里只能是自由字典，无法进一步约束结构。
    """

    user_id: int
    preferences: dict[str, Any] = {}
