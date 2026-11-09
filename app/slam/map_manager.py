"""
map_manager.py — Top-level SLAM coordinator.
Ties together OccupancyGrid, PoseEstimator, ObstacleDetector, and VisualOdometry.
Called once per camera frame from the main control loop.
"""
import asyncio
import logging
import math
from typing import Optional

import numpy as np

from app.slam.mapping import OccupancyGrid
from app.slam.localization import PoseEstimator
from app.perception.obstacle_detection import ObstacleDetector
from app.perception.visual_odometry import VisualOdometry
from app.config import RoverConfig

logger = logging.getLogger("rover.slam")


class SlamManager:
    def __init__(self, cfg: RoverConfig):
        self.cfg        = cfg
        self.map        = OccupancyGrid(cfg)
        self.pose_est   = PoseEstimator()
        self.obstacle   = ObstacleDetector(cfg)
        self.vo         = VisualOdometry(cfg.camera_width, cfg.camera_height)
        self._lock      = asyncio.Lock()

    async def process_frame(self, frame: np.ndarray,
                            wheel_dx: float, wheel_dy: float, wheel_dtheta: float):
        """
        Process one camera frame alongside wheel odometry deltas.
        Updates the map and pose estimate.
        """
        # 1. Update pose from wheel odometry (dead reckoning)
        self.pose_est.predict(wheel_dx, wheel_dy, wheel_dtheta)

        # 2. Run obstacle detection
        threats = await self.obstacle.update(frame)

        # 3. Visual odometry (CPU, best-effort)
        import cv2
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        vo_result = self.vo.process(gray)
        if vo_result is not None:
            vdx, vdy, vdtheta = vo_result
            self.pose_est.update_vo(vdx, vdy, vdtheta, scale=0.1)

        # 4. Update map from pose + obstacle threats
        pose = self.pose_est.pose
        px, py, ptheta = pose["x"], pose["y"], pose["theta"]

        async with self._lock:
            # Mark current cell free
            self.map.mark_free(px, py)

            # Ray-cast obstacle info from threat scores
            # Front ray
            front_dist = 0.8 - threats["front"] * 0.6  # 0.2..0.8 m
            self.map.ray_cast(px, py, ptheta,
                              front_dist, hit=threats["front"] > 0.6)

            # Side rays (±45°)
            left_dist  = 0.8 - threats["left"]  * 0.5
            right_dist = 0.8 - threats["right"] * 0.5
            self.map.ray_cast(px, py, ptheta + math.radians(45),
                              left_dist,  hit=threats["left"]  > 0.65)
            self.map.ray_cast(px, py, ptheta - math.radians(45),
                              right_dist, hit=threats["right"] > 0.65)

        return threats

    def get_map_json(self) -> dict:
        return self.map.get_map_json()

    def save_map(self, name: str) -> str:
        return self.map.save_map(name)

    def load_map(self, name: str) -> bool:
        return self.map.load_map(name)

    @property
    def pose(self) -> dict:
        return self.pose_est.pose
