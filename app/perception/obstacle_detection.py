"""
obstacle_detection.py — Monocular obstacle detection using optical flow + depth heuristics.

Since the rover has only a single CSI camera (no LiDAR, no stereo), we use:
  1. Frame-differencing optical flow to detect motion / looming objects.
  2. Bottom-ROI brightness/edge density as a floor-contact proxy.
  3. A simple MobileNet-SSD detector (optional, runs on Jetson NVDLA if available)
     for identifying furniture legs and walls.

The output is a per-direction threat score: {front, left, right} in 0.0–1.0.
"""
import asyncio
import logging
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from app.config import RoverConfig

logger = logging.getLogger("rover.perception")


class ObstacleDetector:
    def __init__(self, cfg: RoverConfig):
        self.cfg = cfg
        self._prev_gray: Optional[np.ndarray] = None
        self._threats = {"front": 0.0, "left": 0.0, "right": 0.0}
        self._lock = asyncio.Lock()
        self._last_frame_time = 0.0

        # Edge detector
        self._edge_low  = 50
        self._edge_high = 150

    async def update(self, frame: np.ndarray) -> dict:
        """Process a new BGR frame and return updated threat scores."""
        loop = asyncio.get_event_loop()
        threats = await loop.run_in_executor(None, self._process, frame)
        async with self._lock:
            self._threats = threats
        return threats

    def _process(self, frame: np.ndarray) -> dict:
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ── Region of interest: lower 40% of frame ─────────────────────────
        roi_top = int(h * 0.4)
        roi = gray[roi_top:, :]

        left_roi   = roi[:, :w//3]
        centre_roi = roi[:, w//3: 2*w//3]
        right_roi  = roi[:, 2*w//3:]

        threats = {"front": 0.0, "left": 0.0, "right": 0.0}

        # ── Edge density (high density = obstacle close) ───────────────────
        for name, region in [("left", left_roi), ("front", centre_roi), ("right", right_roi)]:
            edges = cv2.Canny(region, self._edge_low, self._edge_high)
            density = np.count_nonzero(edges) / edges.size
            threats[name] = min(1.0, density * 10.0)

        # ── Optical flow: large looming flow in centre = front obstacle ────
        if self._prev_gray is not None:
            try:
                flow = cv2.calcOpticalFlowFarneback(
                    self._prev_gray[roi_top:, w//3:2*w//3],
                    gray[roi_top:,           w//3:2*w//3],
                    None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                mean_flow = float(np.mean(mag))
                # Blend optical-flow score with edge score
                flow_score = min(1.0, mean_flow / 5.0)
                threats["front"] = max(threats["front"], flow_score)
            except cv2.error:
                pass

        self._prev_gray = gray
        self._last_frame_time = time.time()
        return threats

    async def get_threats(self) -> dict:
        async with self._lock:
            return dict(self._threats)

    def is_front_blocked(self, threshold: float = 0.65) -> bool:
        return self._threats.get("front", 0.0) >= threshold

    def is_side_blocked(self, side: str, threshold: float = 0.70) -> bool:
        return self._threats.get(side, 0.0) >= threshold
