"""家庭环境指标聚合：供 AI 助理顶部中控指标展示。

指标严格绑定对应智能设备：
- 室内温度/湿度：温湿度传感器（temp_humidity_sensor）
- 室外温度：室外温湿度传感器（outdoor_sensor）或室外气象站（weather_station）
- 空气质量：多功能空气检测仪（air_monitor），兼容空气净化器 PM2.5
- 天气：室外气象站（weather_station）
- 网络状态：智能路由器（router）
- 房间安全警报：门锁/门窗/水浸/燃气/烟雾传感器
- 电费/水费/燃气费余额：智能电表/水表/燃气表
没有对应设备时指标为 None，前端展示 "--"。
"""
from typing import Any, Dict, List

from app.services.device_service import list_devices_by_family

SECURITY_SENSOR_TYPES = (
    "door_lock",
    "door_window_sensor",
    "leak_sensor",
    "gas_sensor",
    "smoke_sensor",
)


def _average(values: List[float]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def _air_quality_label(pm25: float) -> str:
    if pm25 <= 35:
        return "优"
    if pm25 <= 75:
        return "良"
    if pm25 <= 115:
        return "轻度污染"
    return "中度污染"


def _status(device, key: str):
    """读取设备状态字段，忽略空值。"""
    value = (device.status or {}).get(key)
    return value


async def get_family_environment(family_id: int) -> Dict[str, Any]:
    """聚合家庭中控指标；无对应设备时返回 None。"""
    devices = await list_devices_by_family(family_id)

    indoor_temps = []
    indoor_humidities = []
    outdoor_temps = []
    for device in devices:
        if device.type == "temp_humidity_sensor" and _status(device, "online"):
            if _status(device, "temperature") is not None:
                indoor_temps.append(float(device.status["temperature"]))
            if _status(device, "humidity") is not None:
                indoor_humidities.append(float(device.status["humidity"]))
        elif device.type in ("outdoor_sensor", "weather_station") and _status(device, "online"):
            if _status(device, "temperature") is not None:
                outdoor_temps.append(float(device.status["temperature"]))

    air_quality = None
    for device in devices:
        if device.type == "air_monitor" and _status(device, "online"):
            label = _status(device, "air_quality")
            if label:
                air_quality = str(label)
                break
            pm25 = _status(device, "pm25")
            if pm25 is not None:
                air_quality = _air_quality_label(float(pm25))
                break
    if air_quality is None:
        pm25_values = [
            float(device.status["pm25"])
            for device in devices
            if device.type == "air_purifier"
            and _status(device, "power") == "on"
            and _status(device, "pm25") is not None
        ]
        if pm25_values:
            air_quality = _air_quality_label(_average(pm25_values))

    weather = None
    for device in devices:
        if device.type == "weather_station" and _status(device, "online"):
            weather = _status(device, "weather")
            if weather:
                weather = str(weather)
                break

    network_status = None
    for device in devices:
        if device.type == "router" and _status(device, "online"):
            internet = _status(device, "internet_status")
            network_status = "在线" if internet in ("online", True) else "离线"
            break

    security_devices = [device for device in devices if device.type in SECURITY_SENSOR_TYPES]
    security_alarm = None
    if security_devices:
        messages = []
        for device in security_devices:
            if device.type == "door_lock" and _status(device, "locked") is False:
                messages.append(f"{device.name}未上锁")
            if device.type == "door_window_sensor" and _status(device, "status") == "open":
                messages.append(f"{device.name}门窗开启")
            if device.type == "leak_sensor" and _status(device, "leak"):
                messages.append(f"{device.name}漏水告警")
            if device.type == "gas_sensor" and _status(device, "gas_leak"):
                messages.append(f"{device.name}燃气泄漏")
            if device.type == "smoke_sensor" and (
                _status(device, "smoke") or _status(device, "alarm")
            ):
                messages.append(f"{device.name}烟雾告警")
        security_alarm = {
            "status": "alert" if messages else "normal",
            "messages": messages,
        }

    balances = {}
    for device in devices:
        balance = _status(device, "balance")
        if balance is None:
            continue
        if device.type == "electricity_meter" and "electricity" not in balances:
            balances["electricity"] = float(balance)
        elif device.type == "water_meter" and "water" not in balances:
            balances["water"] = float(balance)
        elif device.type == "gas_meter" and "gas" not in balances:
            balances["gas"] = float(balance)

    return {
        "indoor_temperature": _average(indoor_temps) or None,
        "outdoor_temperature": _average(outdoor_temps) or None,
        "indoor_humidity": _average(indoor_humidities) or None,
        "air_quality": air_quality,
        "weather": weather,
        "network_status": network_status,
        "security_alarm": security_alarm,
        "electricity_balance": balances.get("electricity"),
        "water_balance": balances.get("water"),
        "gas_balance": balances.get("gas"),
    }