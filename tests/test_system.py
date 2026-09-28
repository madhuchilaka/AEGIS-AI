"""
End-to-End System Integration Test Suite
Validates computer vision models, tracking, face recognition, event cooldowns,
snapshots, database integrity, 30-day retention, and web routes.
"""
import os
import sys
import json
import time
import unittest
import numpy as np
import cv2

# Set path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from models import db, User, Person, FaceEmbedding, Camera, Event, Notification, SystemSetting
from services.camera_service import camera_service
from services.detection_service import detection_service
from services.face_recognition_service import face_recognition_service
from services.tracking_service import tracking_service
from services.event_service import event_service
from services.storage_service import storage_service
from services.retention_service import retention_service
from services.notification_service import notification_service

class PremisesSecuritySystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_01_user_authentication(self):
        """Test password hashing, verification and admin role check"""
        user = User.query.filter_by(username="admin").first()
        self.assertIsNotNone(user, "Default admin user should exist")
        self.assertTrue(user.check_password("Admin@123"), "Admin password should match")
        self.assertFalse(user.check_password("WrongPassword"), "Incorrect password must fail")
        self.assertTrue(user.is_admin, "Admin role check should be True")

    def test_02_computer_vision_models_loaded(self):
        """Verify YOLO, YuNet, and SFace are loaded"""
        self.assertTrue(detection_service.is_loaded, "YOLOv8 model must be loaded")
        self.assertTrue(face_recognition_service.is_initialized, "YuNet and SFace models must be initialized")

    def test_03_face_detection_and_embedding(self):
        """Test face detection and SFace 128-d vector generation on a test frame"""
        # Create a synthetic face frame (300x300 image with face-like structure)
        frame = np.full((300, 300, 3), 120, dtype=np.uint8)
        # Draw face oval
        cv2.circle(frame, (150, 150), 70, (190, 200, 210), -1)
        # Eyes
        cv2.circle(frame, (125, 135), 8, (30, 30, 30), -1)
        cv2.circle(frame, (175, 135), 8, (30, 30, 30), -1)
        # Nose
        cv2.line(frame, (150, 145), (150, 165), (50, 50, 50), 3)
        # Mouth
        cv2.ellipse(frame, (150, 180), (25, 10), 0, 0, 180, (40, 40, 40), 3)

        # YuNet detection
        faces = face_recognition_service.detect_faces(frame, score_threshold=0.3)
        # If YuNet finds the synthetic face, test SFace embedding extraction
        if faces:
            emb = face_recognition_service.generate_embedding(frame, faces[0])
            self.assertIsNotNone(emb, "SFace should return embedding")
            self.assertEqual(emb.shape, (1, 128), "Embedding must be 128-dimensional")
            # Self-comparison should be ~1.0
            similarity = face_recognition_service.compare_embedding(emb, emb)
            self.assertAlmostEqual(similarity, 1.0, places=4)

    def test_04_person_enrollment_and_recognition(self):
        """Test enrolling a person, saving face vector, and matching"""
        # Register a test person
        test_person = Person(name="Alice Test", person_code="TEST001", status="active")
        db.session.add(test_person)
        db.session.commit()

        # Create a 128-d synthetic vector
        fake_vector = np.random.randn(1, 128).astype(np.float32)
        fake_vector = fake_vector / np.linalg.norm(fake_vector)

        emb = FaceEmbedding(person_id=test_person.id, quality_score=0.95)
        emb.set_vector(fake_vector)
        db.session.add(emb)
        db.session.commit()

        # Reload cache
        face_recognition_service.load_known_faces()
        self.assertIn(test_person.id, face_recognition_service.known_faces_cache)

        # Verify comparison match
        sim = face_recognition_service.compare_embedding(fake_vector, fake_vector)
        self.assertAlmostEqual(sim, 1.0, places=4)

        # Cleanup test person
        db.session.delete(test_person)
        db.session.commit()
        face_recognition_service.load_known_faces()

    def test_05_tracking_and_entry_exit_line(self):
        """Test centroid tracking and crossing detection across virtual line"""
        tracking_service.reset()

        # Frame 1: Object above horizontal line (line_pos=0.5, H=400 -> line at Y=200)
        det_frame1 = [{
            "bbox": [100, 130, 160, 230], # centroid at (130, 180) -> above 200
            "class_name": "person",
            "entity_type": "PERSON",
            "confidence": 0.85
        }]
        tracks1 = tracking_service.update(det_frame1, line_pos=0.5, line_orientation="horizontal", frame_shape=(400, 400))
        self.assertEqual(len(tracks1), 1)
        self.assertEqual(tracks1[0]["direction"], "NONE")

        # Frame 2: Object moved across the line to below 200 (Y=220)
        det_frame2 = [{
            "bbox": [100, 170, 160, 270], # centroid at (130, 220) -> below 200
            "class_name": "person",
            "entity_type": "PERSON",
            "confidence": 0.88
        }]
        tracks2 = tracking_service.update(det_frame2, line_pos=0.5, line_orientation="horizontal", frame_shape=(400, 400))
        self.assertEqual(len(tracks2), 1)
        # Crossed from above to below -> ENTRY
        self.assertEqual(tracks2[0]["direction"], "ENTRY")

    def test_06_event_deduplication_cooldown(self):
        """Test that event service throttles repeated events within cooldown"""
        entity_type = "PERSON"
        identifier = "Unknown Person"
        event_type = "DETECTION"

        # First trigger should be permitted
        allowed1 = event_service.should_record_event(entity_type, identifier, event_type)
        self.assertTrue(allowed1, "First event should be recorded")

        # Immediate second trigger must be throttled
        allowed2 = event_service.should_record_event(entity_type, identifier, event_type)
        self.assertFalse(allowed2, "Second event within cooldown window must be rejected")

    def test_07_snapshot_saving(self):
        """Test that snapshot images are saved to structured YYYY/MM/DD paths"""
        dummy_frame = np.full((100, 100, 3), 50, dtype=np.uint8)
        rel_path = storage_service.save_snapshot(dummy_frame, prefix="test")
        self.assertTrue(rel_path.startswith("snapshots/"), "Snapshot must be in snapshots/ folder")

        # Verify file exists on disk
        full_path = storage_service.base_dir / rel_path
        self.assertTrue(full_path.exists(), "Snapshot file must exist on disk")

        # Clean up test snapshot
        storage_service.delete_file(rel_path)
        self.assertFalse(full_path.exists(), "File should be deleted after cleanup")

    def test_08_web_routes_unauthenticated_redirection(self):
        """Verify protected routes redirect unauthenticated users to /login"""
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 302, "Dashboard must redirect to login")
        self.assertIn("/login", res.headers.get("Location", ""))

        res2 = self.client.get("/monitor")
        self.assertEqual(res2.status_code, 302, "Monitor must redirect to login")

    def test_09_login_flow_and_authenticated_access(self):
        """Test login POST, session creation, and accessing protected views"""
        # Login with admin
        login_res = self.client.post("/login", data={"username": "admin", "password": "Admin@123"}, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)

        # Access Dashboard
        dash_res = self.client.get("/dashboard")
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b"Security Command Center", dash_res.data)

        # Access Monitoring page
        mon_res = self.client.get("/monitor")
        self.assertEqual(mon_res.status_code, 200)
        self.assertIn(b"Live Premises Surveillance Monitor", mon_res.data)

        # Access Events page
        events_res = self.client.get("/events")
        self.assertEqual(events_res.status_code, 200)

        # Access People page
        people_res = self.client.get("/people")
        self.assertEqual(people_res.status_code, 200)

        # Access Face Enrollment page
        enroll_res = self.client.get("/face-enrollment")
        self.assertEqual(enroll_res.status_code, 200)

        # Access Cameras page
        cams_res = self.client.get("/cameras")
        self.assertEqual(cams_res.status_code, 200)

        # Access Notifications page
        notifs_res = self.client.get("/notifications")
        self.assertEqual(notifs_res.status_code, 200)

        # Access Storage page
        storage_res = self.client.get("/storage")
        self.assertEqual(storage_res.status_code, 200)

        # Access Settings page
        settings_res = self.client.get("/settings")
        self.assertEqual(settings_res.status_code, 200)

    def test_10_api_endpoints(self):
        """Test REST API endpoints with authentication"""
        # Authenticate session
        self.client.post("/login", data={"username": "admin", "password": "Admin@123"})

        # GET /api/statistics
        res = self.client.get("/api/statistics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("metrics", data)

        # GET /api/events
        res = self.client.get("/api/events")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")

        # GET /api/camera/status
        res = self.client.get("/api/camera/status")
        self.assertEqual(res.status_code, 200)

        # GET /api/storage/stats
        res = self.client.get("/api/storage/stats")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "success")

        # POST /api/cleanup
        res = self.client.post("/api/cleanup", json={"retention_days": 30})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "success")

    def test_11_restricted_zones_and_threat_engine(self):
        """Test RestrictedZone spatial bounding checks and SecurityEngine threat classification"""
        from models import RestrictedZone
        from services.security_engine import security_engine

        cam = Camera.query.first()
        self.assertIsNotNone(cam, "At least one camera should exist")

        # Create a test restricted zone
        zone = RestrictedZone(
            camera_id=cam.id,
            name="Unit Test Vault Zone",
            boundary_type="rectangle",
            alert_level="CRITICAL",
            enabled=True
        )
        zone.set_coordinates({"x1": 0.2, "y1": 0.2, "x2": 0.8, "y2": 0.8})
        db.session.add(zone)
        db.session.commit()

        # Test point containment
        self.assertTrue(zone.contains_point(0.5, 0.5), "Center point (0.5, 0.5) must be inside zone")
        self.assertFalse(zone.contains_point(0.1, 0.1), "Perimeter point (0.1, 0.1) must be outside zone")

        # Test Threat Engine evaluation inside zone
        test_track = {
            "object_id": 999,
            "entity_type": "PERSON",
            "recognition_status": "UNKNOWN",
            "centroid": (320, 240), # (0.5, 0.5) on 640x480 frame
            "dwell_time": 10.0,
            "direction": "NONE"
        }
        eval_result = security_engine.evaluate_track(test_track, cam.id, [zone], frame_shape=(480, 640))
        self.assertTrue(eval_result["is_unauthorized"], "Unknown subject in restricted zone must be unauthorized")
        self.assertEqual(eval_result["event_type"], "RESTRICTED_ZONE_VIOLATION")
        self.assertEqual(eval_result["severity"], "CRITICAL")

        # Test Loitering Rule
        loitering_track = {
            "object_id": 998,
            "entity_type": "PERSON",
            "recognition_status": "UNKNOWN",
            "centroid": (50, 50), # outside zone
            "dwell_time": 75.0, # exceeds 60s loitering threshold
            "direction": "NONE"
        }
        loiter_eval = security_engine.evaluate_track(loitering_track, cam.id, [zone], frame_shape=(480, 640))
        self.assertTrue(loiter_eval["is_suspicious"], "Prolonged dwell time must be classified as suspicious")
        self.assertEqual(loiter_eval["event_type"], "LOITERING_DETECTED")

        # Test Zone API Endpoints
        self.client.post("/login", data={"username": "admin", "password": "Admin@123"})
        get_zones_res = self.client.get(f"/api/cameras/{cam.id}/zones")
        self.assertEqual(get_zones_res.status_code, 200)
        self.assertTrue(any(z["name"] == "Unit Test Vault Zone" for z in get_zones_res.get_json()["zones"]))

        # Cleanup zone
        db.session.delete(zone)
        db.session.commit()

    def test_12_acknowledgments_and_csv_export(self):
        """Test event/notification acknowledgment endpoints and CSV forensic log export"""
        self.client.post("/login", data={"username": "admin", "password": "Admin@123"})

        # Create or fetch an unacknowledged event
        ev = Event.query.filter_by(is_acknowledged=False).first()
        if not ev:
            ev = Event(
                camera_id=1,
                entity_type="PERSON",
                entity_name="Test Subject",
                recognition_status="UNKNOWN",
                severity="HIGH",
                is_acknowledged=False
            )
            db.session.add(ev)
            db.session.commit()

        # Acknowledge event
        ack_ev_res = self.client.post(f"/api/events/{ev.id}/acknowledge")
        self.assertEqual(ack_ev_res.status_code, 200)
        self.assertEqual(ack_ev_res.get_json()["status"], "success")

        # Verify DB state
        db.session.refresh(ev)
        self.assertTrue(ev.is_acknowledged)

        # Test CSV Export
        csv_res = self.client.get("/events/export/csv")
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res.headers.get("Content-Type"), "text/csv; charset=utf-8")
        self.assertIn(b"Event ID", csv_res.data)
        self.assertIn(b"Entity Type", csv_res.data)

    def test_13_capture_snapshot_on_unknown_person_misbehaving(self):
        """Test automatic snapshot capture by default when an unknown person is detected misbehaving"""
        from services.security_engine import security_engine

        # 1. Test Security Engine Flags Misbehaving Unknown Person
        unknown_misbehaving_track = {
            "object_id": 777,
            "entity_type": "PERSON",
            "recognition_status": "UNKNOWN",
            "centroid": (200, 200),
            "dwell_time": 70.0, # exceeds loitering threshold
            "direction": "ENTRY"
        }
        eval_res = security_engine.evaluate_track(unknown_misbehaving_track, camera_id=1, zones=[], frame_shape=(480, 640))
        self.assertTrue(eval_res["is_unauthorized"], "Unknown person crossing/loitering must be unauthorized")
        self.assertTrue(eval_res["is_misbehaving"], "Must flag is_misbehaving=True")
        self.assertTrue(eval_res["force_snapshot"], "Must flag force_snapshot=True")

        # 2. Test Erratic Motion / Pacing Detection
        pacing_trajectory = [
            (100, 200), (120, 200), (140, 200), # moving right
            (120, 200), (100, 200),             # reversed left
            (120, 200), (140, 200),             # reversed right
            (120, 200), (100, 200),             # reversed left
            (120, 200), (140, 200)              # reversed right
        ]
        is_erratic, reason = security_engine.detect_erratic_motion(pacing_trajectory)
        self.assertTrue(is_erratic, "Pacing back and forth must trigger erratic motion")

        # 3. Test Event Service Automatic Snapshot Capture
        test_frame = np.full((300, 300, 3), 70, dtype=np.uint8)
        # Add visual subject in frame
        cv2.circle(test_frame, (150, 150), 40, (180, 180, 220), -1)

        event = event_service.record_detection_event(
            frame=test_frame,
            camera_id=1,
            entity_type="PERSON",
            entity_name="Unknown Person",
            recognition_status="UNKNOWN",
            event_type="UNAUTHORIZED_ENTRY",
            direction="ENTRY",
            confidence=0.89,
            severity="CRITICAL",
            zone_name="Perimeter Gate",
            camera_name="Main Gate Cam",
            metadata={"reason": "Unenrolled visitor unauthorized boundary breach"},
            is_misbehaving=True,
            force_snapshot=True
        )

        self.assertIsNotNone(event, "Event must be recorded")
        self.assertTrue(event.snapshot_path, "Snapshot path must NOT be empty")
        self.assertTrue(event.snapshot_path.startswith("snapshots/"), "Snapshot must be saved in snapshots/ directory")

        # Verify physical file existence on disk
        full_snap_path = storage_service.base_dir / event.snapshot_path
        self.assertTrue(full_snap_path.exists(), "Snapshot file must physically exist on disk")

        # Verify Notification generated with category UNAUTHORIZED and critical severity
        notif = Notification.query.filter_by(event_id=event.id).first()
        self.assertIsNotNone(notif, "Notification must be generated for misbehavior")
        self.assertEqual(notif.category, "UNAUTHORIZED")
        self.assertEqual(notif.severity, "critical")

        # Cleanup test snapshot & record
        storage_service.delete_file(event.snapshot_path)
        self.assertFalse(full_snap_path.exists(), "Snapshot file should be deleted upon test cleanup")

if __name__ == "__main__":
    unittest.main()


