"""
Database Initialization Script
Creates all tables, default camera, and default system settings.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from models import db, Camera, SystemSetting
from config import Config

def init_db():
    app = create_app()
    with app.app_context():
        print("Creating all database tables in SQLite...")
        db.create_all()

        # Seed default camera if none exists
        if Camera.query.count() == 0:
            cam = Camera(
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
            db.session.add(cam)
            print("Seeded default Camera: Main Entrance")

        # Seed default system settings
        defaults = {
            "DETECTION_CONFIDENCE": (str(Config.DETECTION_CONFIDENCE), "YOLO detection confidence threshold"),
            "FACE_RECOGNITION_THRESHOLD": (str(Config.FACE_RECOGNITION_THRESHOLD), "Cosine similarity threshold for face match"),
            "EVENT_COOLDOWN": (str(Config.EVENT_COOLDOWN), "Seconds before recording a duplicate detection event"),
            "RETENTION_DAYS": (str(Config.RETENTION_DAYS), "Data retention lifespan in days"),
            "FRAME_SKIP": (str(Config.FRAME_SKIP), "Frame skipping factor for inference"),
            "LINE_POSITION": (str(Config.LINE_POSITION), "Virtual boundary line position (0.0 to 1.0)"),
            "LINE_ORIENTATION": (Config.LINE_ORIENTATION, "Virtual boundary line orientation")
        }

        for key, (val, desc) in defaults.items():
            if not SystemSetting.query.filter_by(setting_name=key).first():
                db.session.add(SystemSetting(setting_name=key, setting_value=val, description=desc))
                print(f"Seeded setting: {key} = {val}")

        db.session.commit()
        print("Database initialization completed successfully.")

if __name__ == "__main__":
    init_db()
