# analytics.py
"""
Tracking analytics: speed estimation, line crossing, density and statistics.
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple

from config import Config


# ==========================================================================
# Per-vehicle record
# ==========================================================================
@dataclass
class VehicleRecord:
    track_id: int
    cls_name: str
    first_time: float
    last_time: float
    frames: int = 0
    speeds: List[float] = field(default_factory=list)
    last_speed: Optional[float] = None
    counted: bool = False
    direction: Optional[str] = None      # 'in' / 'out'
    crossed_at: Optional[float] = None

    # ---- derived (all ESTIMATES) ----
    @property
    def avg_speed(self) -> float:
        return sum(self.speeds) / len(self.speeds) if self.speeds else 0.0

    @property
    def max_speed(self) -> float:
        return max(self.speeds) if self.speeds else 0.0

    @property
    def min_speed(self) -> float:
        return min(self.speeds) if self.speeds else 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.last_time - self.first_time)


# ==========================================================================
# Speed estimation
# ==========================================================================
class SpeedEstimator:
    """
    Estimates speed (km/h) from the pixel displacement of tracked centroids.

    IMPORTANT / LIMITATIONS
    -----------------------
    * Pixel displacement alone CANNOT give a real-world speed. The user must
      supply `pixels_per_meter`, measured on the actual scene (see the
      calibration tool in the GUI).
    * The calibration is a single scale factor, so it is only strictly valid
      near the image row where the calibration was performed. Perspective
      distortion will bias speeds elsewhere in the frame.
    * Camera shake, dropped frames and tracking jitter all add noise.
    * Every value produced here is an ESTIMATE, never a measurement.
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._hist: Dict[int, Deque[Tuple[float, float, float]]] = defaultdict(
            lambda: deque(maxlen=max(3, cfg.speed_window))
        )
        self._ema: Dict[int, float] = {}
        self._last_seen: Dict[int, float] = {}

    # ------------------------------------------------------------------
    @property
    def pixels_per_meter(self) -> float:
        return max(1e-6, float(self.cfg.pixels_per_meter))

    # ------------------------------------------------------------------
    def update(self, track_id: int, cx: float, cy: float,
               ts: float) -> Optional[float]:
        """Feed a centroid; returns the smoothed speed in km/h (or None)."""
        hist = self._hist[track_id]
        hist.append((float(ts), float(cx), float(cy)))
        self._last_seen[track_id] = ts

        if len(hist) < max(3, self.cfg.min_speed_samples):
            return None

        t0, x0, y0 = hist[0]
        t1, x1, y1 = hist[-1]
        dt = t1 - t0
        if dt <= 1e-3:
            return None

        dist_m = math.hypot(x1 - x0, y1 - y0) / self.pixels_per_meter
        raw_kmh = (dist_m / dt) * 3.6

        # Clamp implausible values (ID switches, calibration errors)
        if raw_kmh > self.cfg.max_plausible_speed:
            raw_kmh = self.cfg.max_plausible_speed

        prev = self._ema.get(track_id)
        a = float(self.cfg.speed_ema_alpha)
        value = raw_kmh if prev is None else a * raw_kmh + (1.0 - a) * prev
        self._ema[track_id] = value
        return value

    # ------------------------------------------------------------------
    def prune(self, ts: float, max_age: float = 5.0) -> None:
        """Drop state for tracks not seen for `max_age` seconds."""
        stale = [tid for tid, t in self._last_seen.items() if ts - t > max_age]
        for tid in stale:
            self._last_seen.pop(tid, None)
            self._hist.pop(tid, None)
            self._ema.pop(tid, None)

    def reset(self) -> None:
        self._hist.clear()
        self._ema.clear()
        self._last_seen.clear()


