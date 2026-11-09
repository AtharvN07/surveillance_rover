"""
localization.py — Fuses wheel odometry and visual odometry for pose estimation.

Without an IMU or encoder ticks we rely on:
  1. Wheel odometry from PWM-based DifferentialDrive model (dead reckoning).
  2. Visual odometry scale-corrected by the wheel model.

The EKF here is intentionally simple — a full particle filter or graph-SLAM
would be better but requires significantly more CPU on the Jetson Nano.
"""
import math
import logging
import numpy as np
from typing import Optional, Tuple

logger = logging.getLogger("rover.localization")


class PoseEstimator:
    """
    Simple fused pose estimator.
    State: [x, y, theta]
    """

    def __init__(self):
        self.x     = 0.0
        self.y     = 0.0
        self.theta = 0.0

        # EKF covariance
        self._P = np.eye(3) * 0.01

        # Process noise
        self._Q = np.diag([0.01, 0.01, 0.005])

        # Observation noise (visual odometry, less reliable)
        self._R_vo = np.diag([0.05, 0.05, 0.02])

    def predict(self, dx: float, dy: float, dtheta: float):
        """Update pose from wheel odometry delta."""
        cos_t = math.cos(self.theta)
        sin_t = math.sin(self.theta)
        self.x     += cos_t * dx - sin_t * dy
        self.y     += sin_t * dx + cos_t * dy
        self.theta  = math.atan2(
            math.sin(self.theta + dtheta),
            math.cos(self.theta + dtheta),
        )
        # Jacobian of motion model
        F = np.array([
            [1, 0, -sin_t * dx - cos_t * dy],
            [0, 1,  cos_t * dx - sin_t * dy],
            [0, 0,  1],
        ])
        self._P = F @ self._P @ F.T + self._Q

    def update_vo(self, vo_dx: float, vo_dy: float, vo_dtheta: float,
                  scale: float = 1.0):
        """
        Correct with visual odometry observation.
        scale: estimated metres per VO unit (tuned empirically).
        """
        z = np.array([vo_dx * scale, vo_dy * scale, vo_dtheta])
        h = np.array([self.x, self.y, self.theta])
        y = z - h
        y[2] = math.atan2(math.sin(y[2]), math.cos(y[2]))  # angle wrap

        S   = self._P + self._R_vo
        K   = self._P @ np.linalg.inv(S)
        correction = K @ y
        self.x     += correction[0]
        self.y     += correction[1]
        self.theta  = math.atan2(
            math.sin(self.theta + correction[2]),
            math.cos(self.theta + correction[2]),
        )
        self._P = (np.eye(3) - K) @ self._P

    def reset(self):
        self.x = self.y = self.theta = 0.0
        self._P = np.eye(3) * 0.01

    @property
    def pose(self) -> dict:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "theta": round(self.theta, 4),
            "theta_deg": round(math.degrees(self.theta), 2),
        }
