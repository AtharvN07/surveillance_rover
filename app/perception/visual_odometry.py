"""
visual_odometry.py — Lightweight monocular visual odometry using ORB features.

Computes frame-to-frame rotation/translation estimates.
Returns a normalised (dx, dy, dtheta) motion estimate per frame pair.

IMPORTANT: Monocular VO cannot recover absolute scale without additional
information (wheel encoders or known object dimensions). The output here is
scale-normalised and should be fused with wheel odometry for metric accuracy.
"""
import logging
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("rover.vo")


class VisualOdometry:
    def __init__(self, width: int = 640, height: int = 480):
        self.w = width
        self.h = height

        # ORB feature detector (fast, works on Jetson CPU)
        self._orb = cv2.ORB_create(nfeatures=500)
        self._bf  = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        self._prev_gray: Optional[np.ndarray] = None
        self._prev_kp = None
        self._prev_des = None

        # Approximate camera intrinsics for a 640×480 CSI camera
        fx = fy = 500.0
        cx, cy = width / 2, height / 2
        self.K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)

    def process(self, gray: np.ndarray) -> Optional[Tuple[float, float, float]]:
        """
        Process a grayscale frame.
        Returns (dx, dy, dtheta) in normalised units, or None if insufficient features.
        """
        kp, des = self._orb.detectAndCompute(gray, None)
        result = None

        if self._prev_des is not None and des is not None and len(des) > 20:
            try:
                matches = self._bf.match(self._prev_des, des)
                matches = sorted(matches, key=lambda m: m.distance)[:100]

                pts1 = np.float32([self._prev_kp[m.queryIdx].pt for m in matches])
                pts2 = np.float32([kp[m.trainIdx].pt for m in matches])

                E, mask = cv2.findEssentialMat(pts1, pts2, self.K,
                                               method=cv2.RANSAC, prob=0.999, threshold=1.0)
                if E is not None and mask is not None and mask.sum() > 10:
                    _, R, t, _ = cv2.recoverPose(E, pts1, pts2, self.K, mask=mask)
                    # Extract yaw from rotation matrix
                    dtheta = float(np.arctan2(R[1, 0], R[0, 0]))
                    # t is unit-scale; use magnitude as proxy for forward motion
                    dx = float(t[2])   # forward
                    dy = float(t[0])   # lateral
                    result = (dx, dy, dtheta)
            except cv2.error as e:
                logger.debug("VO error: %s", e)

        self._prev_gray = gray
        self._prev_kp   = kp
        self._prev_des  = des
        return result
