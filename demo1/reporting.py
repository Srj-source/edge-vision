# reporting.py
"""
Report generation: CSV, time-series CSV, charts (Matplotlib) and PDF (ReportLab).
"""
from __future__ import annotations

import csv
import os
import time
from typing import Dict, List, Optional

from config import Config
from analytics import TrafficStats


# ==========================================================================
# Summary construction
# ==========================================================================
def build_summary(stats: TrafficStats, cfg: Config,
                  annotated_path: Optional[str] = None) -> dict:
    counted = [v for v in stats.vehicles.values() if v.counted]
    detected = list(stats.vehicles.values())

    counted_by_class = {}
    detected_by_class = {}
    for name in ("Car", "Motorcycle", "Bus", "Truck"):
        counted_by_class[name] = sum(1 for v in counted if v.cls_name == name)
        detected_by_class[name] = sum(1 for v in detected if v.cls_name == name)

    buckets = stats.bucket_samples()
    peak = max(buckets, key=lambda b: b["avg_active"]) if buckets else None
    low = min(buckets, key=lambda b: b["avg_active"]) if buckets else None

    density_counts: Dict[str, int] = {}
    for s in stats.samples:
        density_counts[s["density"]] = density_counts.get(s["density"], 0) + 1
    overall_density = (max(density_counts, key=density_counts.get)
                       if density_counts else "N/A")

    return {
        "general": {
            "report_generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": stats.source_name,
            "source_type": stats.source_type,
            "video_duration_s": round(stats.source_duration, 2),
            "resolution": f"{stats.width} x {stats.height}",
            "source_fps": round(stats.source_fps, 2),
            "monitoring_duration_s": round(stats.monitoring_duration, 2),
            "frames_processed": stats.frames,
            "annotated_video": annotated_path or "not saved",
        },
        "vehicles": {
            "total_unique_detected": len(detected),
            "total_counted": stats.total_counted,
            "cars": counted_by_class["Car"],
            "motorcycles": counted_by_class["Motorcycle"],
            "buses": counted_by_class["Bus"],
            "trucks": counted_by_class["Truck"],
            "cars_detected": detected_by_class["Car"],
            "motorcycles_detected": detected_by_class["Motorcycle"],
            "buses_detected": detected_by_class["Bus"],
            "trucks_detected": detected_by_class["Truck"],
            "vehicles_entering": stats.entering,
            "vehicles_exiting": stats.exiting,
        },
        "speed": {
            "average_kmh": round(stats.avg_speed, 2),
            "maximum_kmh": round(stats.max_speed, 2),
            "minimum_kmh": round(stats.min_speed, 2) if stats.all_speeds else 0.0,
            "distribution": stats.speed_distribution(),
            "slow_moving_vehicles": stats.slow_total,
            "vehicles_over_threshold": stats.overspeed_total,
            "overspeed_threshold_kmh": cfg.overspeed_threshold,
            "slow_threshold_kmh": cfg.slow_speed_threshold,
        },
        "traffic": {
            "overall_density": overall_density,
            "density_sample_counts": density_counts,
            "peak_period": peak["label"] if peak else "N/A",
            "peak_period_avg_vehicles": round(peak["avg_active"], 2) if peak else 0.0,
            "lowest_period": low["label"] if low else "N/A",
            "lowest_period_avg_vehicles": round(low["avg_active"], 2) if low else 0.0,
            "volume_over_time": buckets,
            "congestion_events": stats.congestion_events,
            "congestion_event_count": len(stats.congestion_events),
        },
        "assumptions": [
            "Speeds are ESTIMATES derived from pixel displacement of tracked "
            "centroids, converted with a user-supplied calibration factor "
            "(pixels per metre).",
            "The calibration is a single scale factor and does not model "
            "perspective distortion, so accuracy degrades away from the "
            "calibration row.",
            "Vehicle counting is based on virtual-line crossings and tracking "
            "IDs; ID switches by the tracker can cause rare miscounts.",
            f"Density thresholds (LOW <= {cfg.density_low_max}, "
            f"MEDIUM <= {cfg.density_medium_max} active vehicles) are "
            "CONFIGURABLE, not measured.",
            f"Congestion is flagged when active vehicles >= "
            f"{cfg.congestion_min_vehicles} AND average speed <= "
            f"{cfg.congestion_max_avg_speed} km/h (CONFIGURABLE).",
            f"Overspeed threshold = {cfg.overspeed_threshold} km/h "
            "(CONFIGURABLE).",
            "Vehicle class names come from the YOLO COCO model and can be "
            "wrong under occlusion or poor lighting.",
        ],
    }


