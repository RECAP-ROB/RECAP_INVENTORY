import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

import asyncio
import threading

import rclpy
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from rs2_ws.src.recap_action.recap_action.restock_client import ROSBridge

from .websocket_manager import WebSocketManager
from .models import RestockRequest

app = FastAPI(title="ROS Bridge Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

websocket_manager = WebSocketManager()

rclpy.init()

ros_bridge = ROSBridge(websocket_manager)


def main():
    rclpy.spin(ros_bridge)

ros_thread = threading.Thread(target=main, daemon=True)


async def process_feedback():
    while True:
        data = await asyncio.get_event_loop().run_in_executor(
            None, websocket_manager.feedback_queue.get
        )
        await websocket_manager.broadcast(data)


@app.on_event("startup")
async def startup_event():
    if not ros_thread.is_alive():
        ros_thread.start()
    asyncio.create_task(process_feedback())


@app.websocket("/ws")
@app.websocket("/ws/restock/queue")
@app.websocket("/ws/restock")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        websocket_manager.disconnect(websocket)


def _get_restock_item_shelf_state(item_id: int) -> str:
    from api.models import RestockItem

    try:
        restock_item = RestockItem.objects.get(id=item_id)
        return restock_item.shelf_state or "unknown"
    except RestockItem.DoesNotExist:
        return "unknown"


@app.post("/restock/queue")
@app.post("/restock")
async def start_restock(request: RestockRequest):
    loop = asyncio.get_running_loop()
    request.current_state = await loop.run_in_executor(
        None, _get_restock_item_shelf_state, request.item_id
    )

    result = await ros_bridge.send_restock_goal(request)

    return result

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
    