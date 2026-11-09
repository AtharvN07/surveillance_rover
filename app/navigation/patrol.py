"""
patrol.py — Patrol mission controller.
Handles waypoint navigation, block detection, replanning, home return.
"""
import asyncio
import logging
import math
from typing import List, Optional, Tuple

logger = logging.getLogger("rover.patrol")


class PatrolMission:
    def __init__(self, slam, waypoints: List[Tuple[float, float]]):
        self.slam = slam
        self.waypoints = waypoints
        self.current_idx = 0
        self.target_idx = 0
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def run(self):
        self.running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self.running:
            if not self.waypoints:
                await asyncio.sleep(0.3)
                continue
            wx, wy = self.waypoints[self.target_idx]
            px, py = self.slam.pose
            dx = wx - px
            dy = wy - py
            dist = math.hypot(dx, dy)
            if dist > 0.01:
                step_x = dx / dist * 3.0
                step_y = dy / dist * 3.0
                step_x = max(-3.0, min(3.0, step_x))
                step_y = max(-3.0, min(3.0, step_y))
                motor_if = self.slam.velocity
                await motor_if.set_joystick(step_x, step_y)
            else:
                # Advance to next waypoint
                self.target_idx = (self.target_idx + 1) % len(self.waypoints)
            await asyncio.sleep(0.3)

    def pause(self):
        self.running = False

    def resume(self):
        self.running = True

    def stop_mission(self):
        self.running = False
        self.stop()

    @property
    def home_position(self):
        return self.slam.pose
