"""
telemetry.py — Collects system metrics for the telemetry WebSocket feed.
"""
import asyncio
import logging
import time
from typing import Optional

import psutil

from app.config import RoverConfig
from app.hardware.arduino import ArduinoInterface
from app.hardware.camera import CameraStream

logger = logging.getLogger("rover.telemetry")


class TelemetryCollector:
    def __init__(self, arduino: ArduinoInterface, camera: CameraStream, cfg: RoverConfig):
        self.arduino = arduino
        self.camera  = camera
        self.cfg     = cfg
        self._cache  = {}
        self._last_collect = 0.0

    async def collect(self) -> dict:
        now = time.time()
        # Rate-limit expensive psutil calls
        if now - self._last_collect > 0.5:
            arduino_status = await self.arduino.get_status()
            cpu    = psutil.cpu_percent(interval=None)
            mem    = psutil.virtual_memory()
            try:
                temp_c = self._jetson_temp()
            except Exception:
                temp_c = None

            self._cache = {
                "type":            "telemetry",
                "ts":              now,
                "arduino_connected": arduino_status.get("connected", False),
                "motor_left":      arduino_status.get("left", 0),
                "motor_right":     arduino_status.get("right", 0),
                "camera_connected": self.camera.connected,
                "camera_fps":      self.camera.fps,
                "cpu_pct":         cpu,
                "ram_pct":         mem.percent,
                "ram_used_mb":     round(mem.used / 1e6),
                "temp_c":          temp_c,
            }
            self._last_collect = now
        return self._cache

    @staticmethod
    def _jetson_temp() -> Optional[float]:
        """Read Jetson SoC temperature from sysfs."""
        with open("/sys/devices/virtual/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
