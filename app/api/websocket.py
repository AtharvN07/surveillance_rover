"""
websocket.py — WebSocket endpoints for real-time joystick, telemetry, and map updates.
"""
import asyncio
import json
import logging
import time
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("rover.ws")
router = APIRouter()

# ── Connection manager ────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        logger.info("WS client connected (%d total)", len(self.active))

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        logger.info("WS client disconnected (%d remaining)", len(self.active))

    async def broadcast(self, data: dict):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)


manager = ConnectionManager()


# ── Joystick control WebSocket ────────────────────────────────────────────────
@router.websocket("/ws/control")
async def control_ws(websocket: WebSocket):
    await manager.connect(websocket)
    rover = websocket.app.state.rover
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            kind = msg.get("type")

            if kind == "joystick":
                x = float(msg.get("x", 0))
                y = float(msg.get("y", 0))
                rover.safety.heartbeat()
                if rover.mode == "manual" and hasattr(rover, "velocity"):
                    await rover.velocity.set_joystick(x, y)
                await websocket.send_json({"type": "ack", "t": time.time()})

            elif kind == "estop":
                rover.safety.trigger_estop()
                await rover.arduino.emergency_stop()
                await websocket.send_json({"type": "estop_ack"})

            elif kind == "estop_clear":
                rover.safety.clear_estop()
                await websocket.send_json({"type": "estop_cleared"})

            elif kind == "mode":
                rover.mode = msg.get("value", "manual")
                await websocket.send_json({"type": "mode_ack", "mode": rover.mode})

            elif kind == "ping":
                await websocket.send_json({"type": "pong", "t": time.time()})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        # Stop motors when dashboard disconnects
        await rover.arduino.emergency_stop()


# ── Telemetry broadcast WebSocket ─────────────────────────────────────────────
@router.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await manager.connect(websocket)
    rover = websocket.app.state.rover
    try:
        while True:
            data = await rover.telemetry.collect()
            await websocket.send_json(data)
            await asyncio.sleep(0.2)   # 5 Hz telemetry
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Map update WebSocket ──────────────────────────────────────────────────────
@router.websocket("/ws/map")
async def map_ws(websocket: WebSocket):
    await manager.connect(websocket)
    rover = websocket.app.state.rover
    try:
        while True:
            if hasattr(rover, "slam") and rover.slam:
                map_data = rover.slam.get_map_json()
                pose     = rover.velocity.pose if hasattr(rover, "velocity") else {}
                await websocket.send_json({"type": "map", "map": map_data, "pose": pose})
            await asyncio.sleep(0.5)   # 2 Hz map updates
    except WebSocketDisconnect:
        manager.disconnect(websocket)
