"""从图状态中提取服务端注入的可信身份。

工具只能通过 InjectedState 拿到身份，模型无法在参数里伪造 user_id / family_id。
"""

from __future__ import annotations

from typing import Any


def extract_identity(state: dict[str, Any]) -> tuple[int, str, int] | None:
    request = state.get("request") or {}
    user_id = request.get("user_id")
    role = request.get("role")
    family_id = request.get("family_id")
    if user_id is None or not role or family_id is None:
        return None
    return int(user_id), str(role), int(family_id)


__all__ = ["extract_identity"]
