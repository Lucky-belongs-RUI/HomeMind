"""WebSocket 连接管理器，负责设备状态与 Agent 流式响应推送。"""
import json
from typing import Any, Dict, List

from fastapi import WebSocket


class WebSocketManager:
    """WebSocket 连接管理器，负责设备状态与 Agent 流式响应推送。"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_device_update(self, message: Dict[str, Any]):
        """广播设备状态变更到所有连接（前端按 family_id 过滤）。"""
        if not self.active_connections:
            return
        text = json.dumps(message, ensure_ascii=False)
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_text(text)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)

    async def send_agent_message(self, websocket: WebSocket, message: Dict[str, Any]):
        """向指定连接发送 Agent 消息。"""
        await websocket.send_text(json.dumps(message, ensure_ascii=False))


ws_manager = WebSocketManager()


async def broadcast_device_update(message: Dict[str, Any]):
    await ws_manager.broadcast_device_update(message)