"""
arduino.py — Async serial interface to the Arduino Mega motor controller.
Sends M:left,right commands and handles watchdog/reconnection.
"""
import asyncio
import logging
import time
from typing import Optional

import serial
import serial.tools.list_ports

from app.config import RoverConfig

logger = logging.getLogger("rover.arduino")


class ArduinoInterface:
    def __init__(self, cfg: RoverConfig):
        self.cfg = cfg
        self._ser: Optional[serial.Serial] = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._last_response: str = ""
        self._reconnect_task: Optional[asyncio.Task] = None

    # ── Connection ────────────────────────────────────────────────────────────
    async def connect(self) -> bool:
        try:
            self._ser = serial.Serial(
                port=self.cfg.arduino_port,
                baudrate=self.cfg.arduino_baud,
                timeout=self.cfg.arduino_timeout,
            )
            await asyncio.sleep(2.0)          # Arduino resets on connect
            self._ser.reset_input_buffer()
            ok = await self.ping()
            self._connected = ok
            if ok:
                logger.info("Arduino connected on %s", self.cfg.arduino_port)
                await self._send_raw(f"MAXSPD:{self.cfg.max_speed}\n")
                await self._send_raw(f"ACCEL:{self.cfg.accel_step}\n")
            else:
                logger.warning("Arduino not responding — running without motors")
            return ok
        except serial.SerialException as e:
            logger.error("Arduino connect failed: %s", e)
            self._connected = False
            return False

    async def _reconnect_loop(self):
        while not self._connected:
            await asyncio.sleep(3.0)
            logger.info("Attempting Arduino reconnect …")
            await self.connect()

    def schedule_reconnect(self):
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    # ── Low-level I/O ─────────────────────────────────────────────────────────
    async def _send_raw(self, msg: str) -> Optional[str]:
        if self._ser is None or not self._ser.is_open:
            return None
        async with self._lock:
            try:
                self._ser.write(msg.encode())
                self._ser.flush()
                await asyncio.sleep(0.02)
                if self._ser.in_waiting:
                    resp = self._ser.readline().decode(errors="replace").strip()
                    self._last_response = resp
                    return resp
            except serial.SerialException as e:
                logger.error("Serial write error: %s", e)
                self._connected = False
                self.schedule_reconnect()
        return None

    # ── Public API ────────────────────────────────────────────────────────────
    async def ping(self) -> bool:
        resp = await self._send_raw("PING\n")
        return resp == "PONG"

    async def set_motors(self, left: int, right: int) -> bool:
        """Send M:left,right where each value is -255..255."""
        left  = max(-255, min(255, int(left)))
        right = max(-255, min(255, int(right)))
        resp = await self._send_raw(f"M:{left},{right}\n")
        return resp == "OK:M"

    async def emergency_stop(self) -> bool:
        resp = await self._send_raw("E\n")
        return resp == "OK:ESTOP"

    async def get_status(self) -> dict:
        resp = await self._send_raw("STATUS\n")
        result = {"connected": self._connected, "left": 0, "right": 0}
        if resp and resp.startswith("OK:STATUS:"):
            parts = resp[len("OK:STATUS:"):].split(",")
            if len(parts) == 2:
                result["left"]  = int(parts[0])
                result["right"] = int(parts[1])
        return result

    @property
    def connected(self) -> bool:
        return self._connected
