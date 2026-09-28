# Deploying to Render (Render.com)

This guide provides instructions for deploying the **Intelligent Premises Monitoring & Security System** to [Render.com](https://render.com).

The project is fully pre-configured for Render with:
- **`render.yaml`**: One-click Render Blueprint (Infrastructure-as-Code)
- **`Dockerfile` & `.dockerignore`**: Production container with pre-installed OpenCV system libraries (`libgl1`, `libglib2.0-0`), CPU-optimized PyTorch, and Gunicorn
- **`build.sh` & `Procfile`**: Native Python runtime deployment fallback
- **`gunicorn.conf.py`**: Production WSGI server settings configured for multi-threaded AI inference, video streaming, and SSE alert pushes
- **`instance/security_dump.sql`**: Complete database schema and seed data dump

---

## Deployment Options

### Option 1: One-Click Render Blueprint (Recommended)

1. **Commit and push this project to GitHub or GitLab**:
   ```bash
   git add .
   git commit -m "Configure production deployment for Render"
   git remote add origin https://github.com/<your-username>/<your-repo-name>.git
   git branch -M main
   git push -u origin main
   ```

2. **Deploy on Render**:
   - Log into [Render Dashboard](https://dashboard.render.com).
   - Click **New +** at the top right and select **Blueprint**.
   - Connect your Git repository.
   - Render will detect `render.yaml` and configure:
     - **Service Type**: Web Service
     - **Environment**: Docker
     - **Health Check Path**: `/login`
     - **Environment Variables**: Pre-populated with secure defaults
   - Click **Apply**.
   - Render will build the container and deploy the application live!

---

### Option 2: Manual Web Service Deployment (Docker)

If you prefer to configure the Web Service manually via the Render UI:

1. In Render Dashboard, click **New +** -> **Web Service**.
2. Select **Build and deploy from a Git repository** and connect your repository.
3. Configure the service settings:
   - **Name**: `intelligent-premises-security`
   - **Region**: Select closest region (e.g. `Oregon (US West)` or `Frankfurt (EU Central)`)
   - **Branch**: `main`
   - **Runtime**: `Docker`
   - **Plan**: `Free` (or `Starter` for 24/7 uptime)
4. Add **Environment Variables**:
   | Variable | Value | Description |
   | :--- | :--- | :--- |
   | `PORT` | `5000` | Application HTTP port |
   | `SECRET_KEY` | *(Click Generate)* | Secure session key |
   | `ADMIN_USERNAME` | `admin` | Initial admin username |
   | `ADMIN_PASSWORD` | `Admin@123` | Initial admin password |
   | `CAMERA_SOURCE` | `0` | Default camera index or RTSP URL |
   | `DETECTION_CONFIDENCE` | `0.45` | YOLO detection confidence threshold |
   | `LOITERING_THRESHOLD` | `60` | Dwell time limit in seconds |
   | `RESTRICTED_ZONE_ENABLED` | `true` | Enable restricted zone spatial security |
5. Click **Create Web Service**.

---

### Option 3: Native Python Runtime Deployment

If you do not want to use Docker:

1. In Render Dashboard, create a **Web Service** with runtime **Python 3**.
2. Set the following build and start commands:
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn --config gunicorn.conf.py "app:create_app()"`
3. Add the same Environment Variables as above.

---

## Database & Data Persistence

### SQLite with Render Persistent Disk (Free/Starter)
By default, the application runs on SQLite. On Render's Free tier, disk storage is ephemeral (resets on restart). 
To persist snapshots and the database across restarts:
- In your Render Web Service dashboard, go to **Disks** -> **Add Disk**.
- **Mount Path**: `/app/storage`
- **Size**: 1 GB or more.
- Set environment variables:
  - `STORAGE_DIR=/app/storage`
  - `SQLITE_PATH=/app/storage/security.db`

### Render PostgreSQL (Managed Database)
To use a managed relational database instead of SQLite:
1. In Render Dashboard, click **New +** -> **PostgreSQL**.
2. Copy the **Internal Database URL**.
3. In your Web Service environment variables, add:
   - `DATABASE_URL`: *(paste the Render Postgres URL)*
4. The application automatically adapts the `postgres://` prefix to `postgresql://` for SQLAlchemy 2.0 compatibility and auto-creates all tables on startup.

---

## Camera Feeds in Cloud Environments

Cloud virtual machines (like Render) do not have a physical USB webcam attached. The application handles this automatically:

1. **Intelligent Synthetic CCTV Simulator (Default)**:
   - When no physical webcam is found, the system automatically activates the built-in synthetic security camera generator.
   - It simulates realistic premises surveillance with moving subjects, line crossings, and bounding boxes so all features, events, and HUD overlays work out of the box.

2. **Connecting a Real IP / RTSP Camera**:
   - To monitor a real location from Render, point the camera source to your public or VPN-accessible RTSP stream:
     ```env
     CAMERA_SOURCE=rtsp://user:password@camera-ip:554/stream1
     ```

---

## Post-Deployment Verification

1. Once the deploy status is **Live**, open your Render URL:
   ```
   https://<your-service-name>.onrender.com
   ```
2. Navigate to `/login`.
3. Sign in with the admin credentials:
   - **Username**: `admin` (or your `ADMIN_USERNAME`)
   - **Password**: `Admin@123` (or your `ADMIN_PASSWORD`)
4. Verify the SOC Dashboard, Live Monitoring stream, Restricted Zones, and Event logs.
