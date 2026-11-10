from typing import Any

from pydantic import BaseModel, ConfigDict

# ============================================================
# 请求模型
# ============================================================


class SceneCreate(BaseModel):
    """创建场景请求，actions 格式为 {"actions": [...]}。"""

    name: str
    description: str | None = None
    actions: dict[str, Any] | None = None


class SceneUpdate(BaseModel):
    """更新场景请求。"""

    name: str | None = None
    description: str | None = None
    actions: dict[str, Any] | None = None


# ============================================================
# 响应模型
# ============================================================


class SceneItem(BaseModel):
    """场景信息（对应 api/scene.py 的 _scene_dict）。

    from_attributes=True：`/families/{id}/scenes` 直接返回 ORM 列表。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    name: str
    description: str | None = None
    actions: dict[str, Any] | None = None


class SceneExecutionResponse(BaseModel):
    """场景执行结果。

    服务层按三种结果返回不同字段，因此这里全部声明为可选：

    - 全部动作成功：success=True, failed_count=0
    - 部分动作失败：success=True, failed_count>0, 带 message 说明失败明细
    - 全部失败或无动作：success=False, 带 error 说明原因
    """

    success: bool
    scene: str | None = None
    results: list[dict[str, Any]] | None = None
    success_count: int | None = None
    failed_count: int | None = None
    message: str | None = None
    error: str | None = None
