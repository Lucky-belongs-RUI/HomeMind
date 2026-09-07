from typing import Optional

from pydantic import BaseModel


class UserUpdate(BaseModel):
    """更新用户资料请求。"""
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None