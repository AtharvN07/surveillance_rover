"""
mapping.py — 2D occupancy grid map.

Cells: 0=unknown, 1=free, 2=occupied.
Resolution: metres per cell (default 0.05 m = 5 cm).
Origin is at the map centre.
"""
import json
import logging
import math
import os
import time
from typing import List, Optional, Tuple

import numpy as np

from app.config import RoverConfig

logger = logging.getLogger("rover.mapping")

UNKNOWN  = 0
FREE     = 1
OCCUPIED = 2


class OccupancyGrid:
    def __init__(self, cfg: RoverConfig):
        self.res    = cfg.map_resolution          # m per cell
        self.width  = cfg.map_width_cells         # number of cells
        self.height = cfg.map_height_cells
        self.maps_dir = cfg.maps_dir
        os.makedirs(self.maps_dir, exist_ok=True)

        self._grid = np.zeros((self.height, self.width), dtype=np.uint8)

        # Origin offset (cell coordinates of physical (0,0))
        self.origin_col = self.width  // 2
        self.origin_row = self.height // 2

    # ── Coordinate conversion ─────────────────────────────────────────────────
    def world_to_cell(self, x: float, y: float) -> Tuple[int, int]:
        col = int(round(x / self.res)) + self.origin_col
        row = int(round(y / self.res)) + self.origin_row
        return col, row

    def cell_to_world(self, col: int, row: int) -> Tuple[float, float]:
        x = (col - self.origin_col) * self.res
        y = (row - self.origin_row) * self.res
        return x, y

    def _in_bounds(self, col: int, row: int) -> bool:
        return 0 <= col < self.width and 0 <= row < self.height

    # ── Map updates ───────────────────────────────────────────────────────────
    def mark_free(self, x: float, y: float):
        c, r = self.world_to_cell(x, y)
        if self._in_bounds(c, r) and self._grid[r, c] != OCCUPIED:
            self._grid[r, c] = FREE

    def mark_occupied(self, x: float, y: float):
        c, r = self.world_to_cell(x, y)
        if self._in_bounds(c, r):
            self._grid[r, c] = OCCUPIED

    def ray_cast(self, robot_x: float, robot_y: float,
                 theta: float, max_dist: float, hit: bool):
        """
        Cast a ray from robot pose; mark cells FREE up to max_dist,
        and if hit=True mark the endpoint OCCUPIED.
        """
        steps = int(max_dist / self.res)
        for i in range(1, steps + 1):
            d = i * self.res
            wx = robot_x + d * math.cos(theta)
            wy = robot_y + d * math.sin(theta)
            c, r = self.world_to_cell(wx, wy)
            if not self._in_bounds(c, r):
                break
            if hit and i == steps:
                self._grid[r, c] = OCCUPIED
            elif self._grid[r, c] != OCCUPIED:
                self._grid[r, c] = FREE

    # ── Queries ───────────────────────────────────────────────────────────────
    def is_occupied(self, x: float, y: float) -> bool:
        c, r = self.world_to_cell(x, y)
        return self._in_bounds(c, r) and self._grid[r, c] == OCCUPIED

    def get_cell(self, col: int, row: int) -> int:
        if self._in_bounds(col, row):
            return int(self._grid[row, col])
        return UNKNOWN

    def frontier_cells(self) -> List[Tuple[int, int]]:
        """Return (col, row) cells that are FREE and adjacent to UNKNOWN."""
        frontiers = []
        for r in range(1, self.height - 1):
            for c in range(1, self.width - 1):
                if self._grid[r, c] != FREE:
                    continue
                neighbours = [
                    self._grid[r-1, c], self._grid[r+1, c],
                    self._grid[r, c-1], self._grid[r, c+1],
                ]
                if UNKNOWN in neighbours:
                    frontiers.append((c, r))
        return frontiers

    # ── Persistence ───────────────────────────────────────────────────────────
    def save_map(self, name: str) -> str:
        path = os.path.join(self.maps_dir, f"{name}.json")
        data = {
            "ts":          time.time(),
            "res":         self.res,
            "width":       self.width,
            "height":      self.height,
            "origin_col":  self.origin_col,
            "origin_row":  self.origin_row,
            "grid":        self._grid.tolist(),
        }
        with open(path, "w") as f:
            json.dump(data, f)
        logger.info("Map saved to %s", path)
        return path

    def load_map(self, name: str) -> bool:
        path = os.path.join(self.maps_dir, f"{name}.json")
        if not os.path.exists(path):
            return False
        with open(path) as f:
            data = json.load(f)
        self._grid      = np.array(data["grid"], dtype=np.uint8)
        self.res        = data["res"]
        self.width      = data["width"]
        self.height     = data["height"]
        self.origin_col = data["origin_col"]
        self.origin_row = data["origin_row"]
        logger.info("Map loaded from %s", path)
        return True

    def get_map_json(self) -> dict:
        """Return a compact JSON-serialisable map dict for the dashboard."""
        # Downsample for bandwidth: every 4th cell
        step = 4
        small = self._grid[::step, ::step]
        return {
            "width":      small.shape[1],
            "height":     small.shape[0],
            "resolution": self.res * step,
            "cells":      small.flatten().tolist(),
            "origin_col": self.origin_col // step,
            "origin_row": self.origin_row // step,
        }
