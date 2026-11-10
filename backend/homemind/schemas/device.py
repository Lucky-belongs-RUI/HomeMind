import math
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

# ============================================================
# 请求模型
# ============================================================

# 状态请求的防御性上限：避免超长键名/海量键或嵌套结构写进 JSON 列
_MAX_ATTRIBUTE_KEYS = 64
_MAX_KEY_LENGTH = 64
_POSITION_KEYS = {"x", "y"}

# 语义为数值的状态字段：字符串/布尔值写进来会让下游统计与图表直接报错
_NUMERIC_ATTRIBUTES = frozenset(
    {
        "temperature",
        "freezer_temperature",
        "humidity",
        "battery",
        "brightness",
        "volume",
        "channel",
        "pm25",
        "pm10",
        "co2",
        "hcho",
        "tvoc",
        "co",
        "target_humidity",
        "water_level",
        "filter_life",
        "signal_strength",
        "device_count",
        "bandwidth_mbps",
        "power_w",
        "voltage",
        "current",
        "energy_kwh",
        "daily_energy_kwh",
        "monthly_energy_kwh",
        "balance",
        "uv_index",
        "pressure",
        "flow_rate",
        "daily_usage",
        "monthly_usage",
        "dust_bin",
    }
)


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_device_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """校验设备状态字段，API 与 Agent 工具共用同一套约束。

    只允许标量字段与 position 坐标，拒绝任意嵌套/超大 JSON，
    并对语义为数值的字段做类型校验，避免脏数据进入状态列。
    """
    if len(attributes) > _MAX_ATTRIBUTE_KEYS:
        raise ValueError(f"状态字段过多（最多 {_MAX_ATTRIBUTE_KEYS} 个）")

    for key, value in attributes.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("状态字段名不能为空")
        if len(key) > _MAX_KEY_LENGTH:
            raise ValueError(f"状态字段名过长（最多 {_MAX_KEY_LENGTH} 个字符）")

        if key == "position":
            if isinstance(value, dict):
                if set(value) - _POSITION_KEYS or not all(
                    _is_finite_number(coord) for coord in value.values()
                ):
                    raise ValueError("position 仅支持数字 x/y 坐标")
            elif not _is_finite_number(value):
                raise ValueError("position 必须是数字或 x/y 坐标")
            continue

        if isinstance(value, dict | list | tuple | set):
            raise ValueError(f"状态字段 {key} 不支持嵌套结构")
        if value is None:
            raise ValueError(f"状态字段 {key} 不能为 null")
        if key in _NUMERIC_ATTRIBUTES and not _is_finite_number(value):
            raise ValueError(f"状态字段 {key} 必须是有效数字")
    return attributes


class DeviceCreate(BaseModel):
    """创建设备请求。"""

    name: str
    type: str
    room_id: int
    brand: str | None = None
    model: str | None = None


class DeviceUpdate(BaseModel):
    """更新设备信息请求。"""

    name: str | None = None
    type: str | None = None
    room_id: int | None = None
    brand: str | None = None
    model: str | None = None


class DeviceStatusUpdate(BaseModel):
    """更新设备状态请求（前端卡片控制使用）。"""

    attributes: dict[str, Any]

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, attributes: dict[str, Any]) -> dict[str, Any]:
        return validate_device_attributes(attributes)


# ============================================================
# 响应模型
#
# 字段与 api/device.py 的 _device_dict / _log_dict 严格一致。
# response_model 会**过滤**未声明字段——少写一个前端就拿不到，
# 所以增删字段时必须同步改这里。
#
# from_attributes=True 让同一个模型既能校验 dict，也能校验 ORM 对象
# （/families/{id}/devices 直接返回 ORM 列表）。
# ============================================================


class DeviceItem(BaseModel):
    """设备详情 / 列表项。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    name: str
    type: str
    room_id: int
    brand: str | None = None
    model: str | None = None
    status: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DeviceLogItem(BaseModel):
    """设备操作日志条目。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    user_id: int | None = None
    operation: str
    source: str
    before_status: dict[str, Any] | None = None
    after_status: dict[str, Any] | None = None
    description: str | None = None
    created_at: str | None = None
