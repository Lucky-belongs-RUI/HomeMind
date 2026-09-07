import random

from sqlalchemy import select

from app.database import get_db_session
from app.models.device import Device
from app.services.device_service import update_device_status
from app.websocket.manager import broadcast_device_update


async def simulate_vacuum():
    """模拟扫地机器人：清扫中电量下降、位置移动。"""
    async with get_db_session() as db:
        result = await db.execute(select(Device).where(Device.type == "robot_vacuum", Device.is_active == 1))
        vacuums = result.scalars().all()
        for vacuum in vacuums:
            status = vacuum.status or {}
            if status.get("power") != "on" or status.get("status") != "cleaning":
                continue
            position = status.get("position") or {"x": 0, "y": 0}
            attributes = {
                "battery": max(0, int(status.get("battery", 100)) - random.randint(1, 3)),
                "position": {
                    "x": round(float(position.get("x", 0)) + random.uniform(-0.5, 0.5), 2),
                    "y": round(float(position.get("y", 0)) + random.uniform(-0.5, 0.5), 2),
                },
            }
            updated = await update_device_status(
                device_id=vacuum.id,
                attributes=attributes,
                user_id=0,
                source="scheduler",
                family_id=vacuum.family_id,
            )
            await broadcast_device_update(
                {
                    "type": "device_status_update",
                    "device_id": vacuum.id,
                    "family_id": vacuum.family_id,
                    "room_id": vacuum.room_id,
                    "device_type": "robot_vacuum",
                    "status": updated.status,
                }
            )