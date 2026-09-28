# AEGIS AI | Intelligent Premises Monitoring & Security System

A production-grade, full-stack real-time premises surveillance and intelligent security monitoring application built with **Flask**, **OpenCV**, **YOLOv8**, and **OpenCV Deep Learning Face Recognition (YuNet + SFace)** with SQLite storage and automated 30-day data retention.

---

## 1. System Overview

AEGIS AI transforms standard webcams, USB cameras, and network CCTV/IP cameras (via RTSP) into an autonomous premise sentry. The system continuously analyzes video streams in real-time, detecting humans, vehicles, animals, and common objects, tracking trajectory vectors across virtual boundary lines, performing biometric facial recognition (classifying subjects as **KNOWN** or **UNKNOWN**), capturing forensic event snapshots, and alerting operators with audio-visual notifications.

```
                    ┌──────────────────────────┐
                    │ Camera / RTSP / Webcam   │
                    └────────────┬─────────────┘
                                 │ Frame Capture
                                 ▼
                    ┌──────────────────────────┐
                    │  YOLOv8 Object Detection │
                    │ (Person/Vehicle/Animals) │
                    └────────────┬─────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       ┌──────────────────┐            ┌──────────────────┐
       │ Centroid Tracker │            │ Face Detection   │
       │ & Boundary Line  │            │ (YuNet) + SFace  │
       │  (Entry / Exit)  │            │ Face Recognition │
       └─────────┬────────┘            └─────────┬────────┘
                 │                               │
                 └───────────────┬───────────────┘
                                 │ Event Deduplication & Cooldown
                                 ▼
                    ┌──────────────────────────┐
                    │  Event & Snapshot Engine │
                    │ (storage/snapshots/Y/M/D)│
                    └────────────┬─────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       ┌──────────────────┐            ┌──────────────────┐
       │  SQLite Database │            │ SSE Real-Time    │
       │ (30-Day Purge)   │            │ Web Notification │
       └──────────────────┘            └──────────────────┘
```

---

## 2. Key Capabilities & Features

1. **Object Detection**:
   - Modern YOLOv8 neural network detecting people, vehicles (cars, motorcycles, bicycles, buses, trucks), animals (dogs, cats, wildlife), and luggage/objects.
   - Color-coded bounding boxes and HUD overlays (Emerald Green for Known, Crimson Red for Unknown, Electric Blue for Vehicles, Amber for Animals).

2. **Facial Biometric Recognition**:
   - Deep neural network pipeline using **YuNet** face detection and **SFace** 128-dimensional L2-normalized feature embeddings.
   - Cosine similarity matching against an enrolled subjects database with configurable thresholds.
   - Built-in biometric quality validator checking face dimensions, illumination glare/darkness, and motion blur (Laplacian variance).
   - In-memory embedding cache for sub-millisecond recognition.

3. **Entry / Exit Virtual Boundary Tracking**:
   - Configurable virtual tripwire (horizontal or vertical line at customizable percentages of frame dimensions).
   - Centroid Euclidean distance tracker tracking object trajectories across consecutive frames.
   - Automatically classifies movement as **ENTRY** (crossing forward) or **EXIT** (crossing reverse).

4. **Event Deduplication & Cooldown Engine**:
   - Configurable cooldown (default 30 seconds) ensuring identical subjects remaining in camera view do not flood the database with duplicate records.
   - Immediate event capture upon line crossing transitions.

5. **Hierarchical Snapshot Storage**:
   - Automatically stores high-resolution forensic snapshots under `storage/snapshots/YYYY/MM/DD/event_<timestamp>_<uuid>.jpg`.
   - Snapshot paths stored as relational references in SQLite.

6. **Automated 30-Day Data Retention**:
   - Automated background scheduler runs daily to delete snapshot images, orphaned folders, and database event records older than `RETENTION_DAYS` (default 30).
   - Dedicated **Storage & Retention** UI showing disk telemetry, oldest snapshot on record, and an instant "Run Cleanup Now" trigger.

7. **Real-Time Alerting System**:
   - Server-Sent Events (SSE) `/api/notifications/stream` for zero-delay browser push alerts.
   - Web Audio API synthesizer generating dual-tone emergency chimes for unknown person detection.
   - On-screen toast notifications with snapshot preview thumbnails and Web Notifications API support.

