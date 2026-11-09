"""
config.py — Central configuration for the Surveillance Rover system.
All tunables live here; override via environment variables or config/rover.env.
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RoverConfig:
    # ── Arduino serial ────────────────────────────────────────────────────────
    arduino_port: str = os.getenv("ARDUINO_PORT", "/dev/ttyACM0")
    arduino_baud: int = int(os.getenv("ARDUINO_BAUD", "115200"))
    arduino_timeout: float = float(os.getenv("ARDUINO_TIMEOUT", "0.1"))
    arduino_watchdog_ms: int = int(os.getenv("ARDUINO_WATCHDOG_MS", "500"))

    # ── Camera ────────────────────────────────────────────────────────────────
    camera_width: int = int(os.getenv("CAMERA_WIDTH", "640"))
    camera_height: int = int(os.getenv("CAMERA_HEIGHT", "480"))
    camera_fps: int = int(os.getenv("CAMERA_FPS", "30"))
    camera_flip: int = int(os.getenv("CAMERA_FLIP", "0"))   # 0=none,1=H,2=V,3=both
    use_csi: bool = os.getenv("USE_CSI", "true").lower() == "true"

    # ── Motor control ─────────────────────────────────────────────────────────
    max_speed: int = int(os.getenv("MAX_SPEED", "220"))       # 0-255 PWM
    accel_step: int = int(os.getenv("ACCEL_STEP", "12"))
    deadzone: float = float(os.getenv("DEADZONE", "0.05"))    # joystick fraction

    # ── Networking ────────────────────────────────────────────────────────────
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    cors_origins: list = field(default_factory=lambda: ["*"])

    # ── Streaming ────────────────────────────────────────────────────────────
    stream_quality: int = int(os.getenv("STREAM_QUALITY", "75"))  # JPEG quality
    stream_fps_max: int = int(os.getenv("STREAM_FPS_MAX", "30"))

    # ── SLAM ──────────────────────────────────────────────────────────────────
    map_resolution: float = float(os.getenv("MAP_RESOLUTION", "0.05"))  # m/cell
    map_width_cells: int = int(os.getenv("MAP_WIDTH_CELLS", "400"))
    map_height_cells: int = int(os.getenv("MAP_HEIGHT_CELLS", "400"))
    maps_dir: str = os.getenv("MAPS_DIR", "maps")

    # ── Safety ────────────────────────────────────────────────────────────────
    obstacle_stop_dist_m: float = float(os.getenv("OBSTACLE_STOP_DIST", "0.3"))
    obstacle_slow_dist_m: float = float(os.getenv("OBSTACLE_SLOW_DIST", "0.6"))


config = RoverConfig()
