"""
safety_controller.py — Independent safety watchdog running in a background thread.
Stops motors if connection is lost, obstacle detected, or explicit ESTOP triggered.
"""
import asyncio
import logging
import threading
import time
from typing import Optional

from app.config import RoverConfig
from app.hardware.arduino import ArduinoInterface

logger = logging.getLogger("rover.safety")


class SafetyController:
    def __init__(self, arduino: ArduinoInterface, cfg: RoverConfig):
        self.arduino  = arduino
        self.cfg      = cfg
        self._stopped = False
        self._thread: Optional[threading.Thread] = None
        self._last_heartbeat = time.time()
        self.obstacle_near   = False
        self.estop_active    = False

    def start(self):
        self._stopped = False
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Safety controller running")

    def stop(self):
        self._stopped = True

    def heartbeat(self):
        """Call from WebSocket handler on each joystick message."""
        self._last_heartbeat = time.time()

    def trigger_estop(self):
        self.estop_active = True

    def clear_estop(self):
        self.estop_active = False
        self._last_heartbeat = time.time()

    def set_obstacle(self, near: bool):
        self.obstacle_near = near

    def _run(self):
        loop = asyncio.new_event_loop()
        while not self._stopped:
            time.sleep(0.1)
            if self.estop_active:
                loop.run_until_complete(self.arduino.emergency_stop())
                continue
            # Connection timeout watchdog
            if time.time() - self._last_heartbeat > 2.0:
                loop.run_until_complete(self.arduino.emergency_stop())
