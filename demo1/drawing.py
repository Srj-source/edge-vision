# drawing.py
"""All OpenCV drawing helpers for the annotated video feed."""
from __future__ import annotations

from typing import Dict, List, Optional

import cv2
import numpy as np

from config import CLASS_COLORS_BGR, Config

FONT = cv2.FONT_HERSHEY_SIMPLEX


def _color_for(cls_name: str):
    return CLASS_COLORS_BGR.get(cls_name, CLASS_COLORS_BGR["Unknown"])


def _text_color(bgr):
    b, g, r = bgr
    luminance = 0.114 * b + 0.587 * g + 0.299 * r
    return (0, 0, 0) if luminance > 140 else (255, 255, 255)


def blend_rect(img, pt1, pt2, color, alpha=0.55):
    overlay = img.copy()
    cv2.rectangle(overlay, pt1, pt2, color, -1)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)


# --------------------------------------------------------------------------
def draw_tracks(frame, detections: List[dict]) -> None:
    """Draw a bounding box + label for every tracked vehicle."""
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        color = _color_for(det["cls_name"])
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        speed = det.get("speed")
        speed_txt = f"{speed:4.0f}km/h" if speed is not None else " -- km/h"
        label = (f"#{det['id']} {det['cls_name']} "
                 f"{speed_txt} {det['conf']:.2f}")

        (tw, th), _ = cv2.getTextSize(label, FONT, 0.5, 1)
        top = max(0, y1 - th - 10)
        blend_rect(frame, (x1, top), (x1 + tw + 8, y1), color, 0.85)
        cv2.putText(frame, label, (x1 + 4, y1 - 5),
                    FONT, 0.5, _text_color(color), 1, cv2.LINE_AA)

        # centroid marker (the point used for speed estimation)
        cv2.circle(frame, (int(det["cx"]), int(det["cy"])), 3, color, -1)


# --------------------------------------------------------------------------
def draw_counting_line(frame, counter, cfg: Config) -> None:
    h, w = frame.shape[:2]
    y = counter.line_y(h)
    cv2.line(frame, (0, y), (w, y), (0, 255, 255), 2)
    txt = f"COUNT LINE  |  '{cfg.entering_direction.upper()}' = ENTERING"
    cv2.putText(frame, txt, (10, y - 8), FONT, 0.5, (0, 255, 255), 1, cv2.LINE_AA)


# --------------------------------------------------------------------------
def draw_hud(frame, lines: List[str], x: int = 10, y: int = 10,
             line_h: int = 20, alpha: float = 0.55) -> None:
    if not lines:
        return
    width = max(cv2.getTextSize(t, FONT, 0.5, 1)[0][0] for t in lines) + 20
    height = line_h * len(lines) + 12
    blend_rect(frame, (x, y), (x + width, y + height), (0, 0, 0), alpha)
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (x + 10, y + 20 + i * line_h),
                    FONT, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


# --------------------------------------------------------------------------
def annotate(frame, detections, counter, cfg: Config, fps: float,
             snapshot: dict, source_label: str):
    """Full annotation pipeline; returns the annotated frame."""
    draw_tracks(frame, detections)
    draw_counting_line(frame, counter, cfg)

    hud = [
        f"FPS: {fps:5.1f}   Source: {source_label}",
        f"Density: {snapshot['density']}   Active: {snapshot['active']}",
        f"Counted: {snapshot['total_counted']}  "
        f"(In {snapshot['entering']} / Out {snapshot['exiting']})",
        f"Avg speed (est.): {snapshot['avg_speed']:.1f} km/h   "
        f"Slow: {snapshot['slow_now']}",
        "Speeds are ESTIMATES - calibrate pixels/metre for accuracy",
    ]
    draw_hud(frame, hud)
    return frame
