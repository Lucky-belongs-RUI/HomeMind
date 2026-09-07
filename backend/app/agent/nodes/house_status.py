"""全屋状态节点：汇总家庭房间、设备、环境与当前时间季节。

用于两处：
1. 首次进入聊天界面时生成动态开场白（由 /agent/opening 调用，只运行一次）。
2. 每轮对话把紧凑的全屋状态注入意图识别与任务规划，让模型
   根据天气、日期、季节和家庭实际设备自由判断操作。
"""
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.agent.rules.common import device_label
from app.llm.factory import get_llm_client
from app.llm.message import Message
from app.services.device_service import list_devices_by_family
from app.services.environment_service import get_family_environment
from app.services.room_service import list_rooms_by_family

logger = logging.getLogger(__name__)

WEEKDAY_LABELS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

SEASON_BY_MONTH = {
    1: "冬季", 2: "冬季", 3: "春季", 4: "春季", 5: "春季",
    6: "夏季", 7: "夏季", 8: "夏季", 9: "秋季", 10: "秋季", 11: "秋季", 12: "冬季",
}


def _season(month: int) -> str:
    return SEASON_BY_MONTH.get(month, "")


def _period_label(hour: int) -> str:
    if 5 <= hour < 9:
        return "早上"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 23:
        return "晚上"
    return "凌晨"


def _collect_issues(status: Dict[str, Any]) -> List[str]:
    """汇总安全类异常，供开场白与上下文使用。"""
    issues = []
    for device in status.get("devices") or []:
        st = device.get("status") or {}
        device_type = device.get("type", "")
        name = device.get("name", "")
        if device_type == "door_lock" and st.get("locked") is False:
            issues.append(f"{name}未上锁")
        if device_type == "door_window_sensor" and st.get("status") == "open":
            issues.append(f"{name}门窗开启")
        if device_type == "leak_sensor" and st.get("leak"):
            issues.append(f"{name}漏水")
        if device_type == "gas_sensor" and st.get("gas_leak"):
            issues.append(f"{name}燃气泄漏")
        if device_type == "smoke_sensor" and (st.get("smoke") or st.get("alarm")):
            issues.append(f"{name}烟雾告警")
    return issues


def _device_brief(device: Dict[str, Any]) -> str:
    """把设备状态压缩成一行中文摘要，控制 prompt 长度。"""
    status = device.get("status") or {}
    room = device.get("room") or "未分区"
    label = device.get("type_label") or device.get("type", "设备")
    name = device.get("name", "")
    fields = []
    for key in (
        "power", "temperature", "brightness", "position", "volume",
        "mode", "locked", "status", "pm25", "humidity", "battery",
        "online", "internet_status", "weather",
    ):
        if key in status and status[key] is not None:
            fields.append(f"{key}={status[key]}")
    base = f"{room}{label}({name})"
    return f"{base}[{','.join(fields)}]" if fields else base


async def collect_house_status(family_id: int) -> Dict[str, Any]:
    """获取家庭房间、设备、环境指标以及当前时间/季节信息。"""
    rooms = await list_rooms_by_family(family_id)
    devices = await list_devices_by_family(family_id)
    environment = await get_family_environment(family_id)
    room_map = {room.id: room.name for room in rooms}

    device_rows = []
    for device in devices:
        device_rows.append(
            {
                "name": device.name,
                "type": device.type,
                "type_label": device_label(device.type),
                "room": room_map.get(device.room_id, ""),
                "status": dict(device.status or {}),
            }
        )

    now = datetime.now()
    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M"),
        "weekday": WEEKDAY_LABELS[now.weekday()],
        "season": _season(now.month),
        "period": _period_label(now.hour),
        "environment": environment,
        "rooms": [
            {
                "name": room.name,
                "device_count": sum(1 for d in devices if d.room_id == room.id),
            }
            for room in rooms
        ],
        "devices": device_rows,
    }


