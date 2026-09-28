import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import current_app
from config import Config
from models import db, Event, Notification, SystemSetting
from services.storage_service import storage_service

class RetentionService:
    @staticmethod
    def get_retention_days() -> int:
        """Returns configured retention days from DB setting or Config default"""
        try:
            val = SystemSetting.get("RETENTION_DAYS", str(Config.RETENTION_DAYS))
            return max(1, int(val))
        except Exception:
            return Config.RETENTION_DAYS

    @classmethod
    def run_cleanup(cls, retention_days: int = None) -> dict:
        """
        Deletes snapshot images and associated event records older than retention_days.
        Also cleans empty date folders in storage/snapshots/.
        Returns report dict.
        """
        if retention_days is None:
            retention_days = cls.get_retention_days()

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        print(f"[RetentionService] Running cleanup for data older than {cutoff_date} ({retention_days} days)...")

        deleted_events = 0
        deleted_files = 0
        freed_bytes = 0

        # 1. Find all events created before cutoff_date
        old_events = Event.query.filter(Event.timestamp < cutoff_date).all()
        for ev in old_events:
            if ev.snapshot_path:
                full_path = Path(Config.STORAGE_DIR) / ev.snapshot_path.lstrip("/\\")
                if full_path.exists() and full_path.is_file():
                    try:
                        freed_bytes += full_path.stat().st_size
                        full_path.unlink()
                        deleted_files += 1
                    except Exception as e:
                        print(f"Error removing snapshot file {full_path}: {e}")

            # Delete associated notifications
            Notification.query.filter_by(event_id=ev.id).delete()
            db.session.delete(ev)
            deleted_events += 1

        db.session.commit()

        # 2. Sweep storage/snapshots directory for orphaned files older than cutoff
        snapshots_root = Path(Config.SNAPSHOTS_DIR)
        if snapshots_root.exists():
            for root, dirs, files in os.walk(snapshots_root, topdown=False):
                for f in files:
                    file_path = Path(root) / f
                    try:
                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if mtime < cutoff_date:
                            freed_bytes += file_path.stat().st_size
                            file_path.unlink()
                            deleted_files += 1
                    except Exception:
                        pass
                # Remove empty directories
                try:
                    if root != str(snapshots_root) and not os.listdir(root):
                        os.rmdir(root)
                except Exception:
                    pass

        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        print(f"[RetentionService] Completed: {deleted_events} events deleted, {deleted_files} files deleted, {freed_mb} MB freed.")

        report = {
            "status": "success",
            "retention_days": retention_days,
            "cleanup_timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "cutoff_date": cutoff_date.strftime("%Y-%m-%d %H:%M:%S"),
            "deleted_events": deleted_events,
            "deleted_files": deleted_files,
            "freed_mb": freed_mb
        }

        # Store in system settings for audit & dashboard
        try:
            import json
            SystemSetting.set("LAST_CLEANUP_REPORT", json.dumps(report), description="Audit report of most recent retention sweep")
        except Exception:
            pass

        return report

    @classmethod
    def get_cleanup_metadata(cls) -> dict:
        import json
        last_report_json = SystemSetting.get("LAST_CLEANUP_REPORT")
        last_report = {}
        if last_report_json:
            try:
                last_report = json.loads(last_report_json)
            except Exception:
                last_report = {}

        retention_days = cls.get_retention_days()
        # Next scheduled cleanup: typically 24 hours from last, or next midnight
        next_cleanup = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d 03:00:00")

        return {
            "retention_days": retention_days,
            "last_cleanup": last_report.get("cleanup_timestamp", "System Setup"),
            "next_cleanup": next_cleanup,
            "last_deleted_events": last_report.get("deleted_events", 0),
            "last_deleted_files": last_report.get("deleted_files", 0),
            "last_freed_mb": last_report.get("freed_mb", 0.0)
        }

retention_service = RetentionService()
