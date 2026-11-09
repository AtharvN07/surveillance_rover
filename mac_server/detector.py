"""
detector.py — YOLO object detection wrapper using Ultralytics.
Runs on Mac CPU/MPS (Apple Silicon GPU automatically used if available).
"""
import logging
import time
from typing import List, Tuple, Dict

import cv2
import numpy as np

log = logging.getLogger("mac.detector")

# COCO class colours — consistent colour per class ID
COLOURS = [
    (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
    (207, 210, 49), (72, 249, 10),  (146, 204, 23), (61, 219, 134),
    (26, 147, 52),  (0, 212, 187),  (44, 153, 168), (0, 194, 255),
    (52, 69, 147),  (100, 115, 255),(0, 24, 236),   (132, 56, 255),
    (82, 0, 133),   (203, 56, 255), (255, 149, 200),(255, 55, 199),
]

def class_colour(cid: int) -> Tuple[int,int,int]:
    return COLOURS[cid % len(COLOURS)]


class Detector:
    def __init__(self, model_name: str = "yolo11n.pt", confidence: float = 0.45):
        from ultralytics import YOLO
        log.info("Loading YOLO model: %s", model_name)
        self.model = YOLO(model_name)
        self.conf  = confidence
        self.names = self.model.names
        # Warm up
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        self.model(dummy, verbose=False)
        log.info("YOLO ready — %d classes, device: %s",
                 len(self.names), self.model.device)

    def detect(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
        """
        Run inference on a BGR frame.
        Returns (annotated_frame, detections).
        detections = [{"label": str, "conf": float, "box": [x1,y1,x2,y2]}]
        """
        t0 = time.perf_counter()
        results = self.model(frame, conf=self.conf, verbose=False)[0]
        ms = (time.perf_counter() - t0) * 1000

        annotated = frame.copy()
        dets = []

        if results.boxes is not None:
            for box in results.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cid  = int(box.cls[0])
                conf = float(box.conf[0])
                label = self.names[cid]
                colour = class_colour(cid)

                # Bounding box
                cv2.rectangle(annotated, (x1, y1), (x2, y2), colour, 2)

                # Label background
                text = f"{label} {conf:.2f}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
                cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), colour, -1)
                cv2.putText(annotated, text, (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1, cv2.LINE_AA)

                dets.append({"label": label, "conf": round(conf, 3),
                             "box": [x1, y1, x2, y2]})

        # Inference time HUD
        cv2.putText(annotated, f"YOLO {ms:.0f}ms", (6, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 160), 1, cv2.LINE_AA)

        return annotated, dets
