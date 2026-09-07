from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """房主注册家庭请求。"""
    family_name: str
    username: str
    password: str = Field(min_length=6, description="密码最少 6 位")
    nickname: str
    description: Optional[str] = None


class LoginRequest(BaseModel):
    """登录请求。"""
    username: str
    password: str


class SubAccountCreate(BaseModel):
    """房主创建子账户（住户/访客）请求。"""
    username: str
    password: str = Field(min_length=6, description="密码最少 6 位")
    nickname: str
    role: str = Field(default="resident", pattern="^(resident|guest)$")


class ChangePasswordRequest(BaseModel):
    """修改密码请求。"""
    old_password: str
    new_password: str = Field(min_length=6, description="新密码最少 6 位")