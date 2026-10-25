# app.py
"""
Real-Time Traffic Monitoring and Vehicle Detection System
=========================================================
Tkinter dashboard + OpenCV/YOLO/ByteTrack processing pipeline.

Run:  python app.py
"""
from __future__ import annotations

import math
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import List, Optional

import cv2
from PIL import Image, ImageTk

from analytics import LineCounter, SpeedEstimator, TrafficStats, classify_density
from config import Config, VEHICLE_CLASSES
from drawing import annotate
from reporting import generate_all

APP_TITLE = "Real-Time Traffic Monitoring & Vehicle Detection System"
DISPLAY_MAX_WIDTH = 980


class TrafficMonitorApp:
    # ==================================================================
    def __init__(self, root: tk.Tk, cfg: Optional[Config] = None) -> None:
        self.root = root
        self.cfg = cfg or Config()

        self.model = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False

        self.source_type: Optional[str] = None      # 'webcam' | 'file'
        self.source_path: Optional[str] = None
        self.source_name = "—"
        self.source_fps = 30.0
        self.source_duration = 0.0
        self.frame_size = (0, 0)

        self.frame_idx = 0
        self.wall_t0 = time.perf_counter()
        self.proc_fps = 0.0

        self.stats: Optional[TrafficStats] = None
        self.speed_est = SpeedEstimator(self.cfg)
        self.counter = LineCounter(self.cfg)

        self.video_writer: Optional[cv2.VideoWriter] = None
        self.annotated_path: Optional[str] = None

        self.current_frame = None
        self._imgtk = None
        self._last_detections: List[dict] = []

        self.active_count = 0
        self.density = "LOW"
        self.current_avg_speed = 0.0

        self.root.title(APP_TITLE)
        self.root.configure(bg="#15171c")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_buttons()
        self._set_status("Idle - choose a video or the webcam, then press Start.")

    # ==================================================================
    # UI
    # ==================================================================
    def _build_ui(self) -> None:
        main = tk.Frame(self.root, bg="#15171c")
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        self.video_label = tk.Label(main, bg="#000000", bd=0)
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        panel = tk.LabelFrame(main, text=" Statistics ",
                              fg="#00e5ff", bg="#15171c",
                              font=("Segoe UI", 10, "bold"),
                              labelanchor="n", bd=1, relief="solid")
        panel.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)

        rows = [
            "Status", "Source", "Resolution", "Source FPS", "Processing FPS",
            "-----", "Total counted", "Cars", "Motorcycles", "Buses", "Trucks",
            "Entering", "Exiting", "Active vehicles", "Unique detected",
            "-----", "Avg speed (km/h)", "Max speed (km/h)", "Slow vehicles",
            "Traffic density", "Congestion events", "-----",
            "pixels / metre",
        ]
        self.stat_labels = {}
        for i, name in enumerate(rows):
            if name == "-----":
                tk.Frame(panel, height=1, bg="#333844").grid(
                    row=i, column=0, columnspan=2, sticky="ew", padx=6, pady=4)
                continue
            tk.Label(panel, text=f"{name}:", fg="#9aa4b2", bg="#15171c",
                     anchor="w", font=("Segoe UI", 9)).grid(
                row=i, column=0, sticky="w", padx=(8, 4), pady=1)
            lbl = tk.Label(panel, text="—", fg="#ffffff", bg="#15171c",
                           anchor="w", font=("Segoe UI", 9, "bold"))
            lbl.grid(row=i, column=1, sticky="w", padx=(0, 10), pady=1)
            self.stat_labels[name] = lbl

        bar = tk.Frame(self.root, bg="#15171c")
        bar.pack(fill="x", padx=8, pady=(0, 10))

        self.btn_start = self._button(bar, "▶  Start Monitoring", self._on_start)
        self.btn_stop = self._button(bar, "■  Stop Monitoring", self._on_stop)
        self.btn_reset = self._button(bar, "⟲  Reset Statistics", self._on_reset)
        self.btn_video = self._button(bar, "📂  Upload Traffic Video", self._on_upload)
        self.btn_webcam = self._button(bar, "🎥  Use Webcam", self._on_webcam)
        self.btn_calib = self._button(bar, "📏  Speed Calibration", self._on_calibrate)
        self.btn_density = self._button(bar, "📊  Density Thresholds", self._on_density)
        self.btn_report = self._button(bar, "📄  Export Report", self._on_export)

    def _button(self, parent, text, command):
        b = tk.Button(parent, text=text, command=command,
                      bg="#22262e", fg="#e6e6e6",
                      activebackground="#2f3540", activeforeground="#ffffff",
                      relief="flat", bd=0, padx=10, pady=7,
                      font=("Segoe UI", 9, "bold"), cursor="hand2")
        b.pack(side="left", padx=3)
        return b

    def _refresh_buttons(self) -> None:
        state_running = "disabled" if self.running else "normal"
        state_stopped = "normal" if self.running else "disabled"
        for b in (self.btn_start, self.btn_video, self.btn_webcam,
                  self.btn_reset, self.btn_calib, self.btn_density):
            b.configure(state=state_running)
        self.btn_stop.configure(state=state_stopped)
        self.btn_report.configure(state="normal")

    def _set_status(self, text: str) -> None:
        if "Status" in self.stat_labels:
            self.stat_labels["Status"].configure(text=text)

    # ==================================================================
    # Model / source handling
    # ==================================================================
    def _ensure_model(self) -> bool:
        if self.model is not None:
            return True
        try:
            from ultralytics import YOLO
        except ImportError:
            messagebox.showerror(
                "Missing dependency",
                "The 'ultralytics' package is required.\n\n"
                "Install it with:\n    pip install ultralytics")
            return False
        try:
            self._set_status(f"Loading {self.cfg.model_path} …")
            self.root.update_idletasks()
            self.model = YOLO(self.cfg.model_path)
        except Exception as exc:
            messagebox.showerror("Model error",
                                 f"Could not load '{self.cfg.model_path}':\n{exc}")
            return False
        return True

    # ------------------------------------------------------------------
    def _open_source(self, source_type: str, path: Optional[str] = None) -> bool:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        if source_type == "webcam":
            cap = cv2.VideoCapture(0)
            if not cap.isOpened() and os.name == "nt":
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            name = "Webcam (device 0)"
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            duration = 0.0
        else:
            cap = cv2.VideoCapture(path)
            name = os.path.basename(path or "video")
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            duration = (frames / fps) if fps > 0 else 0.0

        if not cap.isOpened():
            messagebox.showerror("Source error",
                                 f"Could not open the source:\n{path or 'webcam'}")
            return False

        ok, frame = cap.read()
        if not ok:
            cap.release()
            messagebox.showerror("Source error", "The source returned no frames.")
            return False

        h, w = frame.shape[:2]
        self.cap = cap
        self.source_type = source_type
        self.source_path = path
        self.source_name = name
        self.source_fps = float(fps) if fps and fps > 0 else 30.0
        self.source_duration = float(duration)
        self.frame_size = (w, h)

        # rewind for files
        if source_type == "file":
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
            if not ok:
                cap.release()
                messagebox.showerror("Source error", "Could not rewind the video.")
                return False

        self._show_frame(self._prepare_placeholder(frame))
        return True

    def _prepare_placeholder(self, frame):
        h, w = frame.shape[:2]
        cv2.putText(frame, "Ready - press Start Monitoring",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        return frame

    # ==================================================================
    # Start / stop
    # ==================================================================
    def _on_start(self) -> None:
        if self.running:
            return
        if self.cap is None:
            messagebox.showinfo(
                "No source",
                "Choose a traffic video ('Upload Traffic Video') or the "
                "webcam ('Use Webcam') first.")
            return
        if not self._ensure_model():
            return

        self._reset_state(keep_source=True)
        self.wall_t0 = time.perf_counter()
        self.running = True
        self._refresh_buttons()
        self._set_status("Monitoring …")

        # Optional annotated video writer
        if self.cfg.save_annotated_video:
            os.makedirs(self.cfg.output_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            self.annotated_path = os.path.join(
                self.cfg.output_dir, f"annotated_{stamp}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.video_writer = cv2.VideoWriter(
                self.annotated_path, fourcc, self.source_fps, self.frame_size)

        self.root.after(1, self._tick)

    def _on_stop(self) -> None:
        self._stop("Stopped by user")

    def _stop(self, reason: str, show_report: bool = True) -> None:
        if not self.running and self.stats is None:
            return
        self.running = False
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
        self._refresh_buttons()
        self._set_status(reason)

        if self.stats is not None and (self.stats.frames > 0):
            self._generate_and_show_report(auto=True)

    # ==================================================================
    # Main processing loop
    # ==================================================================
    def _tick(self) -> None:
        if not self.running or self.cap is None:
            return

        ok, frame = self.cap.read()
        if not ok:
            self._stop("End of video - report generated", show_report=True)
            return

        self.frame_idx += 1
        t0 = time.perf_counter()
        ts = self._timestamp()

        annotated = self._process_frame(frame, ts)
        self._show_frame(annotated)

        dt = time.perf_counter() - t0
        inst = 1.0 / dt if dt > 0 else 0.0
        self.proc_fps = inst if self.proc_fps == 0 else (
            0.85 * self.proc_fps + 0.15 * inst)

        self._refresh_panel()
        self.root.after(1, self._tick)

    # ------------------------------------------------------------------
    def _timestamp(self) -> float:
        """
        Video files -> video time (frame_idx / fps) so that speed is
        independent of how fast the machine can process frames.
        Webcam      -> wall-clock time.
        """
        if self.source_type == "file" and self.source_fps > 0:
            return self.frame_idx / self.source_fps
        return time.perf_counter() - self.wall_t0

    # ------------------------------------------------------------------
    def _process_frame(self, frame, ts: float):
        h, w = frame.shape[:2]

        kwargs = dict(
            persist=True,
            tracker=self.cfg.tracker,
            conf=self.cfg.conf_threshold,
            iou=self.cfg.iou_threshold,
            imgsz=self.cfg.imgsz,
            classes=list(VEHICLE_CLASSES.keys()),
            verbose=False,
        )
        if self.cfg.device:
            kwargs["device"] = self.cfg.device

        try:
            results = self.model.track(frame, **kwargs)
        except Exception as exc:
            self._set_status(f"Tracker error: {exc}")
            results = []

        detections: List[dict] = []
        active_ids = set()
        frame_speeds: List[float] = []

        if results:
            boxes = getattr(results[0], "boxes", None)
            if boxes is not None and boxes.id is not None:
                ids = boxes.id.int().cpu().tolist()
                clss = boxes.cls.int().cpu().tolist()
                confs = boxes.conf.cpu().tolist()
                xyxy = boxes.xyxy.cpu().tolist()

                for tid, cls_id, conf, box in zip(ids, clss, confs, xyxy):
                    cls_name = VEHICLE_CLASSES.get(int(cls_id), "Vehicle")
                    x1, y1, x2, y2 = box
                    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0

                    active_ids.add(tid)
                    self.stats.register(tid, cls_name, ts)

                    speed = self.speed_est.update(tid, cx, cy, ts)
                    if speed is not None:
                        self.stats.add_speed(tid, speed, ts)
                        frame_speeds.append(speed)

                    direction = self.counter.update(tid, cy, h, self.frame_idx)
                    if direction:
                        self.stats.mark_crossing(tid, direction, ts)

                    detections.append({
                        "id": tid, "cls_name": cls_name, "conf": conf,
                        "bbox": (x1, y1, x2, y2), "cx": cx, "cy": cy,
                        "speed": speed,
                    })

        self.speed_est.prune(ts)
        self.counter.prune(self.frame_idx)
        self.stats.end_frame(ts, active_ids)

        self.active_count = len(active_ids)
        self.current_avg_speed = (sum(frame_speeds) / len(frame_speeds)
                                  if frame_speeds else 0.0)
        self.density = classify_density(self.active_count, self.cfg)

        self.stats.record_sample(
            ts, self.active_count, self.density,
            self.current_avg_speed if frame_speeds else None)

        snapshot = self.stats.live_snapshot(
            self.active_count, self.density, self.current_avg_speed)

        annotated = annotate(frame, detections, self.counter, self.cfg,
                             self.proc_fps, snapshot, self.source_name)
        self._last_detections = detections

        if self.video_writer is not None:
            self.video_writer.write(annotated)

        return annotated

    # ==================================================================
    # Display helpers
    # ==================================================================
    def _show_frame(self, frame) -> None:
        if frame is None:
            return
        self.current_frame = frame
        h, w = frame.shape[:2]
        if w > DISPLAY_MAX_WIDTH:
            scale = DISPLAY_MAX_WIDTH / float(w)
            frame = cv2.resize(frame, (DISPLAY_MAX_WIDTH, int(h * scale)),
                               interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        self._imgtk = ImageTk.PhotoImage(img)
        self.video_label.configure(image=self._imgtk)

    def _refresh_panel(self) -> None:
        if self.stats is None:
            return
        snap = self.stats.live_snapshot(
            self.active_count, self.density, self.current_avg_speed)
        L = self.stat_labels

        L["Source"].configure(text=self.source_name)
        L["Resolution"].configure(text=f"{self.frame_size[0]} x {self.frame_size[1]}")
        L["Source FPS"].configure(text=f"{self.source_fps:.1f}")
        L["Processing FPS"].configure(text=f"{self.proc_fps:.1f}")
        L["Total counted"].configure(text=str(snap["total_counted"]))
        L["Cars"].configure(text=str(snap["cars"]))
        L["Motorcycles"].configure(text=str(snap["motorcycles"]))
        L["Buses"].configure(text=str(snap["buses"]))
        L["Trucks"].configure(text=str(snap["trucks"]))
        L["Entering"].configure(text=str(snap["entering"]))
        L["Exiting"].configure(text=str(snap["exiting"]))
        L["Active vehicles"].configure(text=str(snap["active"]))
        L["Unique detected"].configure(text=str(snap["unique_detected"]))
        L["Avg speed (km/h)"].configure(text=f"{snap['avg_speed']:.1f}")
        L["Max speed (km/h)"].configure(text=f"{snap['max_speed']:.1f}")
        L["Slow vehicles"].configure(text=str(snap["slow_now"]))
        L["Congestion events"].configure(text=str(snap["congestion_events"]))
        L["pixels / metre"].configure(text=f"{self.cfg.pixels_per_meter:.2f}")

        colour = {"LOW": "#3ddc84", "MEDIUM": "#ffb300", "HIGH": "#ff5252"}
        L["Traffic density"].configure(
            text=snap["density"],
            fg=colour.get(snap["density"], "#ffffff"))

    # ==================================================================
    # State management
    # ==================================================================
    def _reset_state(self, keep_source: bool = False) -> None:
        if self.stats is not None:
            self.stats.finalize()
        w, h = self.frame_size
        self.stats = TrafficStats(
            self.cfg, self.source_name,
            self.source_type or "unknown",
            self.source_fps, w, h, self.source_duration)
        self.speed_est = SpeedEstimator(self.cfg)
        self.counter = LineCounter(self.cfg)
        self.frame_idx = 0
        self.proc_fps = 0.0
        self.active_count = 0
        self.current_avg_speed = 0.0
        self.density = "LOW"
        self._last_detections = []
        self.annotated_path = None
        if not keep_source:
            self._refresh_panel()

    def _on_reset(self) -> None:
        if self.stats is None:
            return
        if not messagebox.askyesno("Reset statistics",
                                   "Discard all collected statistics?"):
            return
        was_running = self.running
        self.running = False
        self._reset_state(keep_source=True)
        self.wall_t0 = time.perf_counter()
        self._refresh_panel()
        if was_running:
            self.running = True
            self.root.after(1, self._tick)

    # ==================================================================
    # Source buttons
    # ==================================================================
    def _on_upload(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a traffic video",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv *.m4v"),
                       ("All files", "*.*")])
        if not path:
            return
        if not self._open_source("file", path):
            return
        self._on_start()

    def _on_webcam(self) -> None:
        if not self._open_source("webcam"):
            return
        self._on_start()

    # ==================================================================
    # Calibration
    # ==================================================================
    def _on_calibrate(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Speed Calibration")
        win.configure(bg="#15171c")
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Speed Calibration",
                 fg="#00e5ff", bg="#15171c",
                 font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(12, 4), sticky="w")

        info = ("Speed is estimated from pixel displacement. You must tell the\n"
                "system how many pixels correspond to one real metre in the\n"
                "scene. Measure a known distance (e.g. a lane marking or the\n"
                "distance between two road studs) and use one of the methods\n"
                "below. Perspective distortion means the estimate is only\n"
                "accurate near the row where you calibrated.")
        tk.Label(win, text=info, justify="left", fg="#9aa4b2", bg="#15171c",
                 font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=2,
                                            padx=12, pady=(0, 10), sticky="w")

        tk.Label(win, text="Pixels per metre:", fg="#e6e6e6", bg="#15171c",
                 font=("Segoe UI", 9)).grid(row=2, column=0, padx=12,
                                            pady=4, sticky="w")
        entry = tk.Entry(win, width=14, bg="#22262e", fg="#ffffff",
                         insertbackground="#ffffff", relief="flat")
        entry.insert(0, f"{self.cfg.pixels_per_meter:.3f}")
        entry.grid(row=2, column=1, padx=12, pady=4, sticky="w")

        def apply_manual():
            try:
                value = float(entry.get())
                if value <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid value",
                                     "Enter a positive number.", parent=win)
                return
            self.cfg.pixels_per_meter = value
            self._refresh_panel()
            win.destroy()

        def visual():
            win.withdraw()
            self.root.update_idletasks()
            ppm = self._visual_calibration()
            if ppm:
                entry.delete(0, tk.END)
                entry.insert(0, f"{ppm:.3f}")
                self.cfg.pixels_per_meter = ppm
                self._refresh_panel()
            win.deiconify()

        tk.Button(win, text="Apply", command=apply_manual,
                  bg="#1f6fb2", fg="#ffffff", relief="flat", bd=0,
                  padx=14, pady=6, font=("Segoe UI", 9, "bold"),
                  cursor="hand2").grid(row=3, column=0, padx=12, pady=12)
        tk.Button(win, text="Click 2 points on a frame…", command=visual,
                  bg="#22262e", fg="#e6e6e6", relief="flat", bd=0,
                  padx=14, pady=6, font=("Segoe UI", 9, "bold"),
                  cursor="hand2").grid(row=3, column=1, padx=12, pady=12)

    # ------------------------------------------------------------------
    def _grab_reference_frame(self):
        if self.current_frame is not None:
            return self.current_frame.copy()
        if self.cap is not None:
            pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
            ok, frame = self.cap.read()
            if ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                return frame
        if self.source_path:
            cap = cv2.VideoCapture(self.source_path)
            ok, frame = cap.read()
            cap.release()
            if ok:
                return frame
        return None

    def _visual_calibration(self) -> Optional[float]:
        frame = self._grab_reference_frame()
        if frame is None:
            messagebox.showinfo("Calibration",
                                "Load a video or the webcam first.")
            return None

        points = []
        clone = frame.copy()

        def on_mouse(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN and len(points) < 2:
                points.append((x, y))
                cv2.circle(clone, (x, y), 6, (0, 0, 255), -1)
                if len(points) == 2:
                    cv2.line(clone, points[0], points[1], (0, 255, 255), 2)
                    mid = ((points[0][0] + points[1][0]) // 2,
                           (points[0][1] + points[1][1]) // 2)
                    px = math.dist(points[0], points[1])
                    cv2.putText(clone, f"{px:.0f} px", mid,
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.imshow("Calibration - click 2 points (ESC to cancel)", clone)

        win_name = "Calibration - click 2 points (ESC to cancel)"
        cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(win_name, on_mouse)
        cv2.putText(clone, "Click 2 points of a known real-world distance",
                    (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow(win_name, clone)

        while True:
            key = cv2.waitKey(20) & 0xFF
            if key == 27:
                break
            if len(points) == 2:
                cv2.waitKey(500)
                break

        cv2.destroyWindow(win_name)
        cv2.waitKey(1)

        if len(points) < 2:
            return None

        pixel_distance = math.dist(points[0], points[1])
        real_distance = simpledialog.askfloat(
            "Calibration",
            f"The two points are {pixel_distance:.1f} pixels apart.\n\n"
            "Enter the real-world distance between them, in METRES:",
            parent=self.root, minvalue=0.05, maxvalue=1000.0)
        if not real_distance:
            return None

        ppm = pixel_distance / real_distance
        messagebox.showinfo(
            "Calibration complete",
            f"Calibration factor: {ppm:.2f} pixels per metre.\n\n"
            "Reminder: this is a single-scale approximation. Perspective "
            "distortion will still bias speeds away from the calibrated "
            "image row.")
        return ppm

    # ==================================================================
    # Density thresholds
    # ==================================================================
    def _on_density(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Traffic Density Thresholds")
        win.configure(bg="#15171c")
        win.transient(self.root)
        win.grab_set()

        fields = [
            ("LOW max active vehicles", "density_low_max", int),
            ("MEDIUM max active vehicles", "density_medium_max", int),
            ("Slow-vehicle threshold (km/h)", "slow_speed_threshold", float),
            ("Overspeed threshold (km/h)", "overspeed_threshold", float),
            ("Congestion: min active vehicles", "congestion_min_vehicles", int),
            ("Congestion: max avg speed (km/h)", "congestion_max_avg_speed", float),
        ]
        entries = {}
        tk.Label(win, text="Configurable thresholds",
                 fg="#00e5ff", bg="#15171c",
                 font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(12, 8), sticky="w")

        for i, (label, attr, _typ) in enumerate(fields, start=1):
            tk.Label(win, text=label + ":", fg="#e6e6e6", bg="#15171c",
                     font=("Segoe UI", 9)).grid(row=i, column=0, padx=12,
                                                pady=3, sticky="w")
            e = tk.Entry(win, width=12, bg="#22262e", fg="#ffffff",
                         insertbackground="#ffffff", relief="flat")
            e.insert(0, str(getattr(self.cfg, attr)))
            e.grid(row=i, column=1, padx=12, pady=3, sticky="w")
            entries[attr] = (e, _typ)

        def apply():
            parsed = {}
            for attr, (e, typ) in entries.items():
                try:
                    parsed[attr] = typ(float(e.get()))
                except ValueError:
                    messagebox.showerror("Invalid value",
                                         f"'{attr}' must be numeric.", parent=win)
                    return
            if parsed["density_medium_max"] <= parsed["density_low_max"]:
                messagebox.showerror("Invalid value",
                                     "MEDIUM max must be greater than LOW max.",
                                     parent=win)
                return
            for attr, value in parsed.items():
                setattr(self.cfg, attr, value)
            win.destroy()

        tk.Button(win, text="Apply", command=apply,
                  bg="#1f6fb2", fg="#ffffff", relief="flat", bd=0,
                  padx=18, pady=6, font=("Segoe UI", 9, "bold"),
                  cursor="hand2").grid(row=len(fields) + 1, column=0,
                                       columnspan=2, pady=12)

    # ==================================================================
    # Reports
    # ==================================================================
    def _on_export(self) -> None:
        if self.stats is None or self.stats.frames == 0:
            messagebox.showinfo("No data",
                                "There is no traffic data to report yet.")
            return
        self._generate_and_show_report(auto=False)

    def _generate_and_show_report(self, auto: bool = False) -> None:
        if self.stats is None:
            return
        self._set_status("Generating report …")
        self.root.update_idletasks()

        try:
            result = generate_all(self.stats, self.cfg,
                                  annotated_path=self.annotated_path)
        except Exception as exc:
            messagebox.showerror("Report error", str(exc))
            self._set_status("Report failed")
            return

        self._set_status("Report ready")
        self._show_report_window(result, auto)

    def _show_report_window(self, result: dict, auto: bool) -> None:
        summary = result["summary"]
        win = tk.Toplevel(self.root)
        win.title("Traffic Summary Report")
        win.configure(bg="#15171c")
        win.geometry("760x620")

        tk.Label(win, text="Traffic Summary Report",
                 fg="#00e5ff", bg="#15171c",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(10, 6))

        text_frame = tk.Frame(win, bg="#15171c")
        text_frame.pack(fill="both", expand=True, padx=12, pady=6)

        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        box = tk.Text(text_frame, bg="#0f1116", fg="#d6dde6",
                      insertbackground="#ffffff", relief="flat",
                      yscrollcommand=scrollbar.set,
                      font=("Consolas", 9), wrap="word")
        box.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=box.yview)

        box.insert("end", self._format_summary(summary))
        box.insert("end", "\n\n" + "=" * 78 + "\nOUTPUT FILES\n" + "=" * 78 + "\n")
        for key, value in result["files"].items():
            if isinstance(value, list):
                for p in value:
                    box.insert("end", f"  {key}: {p}\n")
            elif value:
                box.insert("end", f"  {key}: {value}\n")
        if result["errors"]:
            box.insert("end", "\nErrors:\n")
            for err in result["errors"]:
                box.insert("end", f"  - {err}\n")
        box.configure(state="disabled")

        btns = tk.Frame(win, bg="#15171c")
        btns.pack(fill="x", padx=12, pady=(0, 12))

        def open_dir():
            path = result["output_dir"]
            try:
                if os.name == "nt":
                    os.startfile(path)          # noqa: S606
                elif os.uname().sysname == "Darwin":
                    os.system(f'open "{path}"')
                else:
                    os.system(f'xdg-open "{path}"')
            except Exception as exc:
                messagebox.showinfo("Open folder", f"Folder:\n{path}\n\n{exc}")

        tk.Button(btns, text="Open output folder", command=open_dir,
                  bg="#22262e", fg="#e6e6e6", relief="flat", bd=0,
                  padx=14, pady=6, font=("Segoe UI", 9, "bold"),
                  cursor="hand2").pack(side="left")
        tk.Button(btns, text="Close", command=win.destroy,
                  bg="#1f6fb2", fg="#ffffff", relief="flat", bd=0,
                  padx=18, pady=6, font=("Segoe UI", 9, "bold"),
                  cursor="hand2").pack(side="right")

        if not auto:
            self.root.bell()

    # ------------------------------------------------------------------
    @staticmethod
    def _format_summary(summary: dict) -> str:
        lines: List[str] = []

        def section(title, data, indent=2):
            lines.append(title)
            lines.append("-" * len(title))
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    continue
                label = k.replace("_", " ").title()
                lines.append(f"{' ' * indent}{label:<34}: {v}")
            lines.append("")

        g = summary["general"]
        lines.append(f"Source            : {g['source']}")
        lines.append(f"Generated         : {g['report_generated']}")
        lines.append("")

        section("GENERAL INFORMATION", g)
        section("VEHICLE STATISTICS", summary["vehicles"])
        section("SPEED ANALYSIS", summary["speed"])

        lines.append("Speed distribution")
        lines.append("-" * 17)
        for k, v in summary["speed"]["distribution"].items():
            lines.append(f"  {k:<34}: {v}")
        lines.append("")

        t = summary["traffic"]
        section("TRAFFIC ANALYSIS", {k: v for k, v in t.items()
                                     if not isinstance(v, (dict, list))})

        if t["volume_over_time"]:
            lines.append("Traffic volume over time")
            lines.append("-" * 23)
            lines.append(f"  {'Interval':<18}{'Avg active':>12}{'Avg km/h':>12}{'Counted':>10}")
            for b in t["volume_over_time"]:
                lines.append(f"  {b['label']:<18}{b['avg_active']:>12.1f}"
                             f"{b['avg_speed']:>12.1f}{b['counted']:>10}")
            lines.append("")

        if t["congestion_events"]:
            lines.append("Congestion events")
            lines.append("-" * 17)
            for i, ev in enumerate(t["congestion_events"], 1):
                lines.append(f"  {i}. {ev['start']:.1f}s -> {ev['end']:.1f}s "
                             f"({ev['duration_s']:.1f}s, peak {ev['peak_vehicles']} vehicles)")
            lines.append("")

        lines.append("ASSUMPTIONS / LIMITATIONS")
        lines.append("-" * 23)
        for note in summary["assumptions"]:
            lines.append(f"  • {note}")

        return "\n".join(lines)

    # ==================================================================
    def _on_close(self) -> None:
        self.running = False
        if self.cap is not None:
            self.cap.release()
        if self.video_writer is not None:
            self.video_writer.release()
        cv2.destroyAllWindows()
        self.root.destroy()


# ==========================================================================
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--config", help="Path to a JSON config file")
    parser.add_argument("--model", help="YOLO model path (e.g. yolov8s.pt)")
    parser.add_argument("--pixels-per-meter", type=float,
                        help="Speed calibration factor")
    args = parser.parse_args()

    cfg = Config.load(args.config) if args.config and os.path.exists(args.config) \
        else Config()
    if args.model:
        cfg.model_path = args.model
    if args.pixels_per_meter:
        cfg.pixels_per_meter = args.pixels_per_meter

    root = tk.Tk()
    app = TrafficMonitorApp(root, cfg)

    # Optional auto-start from the command line
    root.mainloop()


if __name__ == "__main__":
    main()