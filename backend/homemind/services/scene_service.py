"""场景服务：场景 CRUD 与批量执行。

场景名模糊匹配（同义词、后缀归一化）是业务规则，保留在本层；
数据访问走 SceneRepository / DeviceRepository / RoomRepository。
"""

from homemind.core.exceptions import NotFoundError
from homemind.models.scene import Scene
from homemind.repositories import unit_of_work
from homemind.services.device_service import (
    get_device,
    get_device_by_room_and_type,
    update_device_status,
)
from homemind.services.room_service import get_room, get_room_by_name
from homemind.websocket.manager import broadcast_device_update

# 场景名同义词：用户口语与预设场景名的差异映射
SCENE_SYNONYMS = {
    "睡觉": "睡眠",
    "就寝": "睡眠",
    "出门": "离家",
    "离开": "离家",
    "起床": "晨起",
    "早上好": "晨起",
}


async def list_scenes_by_family(family_id: int) -> list[Scene]:
    """列出家庭内所有启用的场景。"""
    async with unit_of_work() as uow:
        return await uow.scenes.list_active(family_id)


async def get_scene_by_name(scene_name: str, family_id: int) -> Scene | None:
    """按名称在当前家庭内查找场景（家庭隔离）。

    匹配顺序：精确匹配 → 去掉“模式/场景”后缀匹配 → 包含匹配
    （“回家”能命中“回家模式”，避免 LLM 输出的场景名与预设场景不一致导致找不到）。
    """
    name = (scene_name or "").strip()
    if not name:
        return None
    async with unit_of_work() as uow:
        scene = await uow.scenes.find_active_by_name(name, family_id)
        if scene:
            return scene

        # 归一化：去掉“模式/场景”后缀后再精确匹配
        normalized = _normalize_scene_name(name)
        if normalized and normalized != name:
            scene = await uow.scenes.find_active_by_name(normalized, family_id)
            if scene:
                return scene

        # 包含匹配：输入包含场景名（回家 → 回家模式），或场景名包含输入词
        # 也支持反方向（用户原话“执行回家模式”包含已存在的“回家模式”），
        # 用于兼容模型把场景名翻译成英文、只能靠原话回查的情况。
        # 同义词归一化：睡觉/就寝 → 睡眠，出门/离开 → 离家
        synonym = SCENE_SYNONYMS.get(normalized) if normalized else None
        for candidate in await uow.scenes.list_active(family_id):
            candidate_name = candidate.name or ""
            candidate_normalized = _normalize_scene_name(candidate_name)
            candidate_synonym = SCENE_SYNONYMS.get(candidate_normalized)
            if (
                candidate_name == name
                or (name and name in candidate_name)
                or (normalized and normalized in candidate_name)
                or (candidate_name and candidate_name in name)
                or (candidate_normalized and candidate_normalized in name)
                or (candidate_normalized and candidate_normalized == normalized)
                or (synonym and candidate_normalized == synonym)
                or (candidate_synonym and candidate_synonym == normalized)
                or (candidate_synonym and synonym and candidate_synonym == synonym)
            ):
                return candidate
        return None


def _normalize_scene_name(name: str) -> str:
    """场景名归一化：去空白、去“模式/场景”后缀，便于模糊匹配。"""
    text = (name or "").strip()
    for suffix in ("模式", "场景"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
    return text


async def create_scene(data: dict, family_id: int) -> Scene:
    """创建场景，actions 采用文档约定的 {"actions": [...]} 结构。"""
    async with unit_of_work() as uow:
        scene = Scene(
            family_id=family_id,
            name=data["name"],
            description=data.get("description"),
            actions=data.get("actions") or {"actions": []},
        )
        await uow.scenes.add(scene)
        await uow.commit()
        await uow.refresh(scene)
        return scene


async def update_scene(scene_id: int, data: dict, family_id: int) -> Scene:
    """更新场景信息与动作列表。"""
    async with unit_of_work() as uow:
        scene = await uow.scenes.find_active(scene_id, family_id)
        if not scene:
            raise NotFoundError("场景不存在")
        for key in ("name", "description", "actions"):
            if key in data:
                setattr(scene, key, data[key])
        await uow.commit()
        await uow.refresh(scene)
        return scene


async def delete_scene(scene_id: int, family_id: int) -> dict:
    """软删除场景。"""
    async with unit_of_work() as uow:
        scene = await uow.scenes.find_active(scene_id, family_id)
        if not scene:
            raise NotFoundError("场景不存在")
        scene.is_active = False
        await uow.commit()
        return {"success": True}


async def execute_scene(
    scene_name: str,
    family_id: int,
    user_id: int,
    source: str = "agent",
) -> dict:
    """执行场景：按动作列表批量更新设备状态并广播 WebSocket。

    返回值区分三种结果：
    - 全部动作成功：success=True，failed_count=0
    - 部分动作失败：success=True，failed_count>0，message 说明失败明细（前端应告警）
    - 全部动作失败或场景无动作：success=False，error 说明原因

    每个动作独立提交：单个设备失败不影响已成功的动作（与改造前一致）。
    """
    scene = await get_scene_by_name(scene_name, family_id)
    if not scene:
        return {"success": False, "error": f"未找到场景: {scene_name}"}

    actions = (scene.actions or {}).get("actions", [])
    if not actions:
        return {"success": False, "error": f"场景「{scene.name}」没有可执行的动作"}

    results = []
    for action in actions:
        device_id = action.get("device_id")
        if device_id:
            # 新格式：按具体设备执行（设备与房间天然绑定）
            device = await get_device(int(device_id), family_id)
            if not device:
                results.append({"error": f"设备不存在: {device_id}"})
                continue
            room = await get_room(device.room_id, family_id)
            if not room:
                results.append({"error": f"设备所属房间不存在: {device.name}"})
                continue
        else:
            # 旧格式兼容：房间 + 设备类型定位设备
            room = await get_room_by_name(action.get("room_name", ""), family_id)
            if not room:
                results.append({"error": f"房间不存在: {action.get('room_name')}"})
                continue
            device = await get_device_by_room_and_type(
                room.id, action.get("device_type", ""), family_id
            )
            if not device:
                results.append(
                    {
                        "error": f"设备不存在: {action.get('device_type')} in {action.get('room_name')}"
                    }
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
                "room_id": device.room_id,
                "device_type": device.type,
                "status": updated.status,
            }
        )
        results.append({"success": True, "device": device.name})

    total = len(results)
    success_count = sum(1 for item in results if item.get("success"))
    failed_count = total - success_count
    failed_msgs = [item["error"] for item in results if item.get("error")]

    if success_count == 0:
        return {
            "success": False,
            "scene": scene.name,
            "results": results,
            "success_count": 0,
            "failed_count": failed_count,
            "error": f"场景「{scene.name}」全部动作执行失败：" + "；".join(failed_msgs),
        }

    response = {
        "success": True,
        "scene": scene.name,
        "results": results,
        "success_count": success_count,
        "failed_count": failed_count,
    }
    if failed_count:
        response["message"] = f"部分动作执行失败（成功 {success_count}/{total}）：" + "；".join(
            failed_msgs
        )
    return response