# ==========================================================================
# CSV writers
# ==========================================================================
def _flatten(prefix: str, data: dict, out: List[tuple]) -> None:
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _flatten(name, value, out)
        elif isinstance(value, list):
            out.append((name, f"{len(value)} entries"))
        else:
            out.append((name, value))


def write_summary_csv(summary: dict, out_dir: str, stamp: str) -> str:
    path = os.path.join(out_dir, f"traffic_summary_{stamp}.csv")
    rows: List[tuple] = []
    for section in ("general", "vehicles", "speed", "traffic"):
        _flatten(section, summary[section], rows)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        writer.writerows(rows)
    return path


def write_vehicles_csv(stats: TrafficStats, out_dir: str, stamp: str) -> str:
    path = os.path.join(out_dir, f"traffic_vehicles_{stamp}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "track_id", "class", "first_seen_s", "last_seen_s",
            "visible_duration_s", "frames_tracked", "speed_samples",
            "avg_speed_kmh", "max_speed_kmh", "min_speed_kmh",
            "counted", "direction", "crossed_at_s",
        ])
        for v in sorted(stats.vehicles.values(), key=lambda r: r.track_id):
            writer.writerow([
                v.track_id, v.cls_name,
                round(v.first_time, 2), round(v.last_time, 2),
                round(v.duration, 2), v.frames, len(v.speeds),
                round(v.avg_speed, 2), round(v.max_speed, 2),
                round(v.min_speed, 2),
                int(v.counted), v.direction or "",
                round(v.crossed_at, 2) if v.crossed_at is not None else "",
            ])
    return path


def write_timeseries_csv(stats: TrafficStats, out_dir: str, stamp: str) -> str:
    path = os.path.join(out_dir, f"traffic_timeseries_{stamp}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time_s", "active_vehicles", "density",
                         "avg_speed_kmh", "cumulative_counted"])
        for s in stats.samples:
            writer.writerow([s["t"], s["active"], s["density"],
                             s["avg_speed"] if s["avg_speed"] is not None else "",
                             s["counted"]])
    return path


