"""
config.py — Mac server configuration.
Edit JETSON_IP to match your Jetson's IP address.
"""
import os
from dataclasses import dataclass

@dataclass
class Config:
    # ── Jetson connection ─────────────────────────────────────────────────
    jetson_ip: str   = os.getenv("JETSON_IP",   "192.168.31.122")
    jetson_port: int = int(os.getenv("JETSON_PORT", "8000"))

    # ── YOLO ──────────────────────────────────────────────────────────────
    # yolo11n.pt = nano (fastest), yolo11s.pt = small, yolo11m.pt = medium
    yolo_model: str  = os.getenv("YOLO_MODEL",  "yolo11n.pt")
    confidence: float = float(os.getenv("YOLO_CONF", "0.45"))

    # ── Mac server ────────────────────────────────────────────────────────
    host: str        = os.getenv("HOST",         "0.0.0.0")
    port: int        = int(os.getenv("PORT",     "9000"))
    stream_quality: int     = int(os.getenv("STREAM_QUALITY",  "75"))
    stream_fps_max: int     = int(os.getenv("STREAM_FPS_MAX",  "25"))

    @property
    def jetson_url(self) -> str:
        return f"http://{self.jetson_ip}:{self.jetson_port}"

    @property
    def jetson_stream_url(self) -> str:
        return f"{self.jetson_url}/api/camera/stream"

    @property
    def jetson_ws_url(self) -> str:
        return f"ws://{self.jetson_ip}:{self.jetson_port}/socket.io/?EIO=4&transport=websocket"


cfg = Config()
