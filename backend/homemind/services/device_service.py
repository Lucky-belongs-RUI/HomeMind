"""设备服务：状态更新、查询与操作日志。

SQL 已下沉到 DeviceRepository；本层只负责归属校验、状态合并与事务边界。
"""

from homemind.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from homemind.models.device import Device, DeviceOperationLog
from homemind.repositories import default_status, unit_of_work

# 可被主动控制的设备类型：其余类型（传感器/仪表）只读，
# 手工编辑只允许修改已有字段，避免把控制指令写进传感器状态。
CONTROLLABLE_TYPES = frozenset(
    {
        "air_conditioner",
        "light",
        "robot_vacuum",
        "curtain",
        "speaker",
        "tv",
        "air_purifier",
        "humidifier",
        "water_heater",
        "washer",
        "fridge",
        "door_lock",
        "camera",
    }
)


async def update_device_status(
    device_id: int,
    attributes: dict,
    user_id: int,
    source: str = "manual",
    family_id: int = None,
) -> Device:
    """更新设备状态、记录操作日志并返回设备。

    家庭隔离：传入 family_id 时校验设备归属，防止跨家庭操作。
    状态字段整体更新 ORM JSON，最终持久化到 MySQL。
    """
    async with unit_of_work() as uow:
        device = await uow.devices.get(device_id)
        if not device or not device.is_active:
            raise NotFoundError(f"设备不存在: {device_id}")
        if family_id is not None and device.family_id != family_id:
            raise PermissionDeniedError(f"设备不属于家庭 {family_id}，无权操作")

        before = dict(device.status or {})
        if device.type not in CONTROLLABLE_TYPES:
            # 传感器/仪表的已有字段仍可手工修正（环境数据编辑），但不接受新增控制属性
            unknown = [key for key in attributes if key not in before]
            if unknown:
                raise ValidationError(
                    f"设备类型 {device.type} 不支持控制属性: {', '.join(unknown)}"
                )
        after = {**before, **attributes}
        device.status = after

        await uow.devices.add_log(
            DeviceOperationLog(
                family_id=device.family_id,
                device_id=device.id,
                user_id=user_id,
                operation="update",
                source=source,
                before_status=before,
                after_status=after,
                description=f"更新属性: {list(attributes.keys())}",
            )
        )
        await uow.commit()
        await uow.refresh(device)
        return device


async def get_device(device_id: int, family_id: int = None) -> Device | None:
    """查询单个设备；传入 family_id 时校验归属。"""
    async with unit_of_work() as uow:
        return await uow.devices.find_active(device_id, family_id)


async def get_device_by_room_and_type(
    room_id: int, device_type: str, family_id: int = None
) -> Device | None:
    """按房间 + 设备类型定位设备。"""
    async with unit_of_work() as uow:
        return await uow.devices.find_by_room_and_type(room_id, device_type, family_id)


async def list_devices_by_room(room_id: int, family_id: int = None) -> list[Device]:
    """列出房间内设备。"""
    async with unit_of_work() as uow:
        return await uow.devices.list_by_room(room_id, family_id)


async def list_devices_by_family(family_id: int) -> list[Device]:
    """列出家庭内全部启用设备。"""
    async with unit_of_work() as uow:
        return await uow.devices.list_by_family(family_id)


async def list_devices_by_type(device_type: str, family_id: int = None) -> list[Device]:
    """按类型列出设备。"""
    async with unit_of_work() as uow:
        return await uow.devices.list_by_type(device_type, family_id)


async def create_device(data: dict, family_id: int) -> Device:
    """新建设备，状态取该类型的默认值。"""
    async with unit_of_work() as uow:
        room = await uow.rooms.find_active(data["room_id"], family_id)
        if not room:
            raise ValidationError("房间不存在或不属于当前家庭")
        device = Device(
            family_id=family_id,
            name=data["name"],
            type=data["type"],
            room_id=data["room_id"],
            brand=data.get("brand"),
            model=data.get("model"),
            status=default_status(data["type"]),
        )
        await uow.devices.add(device)
        await uow.commit()
        await uow.refresh(device)
        return device


async def update_device_info(device_id: int, data: dict, family_id: int) -> Device:
    """更新设备基础信息（不含 status，状态变更走 update_device_status）。"""
    async with unit_of_work() as uow:
        device = await uow.devices.find_active(device_id, family_id)
        if not device:
            raise NotFoundError("设备不存在")
        if "room_id" in data:
            room = await uow.rooms.find_active(data["room_id"], family_id)
            if not room:
                raise ValidationError("房间不存在或不属于当前家庭")
        for key in ("name", "type", "room_id", "brand", "model"):
            if key in data:
                setattr(device, key, data[key])
        await uow.commit()
        await uow.refresh(device)
        return device


async def delete_device(device_id: int, family_id: int, user_id: int = None) -> dict:
    """软删除设备并留操作日志。"""
    async with unit_of_work() as uow:
        device = await uow.devices.find_active(device_id, family_id)
        if not device:
            raise NotFoundError("设备不存在")
        device.is_active = False
        await uow.devices.add_log(
            DeviceOperationLog(
                family_id=device.family_id,
                device_id=device.id,
                user_id=user_id,
                operation="delete",
                source="manual",
                before_status=dict(device.status or {}),
                after_status=None,
                description="软删除设备",
            )
        )
        await uow.commit()
        return {"success": True}


async def get_device_logs(device_id: int, family_id: int) -> list[DeviceOperationLog]:
    """最近 100 条设备操作日志。"""
    async with unit_of_work() as uow:
        return await uow.devices.list_logs(device_id, family_id)
