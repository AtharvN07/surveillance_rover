"""
camera.py — Non-blocking CSI/USB camera capture for the Jetson Nano.
Provides async frame access and MJPEG byte generation for streaming.
"""
import asyncio
import logging
import time
from typing import Optional

import cv2
import numpy as np

from app.config import RoverConfig

logger = logging.getLogger("rover.camera")


def _gstreamer_pipeline(cfg: RoverConfig) -> str:
    """GStreamer pipeline string for the Jetson CSI camera."""
    return (
        f"nvarguscamerasrc sensor-id=0 ! "
        f"video/x-raw(memory:NVMM),width={cfg.camera_width},height={cfg.camera_height},"
        f"format=NV12,framerate={cfg.camera_fps}/1 ! "
        f"nvvidconv flip-method={cfg.camera_flip} ! "
        f"video/x-raw,width={cfg.camera_width},height={cfg.camera_height},format=BGRx ! "
        f"videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
    )


class CameraStream:
    def __init__(self, cfg: RoverConfig):
        self.cfg = cfg
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._frame_time: float = 0.0
        self._fps: float = 0.0
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._capture_loop())
        logger.info("Camera capture loop started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        if self._cap and self._cap.isOpened():
            self._cap.release()
        logger.info("Camera stopped")

    def _open_camera(self) -> bool:
        if self.cfg.use_csi:
            pipeline = _gstreamer_pipeline(self.cfg)
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            cap = cv2.VideoCapture(0)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.cfg.camera_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.camera_height)
            cap.set(cv2.CAP_PROP_FPS,          self.cfg.camera_fps)

        if cap.isOpened():
            self._cap = cap
            return True
        logger.error("Failed to open camera")
        return False

    async def _capture_loop(self):
        loop = asyncio.get_event_loop()
        if not self._open_camera():
            return

        fps_counter = 0
        fps_start = time.time()

        while self._running:
            ret, frame = await loop.run_in_executor(None, self._cap.read)
            if not ret:
                logger.warning("Camera read failed — retrying")
                await asyncio.sleep(0.1)
                continue

            async with self._lock:
                self._frame = frame
                self._frame_time = time.time()

            fps_counter += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                self._fps = fps_counter / elapsed
                fps_counter = 0
                fps_start = time.time()

            # Yield control without sleeping to maximise capture rate
            await asyncio.sleep(0)

    async def get_frame(self) -> Optional[np.ndarray]:
        async with self._lock:
            return self._frame.copy() if self._frame is not None else None

    async def get_jpeg(self, quality: int = 75) -> Optional[bytes]:
        frame = await self.get_frame()
        if frame is None:
            return None
        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return bytes(buf) if ret else None

    async def stream_generator(self):
        """Yields MJPEG boundary frames for HTTP streaming."""
        while True:
            jpg = await self.get_jpeg(self.cfg.stream_quality)
            if jpg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                )
            await asyncio.sleep(1.0 / self.cfg.stream_fps_max)

    @property
    def fps(self) -> float:
        return round(self._fps, 1)

    @property
    def connected(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
