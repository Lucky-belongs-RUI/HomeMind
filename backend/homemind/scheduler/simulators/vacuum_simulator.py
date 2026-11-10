import random

from homemind.repositories import unit_of_work
from homemind.services.device_service import update_device_status
from homemind.websocket.manager import broadcast_device_update


def _battery(value) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 100


async def simulate_vacuum():
    """模拟扫地机器人：清扫耗电、电量耗尽自动回充、充满后待机。

    先在一个会话内读出待处理的机器人快照并立即释放连接，
    再逐个更新——避免改造前"读会话未关就开新写会话"的嵌套连接。
    """
    async with unit_of_work() as uow:
        vacuums = await uow.devices.list_by_type("robot_vacuum")
        targets = [
            (vacuum.id, vacuum.family_id, vacuum.room_id, dict(vacuum.status or {}))
            for vacuum in vacuums
        ]

    for device_id, family_id, room_id, status in targets:
        mode = status.get("status")
        battery = _battery(status.get("battery"))
        attributes = None

        if status.get("power") == "on" and mode == "cleaning":
            position = status.get("position") or {"x": 0, "y": 0}
            remaining = max(0, battery - random.randint(1, 3))
            attributes = {
                "battery": remaining,
                "position": {
                    "x": round(float(position.get("x", 0)) + random.uniform(-0.5, 0.5), 2),
                    "y": round(float(position.get("y", 0)) + random.uniform(-0.5, 0.5), 2),
                },
            }
            if remaining == 0:
                # 电量耗尽：回充而不是永远停在 0% 的“清扫中”
                attributes["status"] = "charging"
        elif mode == "charging":
            if battery >= 100:
                attributes = {"battery": 100, "status": "idle", "power": "off"}
            else:
                attributes = {"battery": min(100, battery + random.randint(2, 4))}

        if not attributes:
            continue

        updated = await update_device_status(
            device_id=device_id,
            attributes=attributes,
            user_id=0,
            source="scheduler",
            family_id=family_id,
        )
        await broadcast_device_update(
            {
                "type": "device_status_update",
                "device_id": device_id,
                "family_id": family_id,
                "room_id": room_id,
                "device_type": "robot_vacuum",
                "status": updated.status,
            }
        )
