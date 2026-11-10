"""设备与设备操作日志的数据访问。"""

from __future__ import annotations

from sqlalchemy import delete, func, select, update

from homemind.models.device import Device, DeviceOperationLog
from homemind.repositories.base import BaseRepository

# 各设备类型的默认状态：新建设备时写入 status 字段
_DEFAULT_STATUS: dict[str, dict] = {
    "air_conditioner": {
        "power": "off",
        "temperature": 26,
        "mode": "cool",
        "fan_speed": "auto",
        "swing": False,
    },
    "light": {"power": "off", "brightness": 80, "color": "#FFFFFF", "mode": "normal"},
    "robot_vacuum": {
        "power": "off",
        "battery": 100,
        "position": {"x": 0, "y": 0},
        "cleaning_mode": "auto",
        "status": "idle",
        "dust_bin": 0,
    },
    "curtain": {"power": "off", "position": 0, "mode": "manual"},
    "speaker": {"power": "off", "volume": 30, "playing": False, "source": "local"},
    "tv": {"power": "off", "volume": 20, "channel": 1, "input_source": "hdmi1"},
    "air_purifier": {
        "power": "off",
        "mode": "auto",
        "fan_speed": "auto",
        "pm25": 35,
        "filter_life": 80,
    },
    "humidifier": {"power": "off", "mode": "auto", "target_humidity": 55, "water_level": 80},
    "water_heater": {"power": "off", "temperature": 45, "mode": "standard"},
    "washer": {"power": "off", "status": "idle", "mode": "standard", "water_temp": "cold"},
    "fridge": {"power": "on", "temperature": 4, "freezer_temperature": -18, "mode": "smart"},
    "door_lock": {"power": "on", "locked": True, "battery": 100, "auto_lock": True},
    "camera": {"power": "on", "recording": False, "motion_detection": True, "night_vision": False},
    "air_monitor": {
        "power": "on",
        "pm25": 35,
        "pm10": 58,
        "co2": 520,
        "hcho": 0.04,
        "tvoc": 0.2,
        "co": 1.0,
        "air_quality": "优",
        "battery": 90,
    },
    "temp_humidity_sensor": {"online": True, "temperature": 26.0, "humidity": 55, "battery": 95},
    "outdoor_sensor": {"online": True, "temperature": 12.0, "humidity": 60},
    "weather_station": {
        "online": True,
        "weather": "晴",
        "temperature": 12.0,
        "humidity": 60,
        "uv_index": 3,
        "pressure": 1013,
        "pm25": 30,
        "air_quality": "优",
    },
    "electricity_meter": {
        "online": True,
        "power_w": 850,
        "voltage": 220,
        "current": 3.9,
        "daily_energy_kwh": 8.6,
        "monthly_energy_kwh": 210.4,
        "balance": 186.5,
    },
    "smart_plug": {"power": "off", "power_w": 0, "energy_kwh": 12.3, "voltage": 220, "current": 0},
    "water_meter": {
        "online": True,
        "flow_rate": 1.2,
        "daily_usage": 0.35,
        "monthly_usage": 8.6,
        "balance": 32.5,
        "leak_alarm": False,
    },
    "gas_meter": {
        "online": True,
        "flow_rate": 0.0,
        "monthly_usage": 12.8,
        "balance": 96.0,
        "gas_alarm": False,
    },
    "door_window_sensor": {"online": True, "status": "closed", "battery": 90},
    "presence_sensor": {"online": True, "presence": False, "battery": 85},
    "leak_sensor": {"online": True, "leak": False, "battery": 80},
    "gas_sensor": {"online": True, "gas_leak": False, "battery": 80},
    "smoke_sensor": {"online": True, "smoke": False, "alarm": False, "battery": 85},
    "router": {
        "online": True,
        "internet_status": "online",
        "wifi_ssid": "SmartHome-5G",
        "signal_strength": 85,
        "device_count": 8,
        "bandwidth_mbps": 300,
    },
}


def default_status(device_type: str) -> dict:
    """返回某类设备的默认状态副本（未知类型退化为仅开关）。"""
    return dict(_DEFAULT_STATUS.get(device_type, {"power": "off"}))


class DeviceRepository(BaseRepository):
    """设备表与设备操作日志表的读写。"""

    async def get(self, device_id: int) -> Device | None:
        return await self.session.get(Device, device_id)

    async def find_active(self, device_id: int, family_id: int | None = None) -> Device | None:
        conditions = [Device.id == device_id, Device.is_active == 1]
        if family_id is not None:
            conditions.append(Device.family_id == family_id)
        result = await self.session.execute(select(Device).where(*conditions))
        return result.scalar_one_or_none()

    async def find_by_room_and_type(
        self, room_id: int, device_type: str, family_id: int | None = None
    ) -> Device | None:
        conditions = [Device.room_id == room_id, Device.type == device_type, Device.is_active == 1]
        if family_id is not None:
            conditions.append(Device.family_id == family_id)
        result = await self.session.execute(select(Device).where(*conditions))
        return result.scalar_one_or_none()

    async def list_by_room(self, room_id: int, family_id: int | None = None) -> list[Device]:
        conditions = [Device.room_id == room_id, Device.is_active == 1]
        if family_id is not None:
            conditions.append(Device.family_id == family_id)
        result = await self.session.execute(select(Device).where(*conditions))
        return list(result.scalars().all())

    async def list_by_family(self, family_id: int) -> list[Device]:
        result = await self.session.execute(
            select(Device).where(Device.family_id == family_id, Device.is_active == 1)
        )
        return list(result.scalars().all())

    async def list_by_type(self, device_type: str, family_id: int | None = None) -> list[Device]:
        conditions = [Device.type == device_type, Device.is_active == 1]
        if family_id is not None:
            conditions.append(Device.family_id == family_id)
        result = await self.session.execute(select(Device).where(*conditions))
        return list(result.scalars().all())

    async def count_by_family(self, family_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(Device.family_id == family_id, Device.is_active == 1)
            )
            or 0
        )

    async def add(self, device: Device) -> Device:
        self.session.add(device)
        await self.session.flush()
        return device

    async def add_log(self, log: DeviceOperationLog) -> DeviceOperationLog:
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_logs(
        self, device_id: int, family_id: int, limit: int = 100
    ) -> list[DeviceOperationLog]:
        result = await self.session.execute(
            select(DeviceOperationLog)
            .where(
                DeviceOperationLog.device_id == device_id,
                DeviceOperationLog.family_id == family_id,
            )
            .order_by(DeviceOperationLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def deactivate_by_family(self, family_id: int) -> None:
        """软删除家庭内全部设备（删除家庭时使用）。"""
        await self.session.execute(
            update(Device).where(Device.family_id == family_id).values(is_active=False)
        )

    async def purge_logs_by_family(self, family_id: int) -> None:
        await self.session.execute(
            delete(DeviceOperationLog).where(DeviceOperationLog.family_id == family_id)
        )
