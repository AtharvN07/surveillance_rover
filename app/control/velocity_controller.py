"""
velocity_controller.py — Smooth velocity command shaping with acceleration limits.
Sits between the navigation / joystick layer and the Arduino motor interface.
"""
import asyncio
import logging
import time
from typing import Optional

from app.config import RoverConfig
from app.hardware.arduino import ArduinoInterface
from app.hardware.motor_interface import MotorInterface
from app.control.differential_drive import DifferentialDrive

logger = logging.getLogger("rover.velocity")


class VelocityController:
    """
    Accepts target (left, right) PWM pairs and forwards them to the Arduino.
    Keeps a shadow copy of the last commanded speeds for telemetry.
    The Arduino firmware already does hardware ramping, so this layer
    handles higher-level concerns: mode arbitration, safety interlocks, etc.
    """

    def __init__(self, arduino: ArduinoInterface, cfg: RoverConfig):
        self.arduino  = arduino
        self.cfg      = cfg
        self.motor_if = MotorInterface(cfg)
        self.odometry = DifferentialDrive()

        self._left  = 0
        self._right = 0
        self._stopped = False
        self._lock = asyncio.Lock()

    async def set_joystick(self, x: float, y: float):
        """Accept joystick input and drive motors."""
        left, right = self.motor_if.joystick_to_motors(x, y)
        await self._apply(left, right)

    async def set_velocity(self, linear: float, angular: float):
        """Accept normalised linear/angular commands from navigation."""
        left, right = self.motor_if.differential_to_motors(linear, angular)
        await self._apply(left, right)

    async def stop(self):
        await self._apply(0, 0)

    async def emergency_stop(self):
        self._stopped = True
        await self.arduino.emergency_stop()
        self._left = self._right = 0

    async def resume(self):
        self._stopped = False

    async def _apply(self, left: int, right: int):
        if self._stopped:
            return
        async with self._lock:
            self._left  = left
            self._right = right
            await self.arduino.set_motors(left, right)
            self.odometry.update(left, right, self.cfg.max_speed)

    @property
    def current_speeds(self) -> tuple[int, int]:
        return self._left, self._right

    @property
    def pose(self) -> dict:
        return self.odometry.pose
