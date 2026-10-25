# config.py
"""
Central configuration for the Real-Time Traffic Monitoring System.

Every threshold in this file is CONFIGURABLE and clearly separated from
measured / estimated values so the report can distinguish them.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Dict

# --------------------------------------------------------------------------
# COCO class ids used by YOLO that we care about
# --------------------------------------------------------------------------
VEHICLE_CLASSES: Dict[int, str] = {
    2: "Car",
    3: "Motorcycle",
    5: "Bus",
    7: "Truck",
}

# BGR colours (OpenCV order) - one colour per vehicle class
CLASS_COLORS_BGR = {
    "Car":        (0, 200, 0),      # green
    "Motorcycle": (0, 165, 255),    # orange
    "Bus":        (255, 128, 0),    # blue-ish
    "Truck":      (0, 0, 255),      # red
    "Unknown":    (200, 200, 200),  # grey
}


@dataclass
class Config:
    # ------------------------------------------------------------------
    # 1. Detection
    # ------------------------------------------------------------------
    model_path: str = "yolov8n.pt"     # any ultralytics model (n/s/m/l/x)
    conf_threshold: float = 0.35       # CONFIGURABLE
    iou_threshold: float = 0.50        # CONFIGURABLE
    imgsz: int = 640                   # CONFIGURABLE
    device: str = ""                   # "" = auto (cpu / cuda:0)
    tracker: str = "bytetrack.yaml"    # ByteTrack (or botsort.yaml)

    # ------------------------------------------------------------------
    # 2. Speed estimation / calibration
    #    pixels_per_meter is MEASURED by the user on the real scene.
    #    Without a valid calibration every speed value is meaningless.
    # ------------------------------------------------------------------
    pixels_per_meter: float = 8.0      # CALIBRATION (pixels per real metre)
    speed_window: int = 12             # frames used for displacement
    speed_ema_alpha: float = 0.45      # temporal smoothing (0..1)
    min_speed_samples: int = 3         # min history before a speed is shown
    max_plausible_speed: float = 200.0 # clamp for outliers (km/h)

    # ------------------------------------------------------------------
    # 3. Counting line
    # ------------------------------------------------------------------
    count_line_ratio: float = 0.62     # line position = ratio * frame height
    entering_direction: str = "down"   # 'down' or 'up'

    # ------------------------------------------------------------------
    # 4. Traffic density thresholds (active vehicles in frame)
    # ------------------------------------------------------------------
    density_low_max: int = 3           # CONFIGURABLE
    density_medium_max: int = 8        # CONFIGURABLE

    # ------------------------------------------------------------------
    # 5. Congestion / speed thresholds
    # ------------------------------------------------------------------
    slow_speed_threshold: float = 15.0     # km/h - CONFIGURABLE
    overspeed_threshold: float = 60.0      # km/h - CONFIGURABLE
    congestion_min_vehicles: int = 6       # CONFIGURABLE
    congestion_max_avg_speed: float = 12.0 # km/h - CONFIGURABLE
    congestion_cooldown_s: float = 5.0     # CONFIGURABLE

    # ------------------------------------------------------------------
    # 6. Output
    # ------------------------------------------------------------------
    output_dir: str = "traffic_output"
    save_annotated_video: bool = False
    sample_interval_s: float = 0.5     # time-series sampling rate

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)