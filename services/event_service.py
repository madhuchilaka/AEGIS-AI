import time
import json
import threading
from datetime import datetime
from typing import Optional, Dict, Tuple
import numpy as np
from config import Config
from models import db, Event, Camera, Person, SystemSetting, Notification
from services.storage_service import storage_service
from services.notification_service import notification_service

class EventService:
    def __init__(self):
        # Cooldown map: (entity_type, identifier, event_sub_type) -> float (timestamp)
        self.cooldown_tracker: Dict[Tuple[str, str, str], float] = {}
        self.lock = threading.Lock()

    def get_cooldown_seconds(self) -> int:
        try:
            val = SystemSetting.get("EVENT_COOLDOWN", str(Config.EVENT_COOLDOWN))
            return max(5, int(val))
        except Exception:
            return Config.EVENT_COOLDOWN

    def should_record_event(self, entity_type: str, identifier: str, event_type: str) -> bool:
        """
        Checks if cooldown has elapsed for this entity and event type.
        Critical security alerts (UNAUTHORIZED, RESTRICTED_ZONE) have shorter cooldown.
        """
        key = (entity_type, str(identifier), event_type)
        now = time.time()
        base_cooldown = self.get_cooldown_seconds()

        # Shorter cooldown for critical breaches so new angles/incidents are logged
        if "UNAUTHORIZED" in event_type or "RESTRICTED" in event_type or "SUSPICIOUS" in event_type or "LOITERING" in event_type:
            cooldown = max(8, int(base_cooldown * 0.4))
        else:
            cooldown = base_cooldown

        with self.lock:
            # Clean up old tracker keys if list gets large (> 2000)
            if len(self.cooldown_tracker) > 2000:
                cutoff = now - 3600
                self.cooldown_tracker = {k: v for k, v in self.cooldown_tracker.items() if v > cutoff}

            last_time = self.cooldown_tracker.get(key, 0.0)
            if (now - last_time) >= cooldown:
                self.cooldown_tracker[key] = now
                return True
            return False

    def record_detection_event(
        self,
        frame: np.ndarray,
        camera_id: Optional[int],
        entity_type: str,
        entity_name: str,
        recognition_status: str = "NOT_APPLICABLE",
        person_id: Optional[int] = None,
        event_type: str = "DETECTION",
        direction: str = "NONE",
        confidence: float = 0.0,
        severity: str = "INFO",
        zone_name: Optional[str] = None,
        camera_name: str = "Main Entrance",
        metadata: Optional[dict] = None,
        is_misbehaving: bool = False,
        force_snapshot: bool = False
    ) -> Optional[Event]:
        """
        Evaluates event cooldown, captures high-quality camera snapshot,
        persists Event and Notification to DB, and broadcasts real-time telemetry.
        When an unknown person is recognized and misbehaving, a snapshot is captured by default.
        """
        identifier = person_id if person_id else entity_name
        effective_event_type = event_type if event_type not in ["DETECTION", "NONE"] else (direction if direction in ["ENTRY", "EXIT"] else "DETECTION")

        # Cooldown evaluation:
        # If an unknown person is misbehaving or force_snapshot is requested,
        # prioritize capturing the snapshot by default and enforce a dedicated misbehavior cooldown
        if is_misbehaving or force_snapshot:
            misbehavior_key = (entity_type, str(identifier), f"MISBEHAVIOR_{effective_event_type}")
            now = time.time()
            with self.lock:
                last_time = self.cooldown_tracker.get(misbehavior_key, 0.0)
                if (now - last_time) < 10.0:
                    return None
                self.cooldown_tracker[misbehavior_key] = now
        else:
            # Check standard cooldown
            if not self.should_record_event(entity_type, identifier, effective_event_type):
                return None

        # Determine snapshot prefix according to requirement
        is_alert_event = is_misbehaving or ("UNAUTHORIZED" in effective_event_type) or ("RESTRICTED" in effective_event_type) or ("SUSPICIOUS" in effective_event_type) or ("LOITERING" in effective_event_type)
        if is_misbehaving or "UNAUTHORIZED" in effective_event_type:
            prefix = "UNAUTHORIZED_PERSON"
        elif "RESTRICTED" in effective_event_type:
            prefix = "RESTRICTED_ZONE_BREACH"
        elif "LOITERING" in effective_event_type:
            prefix = "LOITERING_UNKNOWN_PERSON" if recognition_status == "UNKNOWN" else "LOITERING_PERSON"
        elif "SUSPICIOUS" in effective_event_type:
            prefix = "SUSPICIOUS_UNKNOWN_PERSON" if recognition_status == "UNKNOWN" else "SUSPICIOUS_ACTIVITY"
        elif recognition_status == "KNOWN":
            prefix = f"KNOWN_{entity_type}"
        else:
            prefix = f"{entity_type}_{effective_event_type}"

        # Capture and save fresh snapshot directly from camera frame at exact moment
        snapshot_rel_path = ""
        if frame is not None and frame.size > 0:
            try:
                alert_reason = metadata.get("reason") if metadata else None
                snapshot_rel_path = storage_service.save_snapshot(
                    frame=frame,
                    prefix=prefix,
                    camera_name=camera_name,
                    annotate_meta=True,
                    is_alert=is_alert_event,
                    alert_text=alert_reason
                )
            except Exception as e:
                print(f"[EventService] Error saving snapshot: {e}")

        try:
            new_event = Event(
                camera_id=camera_id,
                person_id=person_id,
                entity_type=entity_type,
                entity_name=entity_name,
                recognition_status=recognition_status,
                event_type=effective_event_type,
                direction=direction,
                confidence=float(confidence),
                snapshot_path=snapshot_rel_path,
                severity=severity.upper() if severity else ("CRITICAL" if is_misbehaving else "INFO"),
                zone_name=zone_name or "Premises",
                is_acknowledged=False,
                timestamp=datetime.utcnow(),
                metadata_json=json.dumps(metadata) if metadata else None
            )
            db.session.add(new_event)
            db.session.commit()

            # Trigger real-time notification & broadcast
            self._handle_event_notification(new_event, camera_name)
            return new_event

        except Exception as e:
            db.session.rollback()
            print(f"[EventService] Database error saving event: {e}")
            return None

    def _handle_event_notification(self, event: Event, camera_name: str = "Camera #1"):
        """
        Dispatches alerts with proper severity and category.
        """
        cam_name = event.camera.name if event.camera else camera_name
        time_str = event.timestamp.strftime("%H:%M:%S")

        sev = event.severity.upper() if event.severity else "INFO"
        category = "SYSTEM"

        # Determine title, message, category, and notification severity
        if "UNAUTHORIZED" in event.event_type:
            category = "UNAUTHORIZED"
            notif_sev = "critical"
            title = f"🚨 UNAUTHORIZED ENTRY DETECTED"
            msg = f"{event.entity_name} entered {event.zone_name or cam_name} without authorization at {time_str}"
        elif "RESTRICTED" in event.event_type:
            category = "UNAUTHORIZED"
            notif_sev = "critical"
            title = f"🛑 RESTRICTED ZONE VIOLATION"
            msg = f"{event.entity_name} breached restricted perimeter in {event.zone_name or cam_name} at {time_str}"
        elif "LOITERING" in event.event_type:
            category = "SUSPICIOUS"
            notif_sev = "critical" if sev in ["CRITICAL", "HIGH"] else "warning"
            title = f"⚠️ LOITERING DETECTED"
            msg = f"Unknown person loitering in {event.zone_name or cam_name} at {time_str}"
        elif "SUSPICIOUS" in event.event_type:
            category = "SUSPICIOUS"
            notif_sev = "critical" if sev in ["CRITICAL", "HIGH"] else "warning"
            title = f"⚠️ SUSPICIOUS ACTIVITY OBSERVED"
            msg = f"Observable anomaly: {event.entity_name} in {event.zone_name or cam_name} at {time_str}"
        elif event.recognition_status == "KNOWN":
            category = "KNOWN"
            notif_sev = "info"
            title = f"👤 {event.entity_name} - {event.direction}"
            msg = f"Verified identity: {event.entity_name} ({event.direction}) at {cam_name} ({time_str})"
        elif event.entity_type == "VEHICLE":
            category = "ALL"
            notif_sev = "warning" if sev in ["HIGH", "CRITICAL"] else "info"
            title = f"🚗 Vehicle Activity ({event.entity_name.capitalize()})"
            msg = f"{event.entity_name.capitalize()} observed at {cam_name} ({time_str})"
        elif event.entity_type == "ANIMAL":
            category = "ALL"
            notif_sev = "info"
            title = f"🐾 Animal Alert ({event.entity_name.capitalize()})"
            msg = f"{event.entity_name.capitalize()} detected within premises boundary at {time_str}"
        else:
            category = "ALL"
            notif_sev = "info"
            title = f"🔍 Security Detection: {event.entity_name}"
            msg = f"{event.entity_type} event recorded at {cam_name} ({time_str})"

        notification_service.create_notification(
            title=title,
            message=msg,
            severity=notif_sev,
            event_id=event.id,
            category=category
        )

event_service = EventService()
