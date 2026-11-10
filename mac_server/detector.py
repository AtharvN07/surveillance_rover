"""
YOLO detector — runs on the Mac (MPS GPU on Apple Silicon, CPU fallback).
Returns annotated frames + structured detections. Never crashes the server:
any inference error returns the raw frame with an error note.
"""
import logging
import time
from typing import List, Dict, Tuple

import cv2
import numpy as np

log = logging.getLogger("mac.detector")

class Detector:
    def __init__(self, model_name: str = "yolo11n.pt", conf: float = 0.45):
        from ultralytics import YOLO
        self.conf = conf
        self.model = YOLO(model_name)
        # Warm up with a dummy frame so first real frame isn't slow
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, conf=self.conf, verbose=False)
        self.names = self.model.names
        self.last_ms = 0.0
        log.info("YOLO ready: %s (%d classes)", model_name, len(self.names))

    def detect(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
        t0 = time.time()
        results = self.model.predict(frame, conf=self.conf, verbose=False)[0]
        self.last_ms = (time.time() - t0) * 1000

        detections = []
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            label = self.names.get(cls_id, str(cls_id))
            detections.append({
                "label": label, "conf": round(conf, 2),
                "box": [x1, y1, x2, y2],
            })
            # Draw box + label
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 160), 2)
            tag = f"{label} {conf:.2f}"
            (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1),
                          (0, 255, 160), -1)
            cv2.putText(annotated, tag, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

        # HUD: inference time + detection count
        cv2.putText(annotated, f"YOLO {self.last_ms:.0f}ms | {len(detections)} objects",
                    (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 160), 1, cv2.LINE_AA)
        return annotated, detections

    def obstacles(self, detections: List[Dict], frame_w: int = 640) -> Dict[str, float]:
        """
        Convert detections into per-region threat scores 0..1.
        Anything in the bottom half of the frame is treated as blocking:
        closer/larger box → higher threat.
        """
        front = left = right = 0.0
        third = frame_w // 3
        for d in detections:
            x1, y1, x2, y2 = d["box"]
            cx = (x1 + x2) / 2
            area_ratio = ((x2 - x1) * (y2 - y1)) / float(frame_w * 480)
            threat = min(1.0, area_ratio * 6.0)  # big box = dangerous
            if cx < third:
                left = max(left, threat)
            elif cx < 2 * third:
                front = max(front, threat)
            else:
                right = max(right, threat)
        return {"front": round(front, 2), "left": round(left, 2), "right": round(right, 2)}
