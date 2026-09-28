import os
import sys
import time
import logging
import threading
from pathlib import Path
from flask import Flask, render_template, session, g

from config import Config
from models import db, User, Camera, SystemSetting
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.monitoring import monitoring_bp
from routes.people import people_bp
from routes.events import events_bp
from routes.cameras import cameras_bp
from routes.notifications import notifications_bp
from routes.storage_routes import storage_bp
from routes.settings import settings_bp

from services.camera_service import camera_service
from services.face_recognition_service import face_recognition_service
from services.retention_service import retention_service
from services.notification_service import notification_service

def setup_logging():
    log_dir = Path("instance")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "premises_security.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_file), encoding="utf-8")
        ]
    )

def start_background_retention_scheduler(app):
    """Background thread that executes the 30-day retention cleanup daily"""
    def scheduler_loop():
        while True:
            # Sleep 24 hours (86400 seconds) between automatic cleanups
            time.sleep(86400)
            try:
                with app.app_context():
                    print("[BackgroundScheduler] Running automated 30-day data retention cleanup...")
                    report = retention_service.run_cleanup()
                    print(f"[BackgroundScheduler] Automated cleanup finished: {report}")
            except Exception as e:
                print(f"[BackgroundScheduler] Error during automatic cleanup: {e}")

    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()

def create_app(config_class=Config):
    setup_logging()
    logger = logging.getLogger("PremisesSecurity")
    logger.info("Initializing Intelligent Premises Monitoring & Security System...")

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure directories
    os.makedirs(app.config["STORAGE_DIR"], exist_ok=True)
    os.makedirs(app.config["SNAPSHOTS_DIR"], exist_ok=True)
    os.makedirs(app.config["FACE_DATA_DIR"], exist_ok=True)
    os.makedirs(app.config["MODELS_DIR"], exist_ok=True)
    os.makedirs("instance", exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(people_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(storage_bp)
    app.register_blueprint(settings_bp)

    # Template context processor for global UI variables
    @app.context_processor
    def inject_global_ui():
        unread_notifs = 0
        current_user = None
        if "user_id" in session:
            try:
                unread_notifs = notification_service.get_unread_count()
                current_user = db.session.get(User, session["user_id"])
            except Exception:
                pass
        return {
            "current_user": current_user,
            "unread_notifications_count": unread_notifs,
            "camera_status": camera_service.get_status()
        }

    # Custom Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("base.html", error_title="404 - Page Not Found", error_message="The requested resource could not be found."), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("base.html", error_title="403 - Forbidden", error_message="You do not have permission to access this resource."), 403

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("base.html", error_title="500 - Internal Server Error", error_message="An internal server error occurred."), 500

    # Initialize DB tables and services within app context
    with app.app_context():
        db.create_all()

        # Seed default camera if none exists
        if Camera.query.count() == 0:
            default_cam = Camera(
                name="Main Entrance (Camera #1)",
                source=Config.CAMERA_SOURCE,
                source_type="webcam" if Config.CAMERA_SOURCE.isdigit() else "rtsp",
                resolution="640x480",
                fps=25,
                confidence_threshold=Config.DETECTION_CONFIDENCE,
                face_threshold=Config.FACE_RECOGNITION_THRESHOLD,
                line_orientation=Config.LINE_ORIENTATION,
                line_position=Config.LINE_POSITION,
                enabled=True
            )
            db.session.add(default_cam)
            db.session.commit()
            logger.info("Created default camera in database.")

        # Seed default admin user if none exists
        if User.query.count() == 0:
            admin_user = os.environ.get("ADMIN_USERNAME", "admin")
            admin_pass = os.environ.get("ADMIN_PASSWORD", "Admin@123")
            admin_name = os.environ.get("ADMIN_FULL_NAME", "System Administrator")
            default_admin = User(
                username=admin_user,
                role="admin",
                full_name=admin_name
            )
            default_admin.set_password(admin_pass)
            db.session.add(default_admin)
            db.session.commit()
            logger.info(f"Created default admin user '{admin_user}' in database.")

        # Load known faces from DB into memory cache
        face_recognition_service.load_known_faces(app)

        # Initialize and start camera monitoring service
        cam = Camera.query.filter_by(enabled=True).first()
        if cam:
            camera_service.configure_from_camera(cam)
        camera_service.init_app(app)
        camera_service.start_monitoring()

        # Start background daily retention cleanup thread
        start_background_retention_scheduler(app)

    logger.info("Application initialized and monitoring service started.")
    return app

if __name__ == "__main__":
    app = create_app()
    # Run development server
    port = int(os.environ.get("PORT", 5000))
    print(f"\n=======================================================")
    print(f" Intelligent Premises Security System is LIVE!")
    print(f" Access URL: http://127.0.0.1:{port}")
    print(f"=======================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
