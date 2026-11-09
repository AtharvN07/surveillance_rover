"""
motor_interface.py — High-level differential-drive motor commands.
Converts joystick (x, y) pairs into left/right PWM values.
"""
import math
from app.config import RoverConfig


class MotorInterface:
    """Translates joystick inputs to left/right PWM for differential drive."""

    def __init__(self, cfg: RoverConfig):
        self.cfg = cfg

    def joystick_to_motors(self, x: float, y: float) -> tuple[int, int]:
        """
        Convert analogue joystick (-1..1) to (left, right) PWM (-255..255).
        x: lateral (positive = right turn)
        y: longitudinal (positive = forward)
        Dead-zone applied before mapping.
        """
        dz = self.cfg.deadzone
        if abs(x) < dz:
            x = 0.0
        else:
            x = math.copysign((abs(x) - dz) / (1.0 - dz), x)

        if abs(y) < dz:
            y = 0.0
        else:
            y = math.copysign((abs(y) - dz) / (1.0 - dz), y)

        # Mix: forward component + turn component
        left  = y + x
        right = y - x

        # Normalise so neither exceeds 1.0
        max_val = max(abs(left), abs(right), 1.0)
        left  /= max_val
        right /= max_val

        scale = self.cfg.max_speed
        return (int(left * scale), int(right * scale))

    def differential_to_motors(self, linear: float, angular: float) -> tuple[int, int]:
        """
        Convert linear (m/s) and angular (rad/s) velocity commands to PWM.
        Used by autonomous navigation.
        linear:  -1..1 (normalised)
        angular: -1..1 (positive = left turn)
        """
        left  = linear - angular
        right = linear + angular
        max_val = max(abs(left), abs(right), 1.0)
        left  /= max_val
        right /= max_val
        scale = self.cfg.max_speed
        return (int(left * scale), int(right * scale))
