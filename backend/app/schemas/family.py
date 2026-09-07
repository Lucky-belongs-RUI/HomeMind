from typing import Optional

from pydantic import BaseModel


class FamilyCreate(BaseModel):
    """创建家庭请求（已登录房主创建新家庭并生成新房主账户）。"""
    name: str
    owner_username: str
    owner_nickname: str
    description: Optional[str] = None


class FamilyUpdate(BaseModel):
    """更新家庭信息请求。"""
    name: Optional[str] = None
    description: Optional[str] = None