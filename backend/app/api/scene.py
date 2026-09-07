"""场景接口：列表、创建、执行与删除（按家庭隔离）。"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_owner, require_owner_or_resident
from app.schemas.scene import SceneCreate, SceneUpdate
from app.services import scene_service

router = APIRouter(prefix="/scenes", tags=["场景"])


def _scene_dict(scene) -> dict:
    return {
        "id": scene.id,
        "family_id": scene.family_id,
        "name": scene.name,
        "description": scene.description,
        "actions": scene.actions,
    }


@router.get("")
async def list_scenes(current_user: dict = Depends(get_current_user)):
    """列出当前家庭所有场景。"""
    scenes = await scene_service.list_scenes_by_family(current_user["family_id"])
    return [_scene_dict(s) for s in scenes]


@router.post("")
async def create_scene(
    payload: SceneCreate,
    current_user: dict = Depends(require_owner),
):
    """房主创建场景。"""
    return _scene_dict(
        await scene_service.create_scene(payload.model_dump(), current_user["family_id"])
    )


@router.post("/{scene_name}/execute")
async def execute_scene(
    scene_name: str,
    current_user: dict = Depends(require_owner_or_resident),
):
    """执行场景（房主/住户可触发，访客仅可查看）。"""
    return await scene_service.execute_scene(
        scene_name=scene_name,
        family_id=current_user["family_id"],
        user_id=current_user["user_id"],
        source="manual",
    )


@router.put("/{scene_id}")
async def update_scene(
    scene_id: int,
    payload: SceneUpdate,
    current_user: dict = Depends(require_owner),
):
    """房主更新场景。"""
    try:
        scene = await scene_service.update_scene(
            scene_id, payload.model_dump(exclude_unset=True), current_user["family_id"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _scene_dict(scene)


@router.delete("/{scene_id}")
async def delete_scene(
    scene_id: int,
    current_user: dict = Depends(require_owner),
):
    """房主删除场景（软删除）。"""
    try:
        return await scene_service.delete_scene(scene_id, current_user["family_id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))