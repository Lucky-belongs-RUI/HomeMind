from sqlalchemy import select

from app.database import get_db_session
from app.models.device import Device, DeviceOperationLog


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
    async with get_db_session() as db:
        device = await db.get(Device, device_id)
        if not device:
            raise ValueError(f"设备不存在: {device_id}")
        if family_id is not None and device.family_id != family_id:
            raise PermissionError(f"设备不属于家庭 {family_id}，无权操作")

        before = dict(device.status or {})
        after = {**before, **attributes}
        device.status = after

        db.add(
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
        await db.commit()
        await db.refresh(device)
        return device


async def get_device(device_id: int, family_id: int = None) -> Device | None:
    """查询单个设备；传入 family_id 时校验归属。"""
    async with get_db_session() as db:
        conditions = [Device.id == device_id, Device.is_active == 1]
        if family_id is not None:
            conditions.append(Device.family_id == family_id)
        result = await db.execute(select(Device).where(*conditions))
        return result.scalar_one_or_none()


async def get_device_by_room_and_type(
    room_id: int, device_type: str, family_id: int = None
) -> Device | None:
    async with get_db_session() as db:
        conditions = [Device.room_id == room_id, Device.type == device_type, Device.is_active == 1]
        if family_id is not None:
            conditions.append(Device.family_id == family_id)
        result = await db.execute(select(Device).where(*conditions))
        return result.scalar_one_or_none()


async def list_devices_by_room(room_id: int, family_id: int = None) -> list[Device]:
    async with get_db_session() as db:
        conditions = [Device.room_id == room_id, Device.is_active == 1]
        if family_id is not None:
            conditions.append(Device.family_id == family_id)
        result = await db.execute(select(Device).where(*conditions))
        return list(result.scalars().all())


async def list_devices_by_family(family_id: int) -> list[Device]:
    async with get_db_session() as db:
        result = await db.execute(
            select(Device).where(Device.family_id == family_id, Device.is_active == 1)
        )
        return list(result.scalars().all())


async def list_devices_by_type(device_type: str, family_id: int = None) -> list[Device]:
    async with get_db_session() as db:
        conditions = [Device.type == device_type, Device.is_active == 1]
        if family_id is not None:
            conditions.append(Device.family_id == family_id)
        result = await db.execute(select(Device).where(*conditions))
        return list(result.scalars().all())


async def create_device(data: dict, family_id: int) -> Device:
    async with get_db_session() as db:
        device = Device(
            family_id=family_id,
            name=data["name"],
            type=data["type"],
            room_id=data["room_id"],
            brand=data.get("brand"),
            model=data.get("model"),
            status=_default_status(data["type"]),
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)
        return device


async def update_device_info(device_id: int, data: dict, family_id: int) -> Device:
    async with get_db_session() as db:
        device = await db.get(Device, device_id)
        if not device or device.family_id != family_id:
            raise ValueError("设备不存在")
        for key in ("name", "type", "room_id", "brand", "model"):
            if key in data:
                setattr(device, key, data[key])
        await db.commit()
        await db.refresh(device)
        return device


async def delete_device(device_id: int, family_id: int, user_id: int = None) -> dict:
    async with get_db_session() as db:
        device = await db.get(Device, device_id)
        if not device or device.family_id != family_id:
            raise ValueError("设备不存在")
        device.is_active = False
        db.add(
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
        await db.commit()
        return {"success": True}


async def get_device_logs(device_id: int, family_id: int) -> list[DeviceOperationLog]:
    async with get_db_session() as db:
        result = await db.execute(
            select(DeviceOperationLog)
            .where(
                DeviceOperationLog.device_id == device_id,
                DeviceOperationLog.family_id == family_id,
            )
            .order_by(DeviceOperationLog.created_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())


def _default_status(device_type: str) -> dict:
    defaults = {
        "air_conditioner": {"power": "off", "temperature": 26, "mode": "cool", "fan_speed": "auto", "swing": False},
        "light": {"power": "off", "brightness": 80, "color": "#FFFFFF", "mode": "normal"},
        "robot_vacuum": {"power": "off", "battery": 100, "position": {"x": 0, "y": 0}, "cleaning_mode": "auto", "status": "idle", "dust_bin": 0},
        "curtain": {"power": "off", "position": 0, "mode": "manual"},
        "speaker": {"power": "off", "volume": 30, "playing": False, "source": "local"},
        "tv": {"power": "off", "volume": 20, "channel": 1, "input_source": "hdmi1"},
        "air_purifier": {"power": "off", "mode": "auto", "fan_speed": "auto", "pm25": 35, "filter_life": 80},
        "humidifier": {"power": "off", "mode": "auto", "target_humidity": 55, "water_level": 80},
        "water_heater": {"power": "off", "temperature": 45, "mode": "standard"},
        "washer": {"power": "off", "status": "idle", "mode": "standard", "water_temp": "cold"},
        "fridge": {"power": "on", "temperature": 4, "freezer_temperature": -18, "mode": "smart"},
        "door_lock": {"power": "on", "locked": True, "battery": 100, "auto_lock": True},
        "camera": {"power": "on", "recording": False, "motion_detection": True, "night_vision": False},
    }
    defaults.update({
        "air_monitor": {"power": "on", "pm25": 35, "pm10": 58, "co2": 520, "hcho": 0.04, "tvoc": 0.2, "co": 1.0, "air_quality": "优", "battery": 90},
        "temp_humidity_sensor": {"online": True, "temperature": 26.0, "humidity": 55, "battery": 95},
        "outdoor_sensor": {"online": True, "temperature": 12.0, "humidity": 60},
        "weather_station": {"online": True, "weather": "晴", "temperature": 12.0, "humidity": 60, "uv_index": 3, "pressure": 1013, "pm25": 30, "air_quality": "优"},
        "electricity_meter": {"online": True, "power_w": 850, "voltage": 220, "current": 3.9, "daily_energy_kwh": 8.6, "monthly_energy_kwh": 210.4, "balance": 186.5},
        "smart_plug": {"power": "off", "power_w": 0, "energy_kwh": 12.3, "voltage": 220, "current": 0},
        "water_meter": {"online": True, "flow_rate": 1.2, "daily_usage": 0.35, "monthly_usage": 8.6, "balance": 32.5, "leak_alarm": False},
        "gas_meter": {"online": True, "flow_rate": 0.0, "monthly_usage": 12.8, "balance": 96.0, "gas_alarm": False},
        "door_window_sensor": {"online": True, "status": "closed", "battery": 90},
        "presence_sensor": {"online": True, "presence": False, "battery": 85},
        "leak_sensor": {"online": True, "leak": False, "battery": 80},
        "gas_sensor": {"online": True, "gas_leak": False, "battery": 80},
        "smoke_sensor": {"online": True, "smoke": False, "alarm": False, "battery": 85},
        "router": {"online": True, "internet_status": "online", "wifi_ssid": "SmartHome-5G", "signal_strength": 85, "device_count": 8, "bandwidth_mbps": 300},
    })
    return defaults.get(device_type, {"power": "off"})