8. **Resilient Camera Service**:
   - Supports webcam indexes (`0`, `1`, etc.), RTSP network streams (`rtsp://user:pass@ip:port/stream`), and video files.
   - Automatic reconnect loop with exponential backoff on disconnect.
   - Seamless **synthetic security feed fallback** ensuring complete testing and demo operation even when no physical webcam is plugged in.

---

## 3. Technology Stack

- **Backend**: Python 3.10+, Flask, Flask-SQLAlchemy, SQLite3, OpenCV (`opencv-python`), NumPy, Ultralytics YOLOv8, PyTorch.
- **Frontend**: HTML5, Vanilla Modern CSS3, JavaScript (Fetch API, SSE, Web Audio API), Chart.js.
- **Security**: Werkzeug password hashing (`scrypt`), session cookies, path traversal protection, role-based authorization (`admin`, `monitor`).

---

## 4. Directory Structure

```
premises_security/
│
├── app.py                     # Main application factory & server entrypoint
├── config.py                  # Core configuration constants & paths
├── requirements.txt           # Python package dependencies
├── README.md                  # Comprehensive technical documentation
├── .env.example               # Environment variables template
├── .env                       # Active environment configuration
│
├── instance/
│   ├── security.db            # Primary SQLite relational database
│   └── premises_security.log  # Application activity logs
│
├── models/                    # Relational SQLAlchemy database models
│   ├── __init__.py
│   ├── user.py                # Users & role management
│   ├── person.py              # Persons & FaceEmbeddings
│   ├── camera.py              # Camera configurations & line settings
│   ├── event.py               # Security events & snapshot paths
│   ├── notification.py        # Alerts & read statuses
│   └── system_setting.py      # Dynamic configuration settings
│
├── routes/                    # Modular Flask blueprints & controllers
│   ├── __init__.py            # Auth decorators (@login_required, @admin_required)
│   ├── auth.py                # Login, logout, session management
│   ├── dashboard.py           # Dashboard metrics & Chart.js telemetry
│   ├── monitoring.py          # Live stream & camera controls
│   ├── people.py              # Subject directory & face enrollment
│   ├── events.py              # Event search, filter & CSV export
│   ├── cameras.py             # Camera settings & RTSP management
│   ├── notifications.py       # Notification feeds & SSE stream
│   ├── storage_routes.py      # Disk stats, retention & secure image serving
│   └── settings.py            # Global thresholds & boundary settings
│
├── services/                  # Computer vision & business logic
│   ├── __init__.py
│   ├── camera_service.py      # Background capture thread, reconnects, synthetic feed
│   ├── detection_service.py   # YOLOv8 object inference & HUD overlay rendering
│   ├── face_recognition_service.py # YuNet detection, SFace 128-d embeddings, cache
│   ├── tracking_service.py    # Centroid tracking & Entry/Exit line crossing
│   ├── event_service.py       # Snapshot saving, cooldown de-duplication
│   ├── notification_service.py# Thread-safe SSE broadcaster & queues
│   ├── retention_service.py   # 30-day purge of files & database rows
│   └── storage_service.py     # File path security & disk usage calculation
│
├── templates/                 # Jinja2 responsive templates
│   ├── base.html              # Cyber-security dark theme layout
│   ├── login.html             # Secure login screen
│   ├── dashboard.html         # Main overview, cards & Chart.js graph
│   ├── monitor.html           # Full live surveillance console
│   ├── events.html            # Event search, filtering & snapshot modal
│   ├── event_detail.html      # Forensic event breakdown
│   ├── people.html            # Subject directory
│   ├── face_enrollment.html   # Biometric capture studio
│   ├── cameras.html           # Camera source setup
│   ├── notifications.html     # Alert history
│   ├── storage.html           # 30-day retention & disk metrics
│   └── settings.html          # Operational thresholds
│
├── static/
│   ├── css/style.css          # Command center dark CSS design system
│   └── js/
│       ├── dashboard.js       # Live chart & metrics poller
│       ├── monitor.js         # Camera command controller
│       └── notifications.js   # SSE listener & audio chime generator
│
├── storage/                   # File storage root
│   ├── snapshots/             # Snapshots partitioned by YYYY/MM/DD
│   └── face_data/             # Enrolled facial crops
│
├── models_data/               # Pre-trained deep learning weights
│   ├── face_detection_yunet_2023mar.onnx
│   ├── face_recognition_sface_2021dec.onnx
│   └── yolov8n.pt
│
└── scripts/
    ├── download_models.py     # Model downloader utility
    ├── init_db.py             # Schema creation & default camera seeding
    ├── create_admin.py        # Administrator account provisioning
    └── cleanup_old_data.py    # Automated retention CLI runner
```

