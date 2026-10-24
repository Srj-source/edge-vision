<div align="center">

# 🚦 IITR TMI — Real-Time Traffic Monitoring & Intelligence

### AI-powered vehicle detection, tracking, speed estimation, and traffic analytics

<p>
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=20&pause=900&color=00C9A7&center=true&vCenter=true&width=750&lines=Detect+vehicles+in+real+time;Track+movement+with+unique+IDs;Estimate+speed+with+calibration;Turn+traffic+video+into+useful+insights" alt="Animated project tagline" />
</p>

<p>
  <img src="https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white" alt="OpenCV" />
  <img src="https://img.shields.io/badge/YOLO-Object%20Detection-111827?style=for-the-badge" alt="YOLO" />
  <img src="https://img.shields.io/badge/Analytics-Traffic%20Insights-00A884?style=for-the-badge" alt="Analytics" />
</p>

**A computer-vision project for turning live camera feeds and traffic videos into actionable traffic insights.**

</div>

---

## ✨ About the Project

**IITR TMI (Traffic Monitoring & Intelligence)** is designed to analyze traffic video using computer vision and object tracking. It aims to detect and classify vehicles, keep track of them across frames, estimate their speed when calibration is available, count line crossings, and summarize traffic conditions.

The project is intended to support traffic observation and analysis. Speed values are **estimates**, not certified measurements, and depend on camera setup and calibration.

## 🎯 Key Features

| Feature | What it does |
|---|---|
| 🚘 Vehicle detection | Detects cars, motorcycles, buses, and trucks using YOLO |
| 🧭 Object tracking | Assigns tracking IDs and follows vehicles across frames |
| ⏱️ Speed estimation | Estimates speed from movement using configurable calibration |
| 🔢 Vehicle counting | Counts vehicles crossing a virtual line or entering a region |
| 🚦 Traffic density | Labels traffic as **LOW**, **MEDIUM**, or **HIGH** using configurable thresholds |
| 📊 Live statistics | Shows counts, active vehicles, average estimated speed, and congestion indicators |
| 📁 Report generation | Designed to export traffic summaries, CSV data, and PDF reports |
| 📈 Visual analytics | Supports charts for vehicle types, traffic volume, speed, and density |

## 🔄 How It Works

```text
Traffic video / Webcam
          │
          ▼
   Read video frames
          │
          ▼
 YOLO vehicle detection
          │
          ▼
 Object tracking (e.g., ByteTrack)
          │
          ├──────────────► Vehicle IDs and classes
          │
          ├──────────────► Line-crossing vehicle counts
          │
          └──────────────► Calibrated speed estimates
                                   │
                                   ▼
                         Traffic density & statistics
                                   │
                                   ▼
                      Dashboard, charts, and reports
```

## 🧰 Technology Stack

- **Language:** Python 3.x
- **Computer vision:** OpenCV
- **Object detection:** Ultralytics YOLO
- **Tracking:** ByteTrack or another compatible tracker
- **Data processing:** NumPy, Pandas
- **Visualization:** Matplotlib or Plotly
- **PDF reports:** ReportLab

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd <your-project-folder>
```

Replace the placeholders with your actual GitHub repository URL and folder name.

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

If the repository includes a `requirements.txt` file:

```bash
pip install -r requirements.txt
```

Otherwise, install the core packages:

```bash
pip install opencv-python ultralytics numpy pandas matplotlib reportlab
```

> Install and configure the tracker supported by your implementation. Exact setup steps may vary with the YOLO and tracking versions used.

### 4. Run the project

Use the entry-point command provided by your repository. For example:

```bash
python main.py
```

If your main script has a different name, replace `main.py` with that filename.

## 🖥️ Suggested Monitoring Dashboard

A useful monitoring screen can include:

- Annotated video with bounding boxes and tracking IDs
- Vehicle class and detection confidence
- Estimated speed in km/h, when calibration is configured
- Virtual counting line and current FPS
- Total count and counts by vehicle type
- Vehicles entering/exiting and currently visible
- Traffic density and congestion warnings
- Export controls for the final report

## 📏 Important Note on Speed Calibration

Pixel movement alone does **not** provide reliable real-world speed. For meaningful km/h estimates, configure a reference distance or other camera-to-road calibration, and account for video FPS and perspective. Results should be treated as estimates unless validated against a trusted measurement system.

## 📊 Report & Analytics Goals

The intended final report may include:

- Recording source, duration, resolution, and FPS
- Unique vehicles detected and vehicles counted
- Counts by vehicle type
- Average, maximum, and minimum estimated speed where meaningful
- Speed-range distribution and slow-moving vehicle count
- Traffic density over time and possible congestion events
- CSV data and a PDF report with tables/charts

Only metrics implemented and collected by the running version should be presented as actual results.

## 🗺️ Project Roadmap

- [ ] Configure webcam and uploaded-video input
- [ ] Detect and classify vehicles
- [ ] Maintain tracking IDs across frames
- [ ] Add configurable line-crossing counts
- [ ] Configure and validate speed calibration
- [ ] Calculate traffic density and congestion indicators
- [ ] Add live charts and a monitoring dashboard
- [ ] Export CSV and PDF summaries
- [ ] Test on different road scenes and lighting conditions

## 👥 Credits & Team

<div align="center">

| Role | Name |
|---|---|
| **Project made by** | **Suraj Kumar Gupta** |
| **Designed by** | **Jatin** |
| **With contributions from** | **Harsh Pandey and Chatyna** |

</div>

*Built as a collaborative traffic-monitoring project. Update the credits to reflect each contributor’s exact role.*

## 🤝 Contributing

Ideas, bug reports, testing feedback, and improvements are welcome. If you contribute, describe the change clearly and include screenshots or sample results when useful.

## 📄 License

No license has been specified yet. Add a `LICENSE` file before distributing or reusing this project publicly.

---

<div align="center">

### 🚦 Detect. Track. Understand.

*IITR TMI — bringing computer vision to traffic analysis.*

</div>