# ==========================================================================
# Charts
# ==========================================================================
def make_charts(stats: TrafficStats, out_dir: str, stamp: str) -> List[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []

    chart_dir = os.path.join(out_dir, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    paths: List[str] = []

    counted = [v for v in stats.vehicles.values() if v.counted]
    classes = ["Car", "Motorcycle", "Bus", "Truck"]
    counts = [sum(1 for v in counted if v.cls_name == c) for c in classes]

    # 1. Vehicle count by type -----------------------------------------
    fig, ax = plt.subplots(figsize=(6, 3.5))
    bars = ax.bar(classes, counts, color=["#2ca02c", "#ff7f0e", "#1f77b4", "#d62728"])
    ax.set_title("Vehicle Count by Type (counted)")
    ax.set_ylabel("Vehicles")
    ax.bar_label(bars)
    fig.tight_layout()
    p = os.path.join(chart_dir, f"count_by_type_{stamp}.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    paths.append(p)

    # 2. Traffic volume over time --------------------------------------
    buckets = stats.bucket_samples()
    if buckets:
        labels = [b["label"] for b in buckets]
        cumulative = [b["counted"] for b in buckets]
        per_bucket = [cumulative[0]] + [cumulative[i] - cumulative[i - 1]
                                        for i in range(1, len(cumulative))]

        fig, ax1 = plt.subplots(figsize=(7, 3.5))
        ax1.plot(labels, cumulative, marker="o", color="#1f77b4",
                 label="Cumulative counted")
        ax1.set_ylabel("Cumulative vehicles", color="#1f77b4")
        ax1.tick_params(axis="x", rotation=45, labelsize=7)
        ax2 = ax1.twinx()
        ax2.bar(labels, per_bucket, alpha=0.3, color="#ff7f0e",
                label="Per interval")
        ax2.set_ylabel("Vehicles per interval", color="#ff7f0e")
        ax1.set_title("Traffic Volume over Time")
        fig.tight_layout()
        p = os.path.join(chart_dir, f"volume_over_time_{stamp}.png")
        fig.savefig(p, dpi=110)
        plt.close(fig)
        paths.append(p)

        # 3. Density (active vehicles) over time -----------------------
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.plot(labels, [b["avg_active"] for b in buckets],
                color="#9467bd", marker="o", ms=3)
        ax.axhline(stats.cfg.density_low_max, color="green", ls="--", lw=1,
                   label=f"LOW max ({stats.cfg.density_low_max})")
        ax.axhline(stats.cfg.density_medium_max, color="red", ls="--", lw=1,
                   label=f"MEDIUM max ({stats.cfg.density_medium_max})")
        ax.set_ylabel("Active vehicles")
        ax.set_title("Traffic Density over Time")
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.legend(fontsize=7)
        fig.tight_layout()
        p = os.path.join(chart_dir, f"density_over_time_{stamp}.png")
        fig.savefig(p, dpi=110)
        plt.close(fig)
        paths.append(p)

        # 4. Average speed over time -----------------------------------
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.plot(labels, [b["avg_speed"] for b in buckets],
                color="#2ca02c", marker="o", ms=3)
        ax.set_ylabel("km/h (estimated)")
        ax.set_title("Average Estimated Speed over Time")
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        fig.tight_layout()
        p = os.path.join(chart_dir, f"avg_speed_over_time_{stamp}.png")
        fig.savefig(p, dpi=110)
        plt.close(fig)
        paths.append(p)

    # 5. Speed distribution --------------------------------------------
    dist = stats.speed_distribution()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    bars = ax.bar(list(dist.keys()), list(dist.values()), color="#17becf")
    ax.set_title("Speed Distribution (estimated)")
    ax.set_ylabel("Measurements")
    ax.bar_label(bars)
    plt.setp(ax.get_xticklabels(), rotation=15, fontsize=8)
    fig.tight_layout()
    p = os.path.join(chart_dir, f"speed_distribution_{stamp}.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    paths.append(p)

    return paths


# ==========================================================================
# PDF
# ==========================================================================
def write_pdf(summary: dict, stats: TrafficStats, chart_paths: List[str],
              out_dir: str, stamp: str) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (Image as RLImage, PageBreak, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)

    path = os.path.join(out_dir, f"traffic_report_{stamp}.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18,
                        textColor=colors.HexColor("#123a63"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13,
                        textColor=colors.HexColor("#1f6fb2"), spaceBefore=10)
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=8,
                           textColor=colors.HexColor("#555555"))

    story = [Paragraph("Real-Time Traffic Monitoring Report", h1),
             Paragraph(f"Generated: {summary['general']['report_generated']}", body),
             Spacer(1, 10)]

    def table(section: dict, title: str):
        story.append(Paragraph(title, h2))
        data = [["Metric", "Value"]]
        for k, v in section.items():
            if isinstance(v, (dict, list)):
                continue
            data.append([k.replace("_", " ").title(), str(v)])
        t = Table(data, colWidths=[8.5 * cm, 7.5 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6fb2")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#eef4fa")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)

    table(summary["general"], "General Information")
    table(summary["vehicles"], "Vehicle Statistics")
    table(summary["speed"], "Speed Analysis")
    table(summary["traffic"], "Traffic Analysis")

    # Speed distribution table
    story.append(Paragraph("Speed Distribution", h2))
    dist = summary["speed"]["distribution"]
    d = [["Range", "Measurements"]] + [[k, str(v)] for k, v in dist.items()]
    t = Table(d, colWidths=[8.5 * cm, 7.5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17becf")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
    ]))
    story.append(t)

    # Congestion events
    if stats.congestion_events:
        story.append(Paragraph("Congestion Events", h2))
        d = [["#", "Start (s)", "End (s)", "Duration (s)", "Peak vehicles"]]
        for i, ev in enumerate(stats.congestion_events, 1):
            d.append([i, ev["start"], ev["end"], ev["duration_s"],
                      ev["peak_vehicles"]])
        t = Table(d, colWidths=[1.2 * cm, 3 * cm, 3 * cm, 3.5 * cm, 3.5 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d62728")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ]))
        story.append(t)

    # Charts
    if chart_paths:
        story.append(PageBreak())
        story.append(Paragraph("Data Visualisation", h1))
        for p in chart_paths:
            try:
                story.append(Paragraph(
                    os.path.basename(p).replace("_", " ").replace(".png", "").title(),
                    h2))
                story.append(RLImage(p, width=16 * cm, height=8.6 * cm))
                story.append(Spacer(1, 6))
            except Exception:
                continue

    # Assumptions
    story.append(PageBreak())
    story.append(Paragraph("Assumptions, Estimates and Limitations", h1))
    for note in summary["assumptions"]:
        story.append(Paragraph(f"&bull; {note}", small))
        story.append(Spacer(1, 3))

    doc.build(story)
    return path


# ==========================================================================
# Orchestrator
# ==========================================================================
def generate_all(stats: TrafficStats, cfg: Config,
                 annotated_path: Optional[str] = None,
                 out_dir: Optional[str] = None) -> dict:
    out_dir = out_dir or cfg.output_dir
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")

    stats.finalize()
    summary = build_summary(stats, cfg, annotated_path)

    result = {
        "output_dir": os.path.abspath(out_dir),
        "summary": summary,
        "files": {},
        "errors": [],
    }

    try:
        result["files"]["summary_csv"] = write_summary_csv(summary, out_dir, stamp)
    except Exception as exc:                                  # pragma: no cover
        result["errors"].append(f"summary CSV: {exc}")

    try:
        result["files"]["vehicles_csv"] = write_vehicles_csv(stats, out_dir, stamp)
    except Exception as exc:                                  # pragma: no cover
        result["errors"].append(f"vehicles CSV: {exc}")

    try:
        result["files"]["timeseries_csv"] = write_timeseries_csv(stats, out_dir, stamp)
    except Exception as exc:                                  # pragma: no cover
        result["errors"].append(f"timeseries CSV: {exc}")

    try:
        result["files"]["charts"] = make_charts(stats, out_dir, stamp)
    except Exception as exc:                                  # pragma: no cover
        result["errors"].append(f"charts: {exc}")
        result["files"]["charts"] = []

    try:
        result["files"]["pdf"] = write_pdf(
            summary, stats, result["files"].get("charts", []), out_dir, stamp)
    except Exception as exc:                                  # pragma: no cover
        result["errors"].append(f"PDF: {exc}")
        result["files"]["pdf"] = None

    # Timestamped JSON copy of the raw summary for future analysis
    try:
        import json
        json_path = os.path.join(out_dir, f"traffic_summary_{stamp}.json")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, default=str)
        result["files"]["summary_json"] = json_path
    except Exception as exc:                                  # pragma: no cover
        result["errors"].append(f"summary JSON: {exc}")

    return result