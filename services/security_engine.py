import time
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from config import Config
from models import SystemSetting, RestrictedZone, Person

class SecurityEngine:
    """
    Rule-Based Premises Security & Threat Classification Engine.
    Evaluates observable physical events against configured security policies:
    - Unauthorized entry detection (unknown persons, vehicles, boundary crossings)
    - After-hours access control (e.g. 22:00 - 06:00)
    - Restricted zone spatial violations (polygons & bounding boxes)
    - Loitering / prolonged dwell-time detection
    - Repeated entry/exit & loitering attempts
    - Erratic / anomalous movement detection (pacing, restless prowling)
    """

    def __init__(self):
        # Cache for recent appearances: identifier -> list of timestamps
        self.appearance_history: Dict[str, List[float]] = {}

    def get_loitering_threshold(self) -> int:
        try:
            return int(SystemSetting.get("LOITERING_THRESHOLD", Config.LOITERING_THRESHOLD))
        except Exception:
            return Config.LOITERING_THRESHOLD

    def get_repeated_threshold(self) -> int:
        try:
            return int(SystemSetting.get("REPEATED_EVENT_THRESHOLD", Config.REPEATED_EVENT_THRESHOLD))
        except Exception:
            return Config.REPEATED_EVENT_THRESHOLD

    def get_after_hours(self) -> Tuple[str, str]:
        start = SystemSetting.get("AFTER_HOURS_START", Config.AFTER_HOURS_START)
        end = SystemSetting.get("AFTER_HOURS_END", Config.AFTER_HOURS_END)
        return start, end

    def is_after_hours(self, check_dt: datetime = None) -> bool:
        if check_dt is None:
            check_dt = datetime.now()
        cur_str = check_dt.strftime("%H:%M")
        start, end = self.get_after_hours()
        if start <= end:
            return start <= cur_str <= end
        else: # e.g. 22:00 to 06:00
            return cur_str >= start or cur_str <= end

    def record_appearance(self, identifier: str) -> int:
        """Records an entity appearance and returns count within past 15 minutes"""
        now = time.time()
        cutoff = now - 900 # 15 minutes window
        if identifier not in self.appearance_history:
            self.appearance_history[identifier] = []
        # Filter old
        self.appearance_history[identifier] = [t for t in self.appearance_history[identifier] if t > cutoff]
        self.appearance_history[identifier].append(now)
        return len(self.appearance_history[identifier])

    def detect_erratic_motion(self, trajectory: List[Tuple[int, int]]) -> Tuple[bool, str]:
        """
        Analyzes 2D centroid trajectory for anomalous movement:
        - Frequent back-and-forth direction reversals (pacing / casing perimeter)
        - High total path length vs minimal net displacement (circling / lurking)
        """
        if not trajectory or len(trajectory) < 8:
            return False, ""

        pts = list(trajectory)
        dxs = [pts[i][0] - pts[i-1][0] for i in range(1, len(pts))]
        dys = [pts[i][1] - pts[i-1][1] for i in range(1, len(pts))]

        # Direction reversals along horizontal axis
        x_reversals = 0
        for i in range(1, len(dxs)):
            if (dxs[i] > 3 and dxs[i-1] < -3) or (dxs[i] < -3 and dxs[i-1] > 3):
                x_reversals += 1

        # Direction reversals along vertical axis
        y_reversals = 0
        for i in range(1, len(dys)):
            if (dys[i] > 3 and dys[i-1] < -3) or (dys[i] < -3 and dys[i-1] > 3):
                y_reversals += 1

        if x_reversals >= 3 or y_reversals >= 3:
            return True, "Erratic pacing & direction reversals"

        # Check total path length vs net displacement
        total_dist = sum(math.hypot(dxs[i], dys[i]) for i in range(len(dxs)))
        net_disp = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])

        if total_dist > 160 and net_disp < 40:
            return True, "Restless perimeter circling / lurking"

        return False, ""

    def evaluate_track(
        self,
        track: dict,
        camera_id: int,
        zones: List[RestrictedZone],
        frame_shape: Tuple[int, int] = (480, 640)
    ) -> dict:
        """
        Evaluates track state against security rules and misbehavior criteria.
        Returns evaluation dict:
        {
            "is_unauthorized": bool,
            "is_suspicious": bool,
            "is_misbehaving": bool,
            "force_snapshot": bool,
            "event_type": str,
            "severity": str ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"),
            "reason": str,
            "zone_name": str,
            "should_alert": bool
        }
        """
        now_dt = datetime.now()
        after_hours = self.is_after_hours(now_dt)
        entity_type = track.get("entity_type", "OTHER")
        rec_status = track.get("recognition_status", "NOT_APPLICABLE")
        person_name = track.get("person_name")
        person_id = track.get("person_id")
        direction = track.get("direction", "NONE")
        dwell_time = track.get("dwell_time", 0.0)
        obj_id = track.get("object_id", "?")
        centroid = track.get("centroid", (0, 0))
        trajectory = track.get("trajectory", [])
        h, w = frame_shape[:2]

        norm_x = centroid[0] / max(1, w)
        norm_y = centroid[1] / max(1, h)

        loitering_limit = self.get_loitering_threshold()
        repeated_limit = self.get_repeated_threshold()

        is_unknown_person = (entity_type == "PERSON" and rec_status == "UNKNOWN")

        # Track appearances count
        identifier = f"{entity_type}_{person_id if person_id else (person_name or obj_id)}"
        if rec_status == "UNKNOWN":
            identifier = f"UNKNOWN_{obj_id}"
        appearances = self.record_appearance(identifier)

        # 1. Check Restricted Zones (Zero-Tolerance Spatial Violation)
        violated_zone = None
        for zone in zones:
            if not zone.enabled:
                continue
            if zone.contains_point(norm_x, norm_y):
                # Check authorization
                is_authorized = False
                if rec_status == "KNOWN" and person_id:
                    auth_ids = zone.get_authorized_persons()
                    if person_id in auth_ids:
                        is_authorized = True
                
                # Check allowed hours for the zone
                if not zone.is_time_allowed(now_dt):
                    is_authorized = False

                if not is_authorized:
                    violated_zone = zone
                    break

        if violated_zone:
            alert_sev = violated_zone.alert_level.upper() if violated_zone.alert_level else "HIGH"
            if after_hours or is_unknown_person:
                alert_sev = "CRITICAL"
            reason_text = f"Unknown individual breached restricted zone '{violated_zone.name}'" if is_unknown_person else f"Restricted zone breach in '{violated_zone.name}'"
            return {
                "is_unauthorized": True,
                "is_suspicious": True,
                "is_misbehaving": True,
                "force_snapshot": True,
                "event_type": "RESTRICTED_ZONE_VIOLATION",
                "severity": alert_sev,
                "reason": reason_text,
                "zone_name": violated_zone.name,
                "should_alert": True
            }

        # 2. Loitering Detection (Prolonged dwell time beyond security threshold)
        if dwell_time >= loitering_limit and not track.get("loitering_flagged", False):
            track["loitering_flagged"] = True
            is_unauth = is_unknown_person
            sev = "CRITICAL" if (after_hours and is_unauth) else ("HIGH" if (is_unauth or after_hours) else "MEDIUM")
            reason_prefix = "After-hours unknown individual" if (after_hours and is_unauth) else ("Unknown individual" if is_unauth else "Subject")
            return {
                "is_unauthorized": is_unauth,
                "is_suspicious": True,
                "is_misbehaving": is_unknown_person,
                "force_snapshot": is_unknown_person,
                "event_type": "LOITERING_DETECTED",
                "severity": sev,
                "reason": f"{reason_prefix} loitering detected (Dwell duration: {int(dwell_time)}s exceeds {loitering_limit}s threshold)",
                "zone_name": "Monitored Perimeter",
                "should_alert": True
            }

        # 3. Erratic Motion / Anomalous Pacing Misbehavior
        if is_unknown_person:
            is_erratic, erratic_reason = self.detect_erratic_motion(trajectory)
            if is_erratic and not track.get("erratic_flagged", False):
                track["erratic_flagged"] = True
                return {
                    "is_unauthorized": True,
                    "is_suspicious": True,
                    "is_misbehaving": True,
                    "force_snapshot": True,
                    "event_type": "SUSPICIOUS_ACTIVITY",
                    "severity": "CRITICAL" if after_hours else "HIGH",
                    "reason": f"Unknown individual anomalous behavior: {erratic_reason}" + (" (During restricted hours)" if after_hours else ""),
                    "zone_name": "Monitored Perimeter",
                    "should_alert": True
                }

        # 4. Repeated Appearances / Suspicious Proximity
        if appearances >= repeated_limit and is_unknown_person and not track.get("repeated_flagged", False):
            track["repeated_flagged"] = True
            return {
                "is_unauthorized": True,
                "is_suspicious": True,
                "is_misbehaving": True,
                "force_snapshot": True,
                "event_type": "SUSPICIOUS_ACTIVITY",
                "severity": "CRITICAL" if after_hours else "HIGH",
                "reason": f"Repeated unauthorized prowling ({appearances} appearances in 15 mins)" + (" (During restricted hours)" if after_hours else ""),
                "zone_name": "Perimeter Boundary",
                "should_alert": True
            }

        # 5. Unauthorized Entry (Unknown person crossing boundary tripwire)
        if direction == "ENTRY" and is_unknown_person:
            return {
                "is_unauthorized": True,
                "is_suspicious": True,
                "is_misbehaving": True,
                "force_snapshot": True,
                "event_type": "UNAUTHORIZED_ENTRY",
                "severity": "CRITICAL" if after_hours else "HIGH",
                "reason": "Unenrolled / unknown individual crossed entry perimeter without authorization" + (" (After hours)" if after_hours else ""),
                "zone_name": "Monitored Entrance",
                "should_alert": True
            }

        # 6. After-Hours Unauthorized Intrusion
        if after_hours:
            if is_unknown_person:
                return {
                    "is_unauthorized": True,
                    "is_suspicious": True,
                    "is_misbehaving": True,
                    "force_snapshot": True,
                    "event_type": "AFTER_HOURS_UNAUTHORIZED_ENTRY" if direction == "ENTRY" else "AFTER_HOURS_TRESPASS",
                    "severity": "CRITICAL",
                    "reason": f"Unknown person detected on premises during restricted hours ({now_dt.strftime('%H:%M:%S')})",
                    "zone_name": "Main Perimeter",
                    "should_alert": True
                }
            elif entity_type == "VEHICLE":
                return {
                    "is_unauthorized": True,
                    "is_suspicious": True,
                    "is_misbehaving": True,
                    "force_snapshot": True,
                    "event_type": "AFTER_HOURS_UNAUTHORIZED_ENTRY",
                    "severity": "CRITICAL",
                    "reason": f"Unscheduled vehicle entry during restricted hours ({now_dt.strftime('%H:%M:%S')})",
                    "zone_name": "Gate Perimeter",
                    "should_alert": True
                }
            elif entity_type == "PERSON" and rec_status == "KNOWN" and direction == "ENTRY":
                return {
                    "is_unauthorized": False,
                    "is_suspicious": True,
                    "is_misbehaving": False,
                    "force_snapshot": False,
                    "event_type": "AFTER_HOURS_ENTRY",
                    "severity": "MEDIUM",
                    "reason": f"Known individual '{person_name}' accessed premises after hours",
                    "zone_name": "Premises Entrance",
                    "should_alert": True
                }

        # 7. Standard Entry / Exit for known persons or other entities
        if direction == "ENTRY":
            return {
                "is_unauthorized": False,
                "is_suspicious": False,
                "is_misbehaving": False,
                "force_snapshot": False,
                "event_type": "ENTRY",
                "severity": "INFO",
                "reason": f"Authorized entry for {person_name or entity_type}",
                "zone_name": "Entrance",
                "should_alert": False
            }
        elif direction == "EXIT":
            return {
                "is_unauthorized": False,
                "is_suspicious": False,
                "is_misbehaving": False,
                "force_snapshot": False,
                "event_type": "EXIT",
                "severity": "INFO",
                "reason": f"Exit observed for {person_name or entity_type}",
                "zone_name": "Exit",
                "should_alert": False
            }

        # Default Neutral Presence
        default_sev = "MEDIUM" if is_unknown_person else "INFO"
        return {
            "is_unauthorized": False,
            "is_suspicious": False,
            "is_misbehaving": False,
            "force_snapshot": False,
            "event_type": "DETECTION",
            "severity": default_sev,
            "reason": f"{entity_type} presence detected",
            "zone_name": "Premises Field",
            "should_alert": False
        }

security_engine = SecurityEngine()
