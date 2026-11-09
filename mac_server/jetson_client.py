"""
jetson_client.py — WebSocket client that talks to the Jetson rover server.
Parses the Socket.IO protocol directly (no python-socketio dependency needed).
"""
import asyncio
import json
import logging
import time

import websockets

log = logging.getLogger("mac.jetson_client")


class JetsonClient:
    def __init__(self, base_url: str):
        # base_url like http://192.168.31.122:8000
        host = base_url.replace("http://", "").split("/")[0]
        self._socketio_url = f"ws://{host}/socket.io/?EIO=4&transport=websocket"
        self._rest_url = base_url
        self._ws: websockets.WebSocketClientProtocol = None
        self._connected = False
        self._sid = None
        self._task: asyncio.Task = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self):
        while not self._connected:
            try:
                log.info("Connecting to Jetson: %s", self._socketio_url)
                self._ws = await websockets.connect(
                    self._socketio_url,
                    ping_interval=5,
                    ping_timeout=10,
                )
                # Wait for Socket.IO open handshake
                raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
                # Format: 0{"sid":"...","pingInterval":25000,...}
                if raw.startswith("0"):
                    data = json.loads(raw[1:])
                    self._sid = data.get("sid")
                # Send connect packet
                await self._ws.send("40")
                self._connected = True
                log.info("Jetson WebSocket connected")
                # Start ping loop
                self._task = asyncio.create_task(self._ping_loop())
            except Exception as e:
                log.warning("Jetson connect failed: %s — retrying in 3s", e)
                self._connected = False
                await asyncio.sleep(3)

    async def _ping_loop(self):
        while self._connected and self._ws:
            try:
                await asyncio.sleep(5)
                await self._ws.send("2")  # Socket.IO ping
                # Read pong (3)
                try:
                    msg = await asyncio.wait_for(self._ws.recv(), timeout=3)
                except asyncio.TimeoutError:
                    pass
            except Exception:
                self._connected = False
                break

    async def _send_event(self, event: str, data: dict = None):
        if not self._connected or not self._ws:
            return
        payload = {"l": data.get("l", 0), "r": data.get("r", 0)} if data else {}
        # Socket.IO event format: 42["eventName",{...}]
        pkt = f'42["{event}",{json.dumps(payload)}]'
        try:
            await self._ws.send(pkt)
        except Exception as e:
            log.warning("Send failed: %s", e)
            self._connected = False

    async def send_motors(self, left: int, right: int):
        await self._send_event("cmd", {"l": int(left), "r": int(right)})

    async def emergency_stop(self):
        await self._send_event("estop")

    async def resume(self):
        await self._send_event("estop_clear")

    async def set_mode(self, mode: str):
        await self._send_event("mode", {"value": mode})

    async def get_status(self) -> dict:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{self._rest_url}/api/status")
                return r.json()
        except Exception:
            return {}

    async def disconnect(self):
        self._connected = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
