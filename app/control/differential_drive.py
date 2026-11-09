"""
differential_drive.py — Kinematic model for the two-wheel differential drive rover.
Converts velocity commands to per-wheel speeds and tracks odometry.
"""
import math
import time


class DifferentialDrive:
    """
    Simple differential-drive kinematic model.
    Wheel base (track width) and wheel radius are in metres.
    Integrates wheel velocities to produce (x, y, theta) odometry.
    """

    def __init__(self, wheel_base: float = 0.20, wheel_radius: float = 0.033):
        self.wheel_base   = wheel_base    # distance between drive wheels (m)
        self.wheel_radius = wheel_radius  # wheel radius (m)

        # Odometry state
        self.x     = 0.0   # metres
        self.y     = 0.0   # metres
        self.theta = 0.0   # radians (CCW positive)

        self._last_time = time.monotonic()

    def reset_odometry(self):
        self.x = self.y = self.theta = 0.0
        self._last_time = time.monotonic()

    def update(self, left_pwm: int, right_pwm: int, max_pwm: int = 220):
        """
        Integrate odometry given current PWM values.
        PWM is used as a proxy for wheel velocity (linear mapping).
        Call this at a fixed rate (e.g. 20 Hz) for accurate odometry.
        """
        now  = time.monotonic()
        dt   = now - self._last_time
        self._last_time = now

        # Approximate wheel velocities (m/s) from PWM fraction
        # Tune MAX_WHEEL_SPEED to match your actual motor speed at full PWM
        MAX_WHEEL_SPEED = 0.35  # m/s at PWM=220

        vl = (left_pwm  / max_pwm) * MAX_WHEEL_SPEED
        vr = (right_pwm / max_pwm) * MAX_WHEEL_SPEED

        v_centre = (vr + vl) / 2.0
        omega    = (vr - vl) / self.wheel_base

        # Integrate pose
        self.x     += v_centre * math.cos(self.theta) * dt
        self.y     += v_centre * math.sin(self.theta) * dt
        self.theta += omega * dt
        self.theta  = math.atan2(math.sin(self.theta), math.cos(self.theta))  # wrap

    @property
    def pose(self) -> dict:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "theta": round(self.theta, 4),
            "theta_deg": round(math.degrees(self.theta), 2),
        }