---

## 5. Installation & Windows Setup

### Step 1: Clone or Navigate to Directory
```powershell
cd c:\Users\AKSHARA\OneDrive\Desktop\new\lakshmi
```

### Step 2: Create and Activate Virtual Environment (Optional)
```powershell
python -m venv venv
.\venv\Scripts\activate
```

### Step 3: Install Required Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Download Deep Learning Model Weights
```powershell
python scripts/download_models.py
```
*Downloads YuNet, SFace, and YOLOv8n into `models_data/`.*

### Step 5: Initialize the SQLite Database
```powershell
python scripts/init_db.py
```

### Step 6: Create the Default Administrator Account
```powershell
python scripts/create_admin.py
```
*Default login created:*
- **Username**: `admin`
- **Password**: `Admin@123`
*(Or pass custom credentials: `python scripts/create_admin.py <username> <password> <fullname>`)*

### Step 7: Start the Application
```powershell
python app.py
```
Open your browser to: **http://127.0.0.1:5000**

---

## 6. Camera Configuration & RTSP Setup

Navigate to **Cameras** (`/cameras`) to configure video feeds:

- **Local USB Webcam**: Set Source Type to `webcam` and Source to `0` (or `1` for secondary USB cam).
- **CCTV / IP Camera (RTSP)**: Set Source Type to `rtsp` and Source to your camera URL, e.g.:
  ```
  rtsp://admin:SecurityPass2026@192.168.1.120:554/h264Preview_01_main
  ```
- **Virtual Boundary**: Configure whether the boundary is `horizontal` or `vertical`, and its position across the frame (e.g., `0.50` for center).
- **Resilience**: If the physical camera is disconnected or busy, the system automatically falls back to an intelligent **Synthetic Premises Feed** so monitoring and recognition never crash.

---

## 7. Face Enrollment Workflow

1. Navigate to **People** (`/people`) and click **+ Register New Person**. Enter full name and ID badge code.
2. Navigate to **Face Enrollment** (`/face-enrollment`).
3. Select the subject from the dropdown.
4. Align the subject's face inside the oval target guide.
5. Click **Capture Face Sample** (capture 3–5 samples with slight head angles for optimal matching), or upload portrait photos.
6. The system checks lighting, blur, and face size, computes the 128-d SFace embedding, and updates the in-memory database.
7. Return to **Live Monitoring**: whenever this subject enters the camera frame, their bounding box turns **Emerald Green** labeled **KNOWN: [Name]**. Unenrolled individuals trigger an immediate **Crimson Red** warning **🚨 UNKNOWN PERSON DETECTED**.

---

## 8. 30-Day Automated Retention Mechanism

1. **Scheduled Cleanup**: The Flask application launches a background thread that executes daily.
2. **Purge Logic**: Any snapshot file in `storage/snapshots/` whose creation date is older than `RETENTION_DAYS` (default: 30 days) is unlinked from disk.
3. **Database Consistency**: All corresponding rows in `events` and `notifications` are removed atomically to prevent orphaned data.
4. **On-Demand Execution**: Go to **Storage & Retention** (`/storage`) and click **🧹 Run Retention Cleanup Now** to execute a manual sweep at any time, or run:
   ```powershell
   python scripts/cleanup_old_data.py 30
   ```

---

## 9. Security & Hardening

- **Passwords**: Hashed with Werkzeug `scrypt` using per-user cryptographic salts. Plaintext passwords are never stored or logged.
- **Path Traversal Protection**: The `/storage/<filename>` endpoint enforces strict filesystem containment against the root storage directory, aborting with HTTP 403 on traversal attempts.
- **Access Control**: Role-based access control enforces `admin_required` on all user mutations, camera updates, face enrollments, and retention purges.
