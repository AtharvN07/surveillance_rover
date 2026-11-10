"""
Mac Rover Server — configuration.
Override with environment variables if needed:
  export JETSON_URL=http://192.168.31.122:8000
"""
import os
from dataclasses import dataclass

@dataclass
class Config:
    jetson_url: str   = os.getenv("JETSON_URL", "http://192.168.31.122:8000")
    yolo_model: str   = os.getenv("YOLO_MODEL", "yolo11n.pt")  # nano: fastest, works on CPU
    yolo_conf: float  = float(os.getenv("YOLO_CONF", "0.45"))
    host: str         = os.getenv("HOST", "0.0.0.0")
    port: int         = int(os.getenv("PORT", "9000"))
    jpeg_quality: int = int(os.getenv("JPEG_QUALITY", "75"))

cfg = Config()
