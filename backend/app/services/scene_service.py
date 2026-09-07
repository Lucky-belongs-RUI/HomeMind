from sqlalchemy import select

from app.database import get_db_session
from app.models.scene import Scene


async def list_scenes_by_family(family_id: int) -> list[Scene]:
    """列出家庭内所有启用的场景。"""
    async with get_db_session() as db:
        result = await db.execute(
            select(Scene)
            .where(Scene.family_id == family_id, Scene.is_active == 1)
            .order_by(Scene.id)
        )
        return list(result.scalars().all())


async def get_scene_by_name(scene_name: str, family_id: int) -> Scene | None:
    """按名称在当前家庭内查找场景（家庭隔离）。"""
    async with get_db_session() as db:
        result = await db.execute(
            select(Scene).where(
                Scene.family_id == family_id,
                Scene.name == scene_name,
                Scene.is_active == 1,
            )
        )
        return result.scalar_one_or_none()


async def create_scene(data: dict, family_id: int) -> Scene:
    """创建场景，actions 采用文档约定的 {"actions": [...]} 结构。"""
    async with get_db_session() as db:
        scene = Scene(
            family_id=family_id,
            name=data["name"],
            description=data.get("description"),
            actions=data.get("actions") or {"actions": []},
        )
        db.add(scene)
        await db.commit()
        await db.refresh(scene)
        return scene


async def update_scene(scene_id: int, data: dict, family_id: int) -> Scene:
    """更新场景信息与动作列表。"""
    async with get_db_session() as db:
        scene = await db.get(Scene, scene_id)
        if not scene or scene.family_id != family_id:
            raise ValueError("场景不存在")
        for key in ("name", "description", "actions"):
            if key in data:
                setattr(scene, key, data[key])
        await db.commit()
        await db.refresh(scene)
        return scene


async def delete_scene(scene_id: int, family_id: int) -> dict:
    """软删除场景。"""
    async with get_db_session() as db:
        scene = await db.get(Scene, scene_id)
        if not scene or scene.family_id != family_id:
            raise ValueError("场景不存在")
        scene.is_active = False
        await db.commit()
        return {"success": True}


async def execute_scene(
    scene_name: str,
    family_id: int,
    user_id: int,
    source: str = "agent",
) -> dict:
    """执行场景：按动作列表批量更新设备状态并广播 WebSocket。"""
    from app.services.device_service import get_device_by_room_and_type, update_device_status
    from app.services.room_service import get_room_by_name
    from app.websocket.manager import broadcast_device_update

    scene = await get_scene_by_name(scene_name, family_id)
    if not scene:
        return {"success": False, "error": f"未找到场景: {scene_name}"}

    actions = (scene.actions or {}).get("actions", [])
    results = []
    for action in actions:
        room = await get_room_by_name(action.get("room_name", ""), family_id)
        if not room:
            results.append({"error": f"房间不存在: {action.get('room_name')}"})
            continue

        device = await get_device_by_room_and_type(
            room.id, action.get("device_type", ""), family_id
        )
        if not device:
            results.append(
                {"error": f"设备不存在: {action.get('device_type')} in {action.get('room_name')}"}
            )
            continue

        updated = await update_device_status(
            device_id=device.id,
            attributes=action.get("attributes", {}),
            user_id=user_id,
            source=source,
            family_id=family_id,
        )
        await broadcast_device_update(
            {
                "type": "device_status_update",
                "device_id": device.id,
                "family_id": device.family_id,
                "room_id": room.id,
                "device_type": device.type,
                "status": updated.status,
            }
        )
        results.append({"success": True, "device": device.name})

    return {"success": True, "scene": scene.name, "results": results}