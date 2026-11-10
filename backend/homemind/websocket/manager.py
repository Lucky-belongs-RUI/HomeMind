"""WebSocket 连接管理器，负责设备状态与 Agent 流式响应推送。"""

import json
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    """WebSocket 连接管理器，负责设备状态与 Agent 流式响应推送。

    连接按家庭分组：设备状态广播只发给同一家庭的连接。
    原实现向全部连接广播、由前端按 family_id 过滤，A 家的设备状态会
    实际推送到 B 家用户的连接上（前端过滤不是服务端隔离）。
    """

    def __init__(self):
        # family_id -> 该家庭的活跃连接；None 表示未认证连接（不接收广播）
        self.active_connections: dict[int | None, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, family_id: int | None = None):
        await websocket.accept()
        self.active_connections.setdefault(family_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket):
        for family_id, connections in list(self.active_connections.items()):
            if websocket in connections:
                connections.remove(websocket)
            if not connections:
                self.active_connections.pop(family_id, None)

    @staticmethod
    def _normalize_family_id(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def broadcast_device_update(self, message: dict[str, Any]):
        """把设备状态变更广播给同一家庭的连接。

        家庭 ID 直接取自消息体的 family_id 字段——所有设备更新消息
        （设备控制工具、场景执行、手动改设备、模拟器）都已携带该字段，
        因此各调用方无需改动签名。family_id 缺失时不广播，避免误发给未认证连接。
        """
        family_id = self._normalize_family_id(message.get("family_id"))
        if family_id is None:
            return
        connections = self.active_connections.get(family_id)
        if not connections:
            return
        text = json.dumps(message, ensure_ascii=False)
        dead = []
        for conn in connections:
            try:
                await conn.send_text(text)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)

    async def send_agent_message(self, websocket: WebSocket, message: dict[str, Any]):
        """向指定连接发送 Agent 消息。"""
        await websocket.send_text(json.dumps(message, ensure_ascii=False))


ws_manager = WebSocketManager()


async def broadcast_device_update(message: dict[str, Any]):
    await ws_manager.broadcast_device_update(message)
