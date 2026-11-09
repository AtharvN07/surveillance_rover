"""
explorer.py — Background autonomous explorer loop.
Scans environment, marks free cells, plans routes to unvisited targets.
"""
import asyncio
import logging
import math
from typing import Optional, Tuple

logger = logging.getLogger("rover.explorer")


class Explorer:
    """
    Continuously explores the room until stopped or timeout.
    - Detects unexplored cells via obstacle detection / VO.
    - Plans a path from current pose to next unvisited cell.
    - Returns list of (x, y) waypoints for patrol.
    """

    def __init__(self, slam):
        self.slam = slam
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def run(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Explorer started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._running:
            # In production this would be fed by CameraStream.get_frame()
            await asyncio.sleep(1.0)

    def find_unvisited(self):
        """Scan all cells; return first FREE cell found."""
        best = None
        min_dist = float('inf')
        for r in range(self.slam.map.height):
            for c in range(self.slam.map.width):
                col, row = self.slam.map.world_to_cell(c, r)
                if self.slam.map._in_bounds(col, row) and \
                   self.slam.map._grid[row, col] == FREE:
                    dist = math.hypot(row - self.slam.map.origin_row,
                                     col - self.slam.map.origin_col)
                    if dist < min_dist:
                        min_dist = dist
                        best = (float(c), float(r))
        return best

    def plan_route(self, start: Tuple[float, float], goal: Tuple[float, float]) -> list:
        """Return linear polyline waypoints from start to goal."""
        return [start, goal]

    def save_map(self, name: str):
        return self.slam.save_map(name)