def build_house_status_text(status: Dict[str, Any]) -> str:
    """把全屋状态转成适合注入 LLM prompt 的中文文本。"""
    if not status:
        return "暂无家庭状态数据。"
    env = status.get("environment") or {}
    lines = [
        (
            f"当前时间：{status.get('datetime', '')}，{status.get('weekday', '')}，"
            f"{status.get('season', '')}，{status.get('period', '')}。"
        ),
        (
            f"室内温度：{env.get('indoor_temperature') or '无数据'}℃，"
            f"室内湿度：{env.get('indoor_humidity') or '无数据'}%，"
            f"空气质量：{env.get('air_quality') or '无数据'}；"
            f"室外温度：{env.get('outdoor_temperature') or '无数据'}℃，"
            f"天气：{env.get('weather') or '无数据'}。"
        ),
    ]
    devices = status.get("devices") or []
    if devices:
        lines.append("家庭设备：" + "；".join(_device_brief(item) for item in devices))
    else:
        lines.append("家庭设备：暂无设备")
    issues = _collect_issues(status)
    if issues:
        lines.append("异常提示：" + "；".join(issues) + "。")
    return "\n".join(lines)


OPENING_PROMPT = """你是智能家居助理，现在要为用户生成首次进入 AI 助理界面的开场白。

当前家庭状态：
{house_status}

用户昵称：{nickname}

开场白要求：
1. 根据当前时间段问候用户，并称呼用户昵称（如“下午好，{nickname}”）。
2. 概括当前全屋设备状态：设备全部正常时明确说“当前房屋各设备正常”；有异常时说明具体异常。
3. 结合当前天气或季节给出一句简短、自然的关怀或建议。
4. 语气温暖口语化，不要输出 JSON，不要复述设备原始字段，总长度不超过 100 字。"""


def _rule_opening(status: Dict[str, Any], nickname: str) -> str:
    """LLM 不可用时的规则版开场白。"""
    greeting = {
        "凌晨": "夜深了",
        "早上": "早上好",
        "上午": "上午好",
        "中午": "中午好",
        "下午": "下午好",
        "晚上": "晚上好",
    }.get(status.get("period", ""), "您好")
    issues = _collect_issues(status)
    if issues:
        state_text = "当前房屋有异常：" + "、".join(issues)
    else:
        state_text = "当前房屋各设备正常"

    env = status.get("environment") or {}
    hint = ""
    season = status.get("season", "")
    outdoor = env.get("outdoor_temperature")
    if season == "夏季" and outdoor is not None and outdoor >= 30:
        hint = "天气炎热，记得补水防暑。"
    elif season == "冬季" and outdoor is not None and outdoor <= 10:
        hint = "天气寒冷，注意保暖。"
    elif env.get("air_quality") in ("轻度污染", "中度污染"):
        hint = "空气质量一般，建议开启空气净化器。"
    return f"{greeting}，{nickname}！{state_text}。{hint}"


async def generate_opening_message(family_id: int, nickname: str) -> str:
    """生成首次进入的开场白：优先调用模型，失败时使用规则回退。"""
    status = await collect_house_status(family_id)
    try:
        client = get_llm_client()
        result = await client.chat(
            messages=[Message(role="user", content="请生成开场白")],
            system=OPENING_PROMPT.format(
                house_status=build_house_status_text(status),
                nickname=nickname,
            ),
            temperature=0.8,
            max_tokens=240,
        )
        text = (result.content or "").strip()
        if text:
            return text
    except Exception as exc:
        logger.warning("开场白生成失败，使用规则回退: %s", exc)
    return _rule_opening(status, nickname)


async def house_status_retrieval_node(state: dict) -> dict:
    """全屋状态节点：把家庭房间、设备与环境数据写入 AgentState。

    API 层每轮已注入最新全屋状态时直接复用，避免重复查库；
    未注入时（如直接调用图或测试）在此补齐。
    """
    current = dict(state)
    if current.get("house_status"):
        return current
    family_id = current.get("family_id")
    if not family_id:
        current["house_status"] = {}
        return current
    current["house_status"] = await collect_house_status(family_id)
    return current
