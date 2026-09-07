from typing import Any, Dict, Optional

from pydantic import BaseModel


class SceneCreate(BaseModel):
    """创建场景请求，actions 格式为 {"actions": [...]}。"""
    name: str
    description: Optional[str] = None
    actions: Optional[Dict[str, Any]] = None


class SceneUpdate(BaseModel):
    """更新场景请求。"""
    name: Optional[str] = None
    description: Optional[str] = None
    actions: Optional[Dict[str, Any]] = None