# ==========================================================================
# Virtual counting line
# ==========================================================================
class LineCounter:
    """
    Detects when a tracked centroid crosses a virtual horizontal line.

    It ONLY detects the crossing and its direction. De-duplication
    (never counting the same ID twice) is handled by TrafficStats.
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._prev_side: Dict[int, int] = {}
        self._last_seen_frame: Dict[int, int] = {}

    # ------------------------------------------------------------------
    def line_y(self, frame_height: int) -> int:
        return int(frame_height * float(self.cfg.count_line_ratio))

    # ------------------------------------------------------------------
    def update(self, track_id: int, cy: float, frame_height: int,
               frame_idx: int) -> Optional[str]:
        """Returns 'in', 'out' or None."""
        y = self.line_y(frame_height)
        side = 1 if cy >= y else -1
        prev = self._prev_side.get(track_id)
        self._prev_side[track_id] = side
        self._last_seen_frame[track_id] = frame_idx

        if prev is None or prev == side:
            return None

        moving_down = (prev < 0 and side > 0)   # top -> bottom
        if self.cfg.entering_direction == "down":
            return "in" if moving_down else "out"
        return "in" if not moving_down else "out"

    # ------------------------------------------------------------------
    def prune(self, frame_idx: int, max_missing: int = 90) -> None:
        stale = [tid for tid, f in self._last_seen_frame.items()
                 if frame_idx - f > max_missing]
        for tid in stale:
            self._last_seen_frame.pop(tid, None)
            self._prev_side.pop(tid, None)

    def reset(self) -> None:
        self._prev_side.clear()
        self._last_seen_frame.clear()


# ==========================================================================
# Density classification
# ==========================================================================
def classify_density(active_count: int, cfg: Config) -> str:
    """LOW / MEDIUM / HIGH based on user-configurable thresholds."""
    if active_count <= int(cfg.density_low_max):
        return "LOW"
    if active_count <= int(cfg.density_medium_max):
        return "MEDIUM"
    return "HIGH"


# ==========================================================================
# Statistics accumulator
# ==========================================================================
class TrafficStats:
    """Accumulates everything needed for the live panel and the final report."""

    def __init__(self, cfg: Config, source_name: str, source_type: str,
                 source_fps: float, width: int, height: int,
                 source_duration: float = 0.0) -> None:
        self.cfg = cfg
        self.source_name = source_name
        self.source_type = source_type
        self.source_fps = float(source_fps)
        self.width = int(width)
        self.height = int(height)
        self.source_duration = float(source_duration)

        self.wall_start = time.time()
        self.first_ts: Optional[float] = None
        self.last_ts: float = 0.0
        self.frames: int = 0

        self.vehicles: Dict[int, VehicleRecord] = {}
        self.active_ids: Set[int] = set()
        self.counted_ids: Set[int] = set()

        self.all_speeds: List[float] = []
        self.samples: List[dict] = []
        self.congestion_events: List[dict] = []

        self._last_sample_ts = -1e9
        self._congestion_active = False
        self._congestion_start: Optional[float] = None
        self._congestion_peak = 0
        self._last_congestion_end = -1e9

    # ------------------------------------------------------------------
    # Per-frame updates
    # ------------------------------------------------------------------
    def register(self, track_id: int, cls_name: str, ts: float) -> VehicleRecord:
        rec = self.vehicles.get(track_id)
        if rec is None:
            rec = VehicleRecord(track_id, cls_name, ts, ts)
            self.vehicles[track_id] = rec
        rec.last_time = ts
        rec.frames += 1
        if self.first_ts is None:
            self.first_ts = ts
        return rec

    def add_speed(self, track_id: int, speed: float, ts: float) -> None:
        rec = self.vehicles.get(track_id)
        if rec is None:
            return
        rec.speeds.append(speed)
        rec.last_speed = speed
        rec.last_time = ts
        self.all_speeds.append(speed)

    def mark_crossing(self, track_id: int, direction: str, ts: float) -> bool:
        """Returns True if this crossing was newly counted."""
        rec = self.vehicles.get(track_id)
        if rec is None or track_id in self.counted_ids:
            return False
        self.counted_ids.add(track_id)
        rec.counted = True
        rec.direction = direction
        rec.crossed_at = ts
        return True

    def end_frame(self, ts: float, active_ids: Set[int]) -> None:
        self.frames += 1
        self.last_ts = ts
        self.active_ids = set(active_ids)

    # ------------------------------------------------------------------
    def record_sample(self, ts: float, active_count: int, density: str,
                      avg_speed: Optional[float]) -> None:
        if ts - self._last_sample_ts >= float(self.cfg.sample_interval_s):
            self._last_sample_ts = ts
            self.samples.append({
                "t": round(ts, 3),
                "active": int(active_count),
                "density": density,
                "avg_speed": round(avg_speed, 2) if avg_speed is not None else None,
                "counted": len(self.counted_ids),
            })

        congested = (
            active_count >= int(self.cfg.congestion_min_vehicles)
            and avg_speed is not None
            and 0.0 <= avg_speed <= float(self.cfg.congestion_max_avg_speed)
        )

        if congested and not self._congestion_active:
            if ts - self._last_congestion_end >= float(self.cfg.congestion_cooldown_s):
                self._congestion_active = True
                self._congestion_start = ts
                self._congestion_peak = active_count
        elif congested and self._congestion_active:
            self._congestion_peak = max(self._congestion_peak, active_count)
        elif not congested and self._congestion_active:
            self._close_congestion(ts)

    def _close_congestion(self, ts: float) -> None:
        if self._congestion_start is None:
            self._congestion_active = False
            return
        self.congestion_events.append({
            "start": round(self._congestion_start, 2),
            "end": round(ts, 2),
            "duration_s": round(ts - self._congestion_start, 2),
            "peak_vehicles": int(self._congestion_peak),
        })
        self._congestion_active = False
        self._congestion_start = None
        self._last_congestion_end = ts

    def finalize(self) -> None:
        if self._congestion_active and self._congestion_start is not None:
            self._close_congestion(max(self.last_ts, self._congestion_start))

    # ------------------------------------------------------------------
    # Live values
    # ------------------------------------------------------------------
    @property
    def total_counted(self) -> int:
        return len(self.counted_ids)

    @property
    def counted_by_class(self) -> Counter:
        return Counter(self.vehicles[i].cls_name
                       for i in self.counted_ids if i in self.vehicles)

    @property
    def entering(self) -> int:
        return sum(1 for i in self.counted_ids
                   if i in self.vehicles and self.vehicles[i].direction == "in")

    @property
    def exiting(self) -> int:
        return sum(1 for i in self.counted_ids
                   if i in self.vehicles and self.vehicles[i].direction == "out")

    @property
    def avg_speed(self) -> float:
        return sum(self.all_speeds) / len(self.all_speeds) if self.all_speeds else 0.0

    @property
    def max_speed(self) -> float:
        return max(self.all_speeds) if self.all_speeds else 0.0

    @property
    def min_speed(self) -> float:
        return min(self.all_speeds) if self.all_speeds else 0.0

    @property
    def slow_now(self) -> int:
        thr = float(self.cfg.slow_speed_threshold)
        n = 0
        for tid in self.active_ids:
            rec = self.vehicles.get(tid)
            if rec and rec.last_speed is not None and rec.last_speed < thr:
                n += 1
        return n

    @property
    def slow_total(self) -> int:
        thr = float(self.cfg.slow_speed_threshold)
        return sum(1 for v in self.vehicles.values() if v.speeds and v.avg_speed < thr)

    @property
    def overspeed_total(self) -> int:
        thr = float(self.cfg.overspeed_threshold)
        return sum(1 for v in self.vehicles.values() if v.avg_speed > thr)

    @property
    def monitoring_duration(self) -> float:
        return max(0.0, self.last_ts - (self.first_ts or 0.0))

    # ------------------------------------------------------------------
    def speed_distribution(self) -> dict:
        bins = [(0, 20, "0-20 km/h"),
                (20, 40, "20-40 km/h"),
                (40, 60, "40-60 km/h"),
                (60, float("inf"), "Above 60 km/h")]
        out = {label: 0 for _, _, label in bins}
        for s in self.all_speeds:
            for lo, hi, label in bins:
                if lo <= s < hi:
                    out[label] += 1
                    break
        return out

    # ------------------------------------------------------------------
    def bucket_samples(self, bucket_s: Optional[float] = None) -> List[dict]:
        if not self.samples:
            return []
        if bucket_s is None:
            span = max(5.0, (self.samples[-1]["t"] - self.samples[0]["t"]) / 12.0)
            bucket_s = max(5.0, round(span))
        buckets: Dict[int, List[dict]] = defaultdict(list)
        for s in self.samples:
            buckets[int(s["t"] // bucket_s)].append(s)

        out = []
        for k in sorted(buckets):
            rows = buckets[k]
            start = k * bucket_s
            speeds = [r["avg_speed"] for r in rows if r["avg_speed"] is not None]
            out.append({
                "start_s": start,
                "end_s": start + bucket_s,
                "label": f"{int(start // 60):02d}:{int(start % 60):02d}"
                         f"-{int((start + bucket_s) // 60):02d}:"
                         f"{int((start + bucket_s) % 60):02d}",
                "avg_active": sum(r["active"] for r in rows) / len(rows),
                "avg_speed": (sum(speeds) / len(speeds)) if speeds else 0.0,
                "counted": rows[-1]["counted"],
            })
        return out

    # ------------------------------------------------------------------
    def live_snapshot(self, active_count: int, density: str,
                      current_avg_speed: float) -> dict:
        cbc = self.counted_by_class
        return {
            "total_counted": self.total_counted,
            "cars": cbc.get("Car", 0),
            "motorcycles": cbc.get("Motorcycle", 0),
            "buses": cbc.get("Bus", 0),
            "trucks": cbc.get("Truck", 0),
            "entering": self.entering,
            "exiting": self.exiting,
            "active": active_count,
            "unique_detected": len(self.vehicles),
            "avg_speed": current_avg_speed if current_avg_speed else self.avg_speed,
            "session_avg_speed": self.avg_speed,
            "max_speed": self.max_speed,
            "slow_now": self.slow_now,
            "density": density,
            "congestion_events": len(self.congestion_events),
        }