from typing import List

from fastapi import WebSocket
import json
import queue


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.feedback_queue = queue.Queue()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        for ws in list(self.active_connections):
            try:
                await ws.send_text(data)
            except Exception as e:
                print(f"Error sending message: {e}")
                self.active_connections.remove(ws)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)