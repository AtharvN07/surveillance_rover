"""
camera.py — Non-blocking CSI/USB camera capture for the Jetson Nano.
IMX219 CSI camera on /dev/video0 via GStreamer nvarguscamerasrc.
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
    """GStreamer pipeline for Jetson Nano IMX219 CSI camera."""
    return (
        f"nvarguscamerasrc sensor-id=0 ! "
        f"video/x-raw(memory:NVMM), "
        f"width=(int){cfg.camera_width}, height=(int){cfg.camera_height}, "
        f"format=(string)NV12, framerate=(fraction){cfg.camera_fps}/1 ! "
        f"nvvidconv flip-method={cfg.camera_flip} ! "
        f"video/x-raw, width=(int){cfg.camera_width}, height=(int){cfg.camera_height}, "
        f"format=(string)BGRx ! "
        f"videoconvert ! "
        f"video/x-raw, format=(string)BGR ! "
        f"appsink max-buffers=1 drop=true sync=false"
    )


def _v4l2_pipeline(cfg: RoverConfig) -> str:
    """Fallback: open /dev/video0 directly via V4L2 (no GStreamer needed)."""
    return f"v4l2src device=/dev/video0 ! video/x-raw,width={cfg.camera_width},height={cfg.camera_height},framerate={cfg.camera_fps}/1 ! videoconvert ! appsink max-buffers=1 drop=true sync=false"


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
        # Try 1: GStreamer CSI pipeline (best quality, hardware accelerated)
        if self.cfg.use_csi:
            pipeline = _gstreamer_pipeline(self.cfg)
            logger.info("Trying GStreamer CSI pipeline...")
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    self._cap = cap
                    logger.info("CSI camera opened via GStreamer")
                    return True
                cap.release()
            logger.warning("GStreamer CSI failed, trying V4L2 direct...")

        # Try 2: Direct V4L2 /dev/video0 (works for CSI exposed as V4L2)
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.cfg.camera_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.camera_height)
        cap.set(cv2.CAP_PROP_FPS,          self.cfg.camera_fps)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                self._cap = cap
                logger.info("Camera opened via V4L2 /dev/video0")
                return True
            cap.release()

        # Try 3: OpenCV default fallback
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                self._cap = cap
                logger.info("Camera opened via OpenCV default")
                return True
            cap.release()

        logger.error("All camera open attempts failed")
        return False

    async def _capture_loop(self):
        loop = asyncio.get_event_loop()
        if not self._open_camera():
            return

        fps_counter = 0
        fps_start = time.time()

        while self._running:
            ret, frame = await loop.run_in_executor(None, self._cap.read)
            if not ret or frame is None:
                logger.warning("Camera read failed — retrying in 0.5s")
                await asyncio.sleep(0.5)
                # Attempt reopen
                self._cap.release()
                if not self._open_camera():
                    break
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
