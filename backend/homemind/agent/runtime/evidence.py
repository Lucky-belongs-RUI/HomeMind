"""回复证据门槛：没有对应设备的工具执行记录时，不允许声称已完成操作。

模型会把历史对话、用户指令或全屋状态改写成“已为您调好空调”，而本轮
实际上只操作了灯。这里按“设备 + 属性”逐句核对成功写操作，避免部分成功
被当成全部成功。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from homemind.agent.rules.devices import (
    DEVICE_TYPE_ALIASES,
    ROOM_ALIASES,
    normalize_room_name,
)
from homemind.agent.rules.plan import parse_attributes

WRITE_TOOLS = frozenset({"set_device_state", "trigger_scene"})

_CLAIM = re.compile(
    r"(?:已|已经|帮您|为您|自动)[^。！？!?\n]{0,15}?"
    r"(?:打开|关闭|关掉|开启|启动|调到|调至|调成|设为|设置|调整|"
    r"调暗|调亮|调高|调低|解锁|锁定|拉上|拉开|烧|清扫|切换)"
)
_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?\n]?")
_CLAUSE = re.compile(r"[^，,；;]+[，,；;]?")
_SUGGESTION_MARKERS = ("如果", "要不要", "是否需要", "需要我", "请确认", "是否已", "建议您")
_FAILURE_MARKERS = ("失败", "未能", "没有执行", "未执行", "未完成", "无法", "没找到", "不支持")
_SCENE_WORDS = ("回家", "离家", "睡眠", "观影", "会客", "晨起")
# 数值型目标必须与真实写入值一致；开关/模式允许由设备默认行为补齐
_STRICT_CLAIM_KEYS = frozenset(
    {"temperature", "brightness", "position", "volume", "channel", "target_humidity"}
)

NO_ACTION_FALLBACK = (
    "本轮我没有实际执行设备操作；如果需要，请告诉我具体要控制的房间和设备。"
)
PARTIAL_ACTION_FALLBACK = "本轮只完成了部分设备操作，其余指令尚未执行，请确认设备状态后再试。"


@dataclass(frozen=True)
class WriteAction:
    """一次成功写操作的确定性事实。"""

    tool: str
    device_type: str = ""
    room_name: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    scene_name: str = ""


def executed_writes(results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """从控制分支结果中提取本轮真正成功的写操作。"""
    writes: list[dict[str, Any]] = []
    for item in results or []:
        if item.get("branch") != "control":
            continue
        for observation in (item.get("data") or {}).get("observations") or []:
            if not observation.get("success"):
                continue
            if observation.get("tool") not in WRITE_TOOLS:
                continue
            writes.append(
                {
                    "tool": observation.get("tool"),
                    "arguments": observation.get("arguments") or {},
                    "message": (observation.get("result") or {}).get("message") or "",
                }
            )
    return writes


def executed_actions(results: list[dict[str, Any]] | None) -> list[WriteAction]:
    """把成功写操作展开成可按设备比对的原子事实。"""
    actions: list[WriteAction] = []
    for write in executed_writes(results):
        arguments = write.get("arguments") or {}
        if write.get("tool") == "set_device_state":
            actions.append(
                WriteAction(
                    tool="set_device_state",
                    device_type=str(arguments.get("device_type") or ""),
                    room_name=str(arguments.get("room_name") or ""),
                    attributes=dict(arguments.get("attributes") or {}),
                )
            )
        elif write.get("tool") == "trigger_scene":
            actions.append(
                WriteAction(
                    tool="trigger_scene",
                    scene_name=str(arguments.get("scene_name") or ""),
                )
            )
    return actions


def has_successful_write(results: list[dict[str, Any]] | None) -> bool:
    return bool(executed_writes(results))


def control_failures(results: list[dict[str, Any]] | None) -> list[str]:
    """返回本轮控制分支的失败原因（含场景部分失败）。"""
    failures: list[str] = []
    for item in results or []:
        if item.get("branch") != "control":
            continue
        data = item.get("data") or {}
        observations = data.get("observations") or []
        for observation in observations:
            result = observation.get("result") or {}
            partial = int(result.get("failed_count") or 0) > 0
            if not observation.get("success") or partial:
                failures.append(
                    str(
                        observation.get("error")
                        or result.get("error")
                        or result.get("message")
                        or "设备操作未完成"
                    )
                )
        if not observations and not item.get("success"):
            failures.append(str(item.get("summary") or "设备操作未完成"))
    return list(dict.fromkeys(failures))


def can_stream(results: list[dict[str, Any]] | None) -> bool:
    """有成功写操作且没有失败任务时才允许流式输出。

    部分失败一旦流式发给前端就无法回收，必须缓冲后由证据门槛修正。
    """
    return has_successful_write(results) and not control_failures(results)


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) == bool(right)
    if isinstance(left, int | float) and isinstance(right, int | float):
        return abs(float(left) - float(right)) < 1e-6
    return str(left).strip().lower() == str(right).strip().lower()


def _mentioned_devices(text: str) -> list[str]:
    devices: list[str] = []
    for alias, device_type in DEVICE_TYPE_ALIASES.items():
        if alias in text and device_type not in devices:
            devices.append(device_type)
    return devices


def _room_matches(text: str, action: WriteAction) -> bool:
    if not action.room_name:
        return True
    rooms = {room for alias, room in ROOM_ALIASES.items() if alias in text}
    if not rooms:
        return True
    return normalize_room_name(action.room_name) in {normalize_room_name(room) for room in rooms}


def _claim_backed(text: str, device_type: str, actions: list[WriteAction]) -> bool:
    candidates = [
        action
        for action in actions
        if action.tool == "set_device_state"
        and action.device_type == device_type
        and _room_matches(text, action)
    ]
    if not candidates:
        return False

    claimed = parse_attributes(text, device_type)
    for key, value in claimed.items():
        observed = [action.attributes[key] for action in candidates if key in action.attributes]
        strict = key in _STRICT_CLAIM_KEYS or (key == "power" and str(value).lower() == "off")
        if not observed:
            if strict:
                return False
            continue
        if not any(_same(observed_value, value) for observed_value in observed):
            return False
    return True


def _scene_backed(text: str, actions: list[WriteAction]) -> bool:
    scenes = [action.scene_name for action in actions if action.tool == "trigger_scene"]
    if not scenes:
        return False
    words = [word for word in _SCENE_WORDS if word in text]
    if not words:
        return True
    return any(any(word in scene for word in words) for scene in scenes)


def _sentence_backed(text: str, actions: list[WriteAction], failures: list[str]) -> bool:
    devices = _mentioned_devices(text)
    if devices:
        return all(_claim_backed(text, device_type, actions) for device_type in devices)
    if any(word in text for word in _SCENE_WORDS):
        return _scene_backed(text, actions)
    # 没有点名设备的泛化声明：存在失败任务时无法确认具体完成了什么，一律不采信
    return bool(actions) and not failures


def _trim_partial_claim(
    sentence: str,
    actions: list[WriteAction],
) -> str | None:
    """一句里既有已执行设备又有未执行设备时，只保留有证据的分句。"""
    devices = _mentioned_devices(sentence)
    if not devices:
        return sentence
    backed = [device for device in devices if _claim_backed(sentence, device, actions)]
    if len(backed) == len(devices):
        return sentence
    if not backed:
        return None

    kept: list[str] = []
    for clause in _CLAUSE.findall(sentence):
        clause_devices = _mentioned_devices(clause)
        if clause_devices and all(
            _claim_backed(clause, device, actions) for device in clause_devices
        ):
            kept.append(clause)
    trimmed = "".join(kept).strip().rstrip("，,；; ")
    if not trimmed:
        return None
    ending = sentence.strip()[-1] if sentence.strip()[-1] in "。！？!?" else "。"
    return f"{trimmed}{ending}"


def strip_unbacked_claims(answer: str, results: list[dict[str, Any]] | None) -> str:
    """删除没有对应成功写操作支撑的动作声明。"""
    text = str(answer or "").strip()
    if not text:
        return text

    actions = executed_actions(results)
    failures = control_failures(results)

    kept: list[str] = []
    for sentence in _SENTENCE.findall(text):
        if not sentence.strip():
            continue
        claims_action = _CLAIM.search(sentence) and not any(
            marker in sentence for marker in _SUGGESTION_MARKERS
        )
        if claims_action and not _sentence_backed(sentence, actions, failures):
            sentence = (
                _trim_partial_claim(sentence, actions) if _mentioned_devices(sentence) else ""
            ) or ""
        if sentence:
            kept.append(sentence)

    cleaned = "".join(kept).strip()
    if cleaned:
        return cleaned
    if failures:
        return "设备操作未完成：" + "；".join(failures)
    if actions:
        return PARTIAL_ACTION_FALLBACK
    return NO_ACTION_FALLBACK


def ensure_failure_notice(answer: str, results: list[dict[str, Any]] | None) -> str:
    """确保用户能看到未完成项，即使模型漏写失败原因。"""
    failures = control_failures(results)
    if not failures:
        return answer
    text = str(answer or "").strip()
    if any(marker in text for marker in _FAILURE_MARKERS):
        return text
    notice = "未完成：" + "；".join(failures)
    return f"{text}\n\n{notice}" if text else notice


__all__ = [
    "NO_ACTION_FALLBACK",
    "PARTIAL_ACTION_FALLBACK",
    "WRITE_TOOLS",
    "can_stream",
    "control_failures",
    "ensure_failure_notice",
    "executed_actions",
    "executed_writes",
    "has_successful_write",
    "strip_unbacked_claims",
]
