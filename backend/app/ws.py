"""WebSocket Connection Manager and Handlers."""
from typing import Dict, List, Set, Optional
from fastapi import WebSocket
from starlette.websockets import WebSocketState


class ConnectionManager:
    """Manages active WebSocket connections across Admin, Camera, and Customer."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.admin_connections: Set[WebSocket] = set()
        self.customer_connections: Dict[str, Set[WebSocket]] = {}
        self.camera_connections: Dict[str, WebSocket] = {}

    async def connect_admin(self, websocket: WebSocket):
        if websocket.client_state != WebSocketState.CONNECTED:
            await websocket.accept()
        self.active_connections.append(websocket)
        self.admin_connections.add(websocket)

    def disconnect_admin(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.admin_connections.discard(websocket)

    async def connect_customer(self, websocket: WebSocket, session_secret: str):
        if websocket.client_state != WebSocketState.CONNECTED:
            await websocket.accept()
        self.active_connections.append(websocket)
        if session_secret not in self.customer_connections:
            self.customer_connections[session_secret] = set()
        self.customer_connections[session_secret].add(websocket)

    def disconnect_customer(self, websocket: WebSocket, session_secret: str):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if session_secret in self.customer_connections:
            self.customer_connections[session_secret].discard(websocket)
            if not self.customer_connections[session_secret]:
                del self.customer_connections[session_secret]

    async def connect_camera(self, websocket: WebSocket, device_id: str):
        if websocket.client_state != WebSocketState.CONNECTED:
            await websocket.accept()
        self.active_connections.append(websocket)
        self.camera_connections[device_id] = websocket

    def disconnect_camera(self, websocket: WebSocket, device_id: str):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if device_id in self.camera_connections:
            del self.camera_connections[device_id]

    async def broadcast_to_admins(self, data: dict):
        for ws in list(self.admin_connections):
            try:
                await ws.send_json(data)
            except Exception:
                self.admin_connections.discard(ws)

    async def broadcast_to_customer(self, session_secret: str, data: dict):
        if session_secret in self.customer_connections:
            for ws in list(self.customer_connections[session_secret]):
                try:
                    await ws.send_json(data)
                except Exception:
                    self.customer_connections[session_secret].discard(ws)

    async def broadcast_json(self, data: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                pass


manager = ConnectionManager()
