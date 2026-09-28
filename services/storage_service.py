import os
import uuid
import cv2
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from config import Config

class StorageService:
    def __init__(self, base_storage_dir=None):
        self.base_dir = Path(base_storage_dir or Config.STORAGE_DIR)
        self.snapshots_dir = self.base_dir / "snapshots"
        self.face_data_dir = self.base_dir / "face_data"
        self._ensure_directories()

    def _ensure_directories(self):
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.face_data_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(
        self,
        frame: np.ndarray,
        prefix: str = "event",
        camera_name: str = "CAMERA_1",
        annotate_meta: bool = True,
        is_alert: bool = False,
        alert_text: Optional[str] = None
    ) -> str:
        """
        Saves a snapshot frame into storage/snapshots/YYYY/MM/DD/
        Filename format matches standard: UNAUTHORIZED_PERSON_YYYY-MM-DD_HH-MM-SS_CAM_NAME.jpg
        Returns the relative path from storage/
        """
        now = datetime.now()
        date_dir = self.snapshots_dir / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize prefix and camera_name
        clean_prefix = "".join(c if c.isalnum() or c in "_-" else "_" for c in prefix.upper())
        clean_cam = "".join(c if c.isalnum() or c in "_-" else "_" for c in camera_name.upper().replace(" ", "_"))
        time_tag = now.strftime("%Y-%m-%d_%H-%M-%S")
        uuid_short = uuid.uuid4().hex[:6]

        filename = f"{clean_prefix}_{time_tag}_{clean_cam}_{uuid_short}.jpg"
        full_path = date_dir / filename

        save_frame = frame.copy() if frame is not None else np.zeros((480, 640, 3), dtype=np.uint8)

        # Burn professional forensic timestamp and camera watermark into top/bottom of snapshot
        if annotate_meta and save_frame is not None and save_frame.size > 0:
            h, w = save_frame.shape[:2]

            # Top prominent alert banner if flagged as alert or misbehavior
            if is_alert or alert_text:
                top_banner_h = 32
                top_sub = save_frame.copy()
                cv2.rectangle(top_sub, (0, 0), (w, top_banner_h), (20, 20, 180), -1)
                cv2.addWeighted(top_sub, 0.85, save_frame, 0.15, 0, save_frame)
                msg = f"[!] CRITICAL THREAT: {alert_text or clean_prefix.replace('_', ' ')}"
                cv2.putText(save_frame, msg[:65], (12, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)

            # Bottom forensic metadata banner
            banner_h = 28
            sub = save_frame.copy()
            cv2.rectangle(sub, (0, h - banner_h), (w, h), (12, 14, 20), -1)
            cv2.addWeighted(sub, 0.75, save_frame, 0.25, 0, save_frame)
            tag_text = f"AEGIS AI SECURITY | {clean_cam} | {clean_prefix.replace('_', ' ')} | {now.strftime('%Y-%m-%d %H:%M:%S')}"
            cv2.putText(save_frame, tag_text, (10, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 240, 255), 1, cv2.LINE_AA)

        # Write image using OpenCV (high quality)
        success = cv2.imwrite(str(full_path), save_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not success:
            raise IOError(f"Failed to write snapshot to {full_path}")

        # Return relative path for database storage (e.g. snapshots/2026/09/28/...)
        rel_path = full_path.relative_to(self.base_dir)
        return str(rel_path).replace("\\", "/")

    def save_face_sample(self, frame: np.ndarray, person_id: int) -> str:
        """
        Saves a face sample crop or frame into storage/face_data/
        Returns relative path
        """
        self.face_data_dir.mkdir(parents=True, exist_ok=True)
        filename = f"person_{person_id}_{uuid.uuid4().hex[:8]}.jpg"
        full_path = self.face_data_dir / filename

        success = cv2.imwrite(str(full_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not success:
            raise IOError(f"Failed to write face sample to {full_path}")

        rel_path = full_path.relative_to(self.base_dir)
        return str(rel_path).replace("\\", "/")

    def delete_file(self, rel_path: str) -> bool:
        """
        Safely deletes a file within the storage directory, preventing path traversal.
        """
        if not rel_path:
            return False

        # Normalize and resolve target path
        clean_rel = rel_path.strip().replace("\\", "/").lstrip("/")
        full_path = (self.base_dir / clean_rel).resolve()

        # Security check: must reside inside base_dir
        if not str(full_path).startswith(str(self.base_dir.resolve())):
            raise ValueError(f"Security error: path {rel_path} escapes storage root!")

        if full_path.exists() and full_path.is_file():
            try:
                full_path.unlink()
                return True
            except Exception as e:
                print(f"Error deleting file {full_path}: {e}")
                return False
        return False

    def get_storage_statistics(self) -> dict:
        """
        Computes disk storage statistics:
        - Snapshots total size (MB)
        - Snapshots count
        - Oldest snapshot timestamp
        - Face data size (MB)
        - Total storage used
        """
        total_snapshots_size = 0
        snapshots_count = 0
        oldest_snapshot_time = None

        if self.snapshots_dir.exists():
            for root, _, files in os.walk(self.snapshots_dir):
                for file in files:
                    if file.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        file_path = Path(root) / file
                        try:
                            stat = file_path.stat()
                            total_snapshots_size += stat.st_size
                            snapshots_count += 1
                            mtime = datetime.fromtimestamp(stat.st_mtime)
                            if oldest_snapshot_time is None or mtime < oldest_snapshot_time:
                                oldest_snapshot_time = mtime
                        except (OSError, FileNotFoundError):
                            continue

        total_face_size = 0
        face_count = 0
        if self.face_data_dir.exists():
            for file in self.face_data_dir.glob("*.*"):
                try:
                    stat = file.stat()
                    total_face_size += stat.st_size
                    face_count += 1
                except (OSError, FileNotFoundError):
                    continue

        # Database file size
        db_size = 0
        db_file = Path("instance") / "security.db"
        if db_file.exists():
            try:
                db_size = db_file.stat().st_size
            except Exception:
                pass

        total_bytes = total_snapshots_size + total_face_size + db_size

        # Disk capacity metrics via shutil
        import shutil
        total_disk, used_disk, free_disk = shutil.disk_usage(str(self.base_dir))
        used_pct = round((used_disk / total_disk) * 100, 1)

        # Build visual ascii bar indicator
        blocks = int((used_pct / 100.0) * 16)
        bar_str = ("█" * blocks) + ("░" * (16 - blocks)) + f" {int(used_pct)}%"

        return {
            "snapshots_count": snapshots_count,
            "snapshots_size_mb": round(total_snapshots_size / (1024 * 1024), 2),
            "face_data_count": face_count,
            "face_data_size_mb": round(total_face_size / (1024 * 1024), 2),
            "database_size_mb": round(db_size / (1024 * 1024), 2),
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "total_size_gb": round(total_bytes / (1024 * 1024 * 1024), 3),
            "disk_total_gb": round(total_disk / (1024 * 1024 * 1024), 1),
            "disk_used_gb": round(used_disk / (1024 * 1024 * 1024), 1),
            "disk_free_gb": round(free_disk / (1024 * 1024 * 1024), 1),
            "disk_used_percent": used_pct,
            "storage_bar": bar_str,
            "oldest_snapshot": oldest_snapshot_time.strftime("%Y-%m-%d %H:%M:%S") if oldest_snapshot_time else "None"
        }

# Global singleton instance
storage_service = StorageService()
