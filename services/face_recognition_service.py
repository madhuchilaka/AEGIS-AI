import os
import threading
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from config import Config
from models import db, Person, FaceEmbedding

class FaceRecognitionService:
    def __init__(self):
        self.models_dir = Path(Config.MODELS_DIR)
        self.yunet_path = self.models_dir / "face_detection_yunet_2023mar.onnx"
        self.sface_path = self.models_dir / "face_recognition_sface_2021dec.onnx"

        self.detector = None
        self.recognizer = None
        self.lock = threading.Lock()

        # Cache of known faces: person_id -> {"name": str, "code": str, "vectors": [np.ndarray]}
        self.known_faces_cache: Dict[int, dict] = {}
        self.is_initialized = False

        self._init_models()

    def _init_models(self):
        """Initializes OpenCV YuNet and SFace models if present"""
        with self.lock:
            try:
                if self.yunet_path.exists() and self.sface_path.exists():
                    self.detector = cv2.FaceDetectorYN.create(
                        str(self.yunet_path),
                        "",
                        (320, 320),
                        score_threshold=0.6,
                        nms_threshold=0.3,
                        top_k=5000
                    )
                    self.recognizer = cv2.FaceRecognizerSF.create(str(self.sface_path), "")
                    self.is_initialized = True
                    print("[FaceRecognitionService] YuNet and SFace models loaded successfully.")
                else:
                    print(f"[FaceRecognitionService] Warning: ONNX model files missing in {self.models_dir}.")
                    self.is_initialized = False
            except Exception as e:
                print(f"[FaceRecognitionService] Error initializing models: {e}")
                self.is_initialized = False

    def load_known_faces(self, app=None):
        """
        Loads all active persons and their face embeddings from the database into the in-memory cache.
        """
        def _load():
            with self.lock:
                self.known_faces_cache.clear()
                try:
                    active_persons = Person.query.filter_by(status="active").all()
                    loaded_count = 0
                    for person in active_persons:
                        vectors = []
                        for emb_record in person.embeddings:
                            vec = emb_record.get_vector()
                            if vec.size > 0:
                                # Ensure shape is (1, 128)
                                if vec.ndim == 1:
                                    vec = vec.reshape(1, -1)
                                vectors.append(vec)
                        
                        if vectors:
                            self.known_faces_cache[person.id] = {
                                "id": person.id,
                                "name": person.name,
                                "person_code": person.person_code or "N/A",
                                "vectors": vectors
                            }
                            loaded_count += len(vectors)
                    print(f"[FaceRecognitionService] Loaded {len(self.known_faces_cache)} persons with {loaded_count} face embeddings into cache.")
                except Exception as e:
                    print(f"[FaceRecognitionService] Error loading known faces from DB: {e}")

        if app:
            with app.app_context():
                _load()
        else:
            _load()

    def train_database(self, app=None):
        """Re-trains/reloads the in-memory database of face embeddings"""
        self.load_known_faces(app)

    def detect_faces(self, frame: np.ndarray, score_threshold: float = 0.6) -> List[np.ndarray]:
        """
        Detects faces in frame using YuNet.
        Returns list of raw face arrays [x, y, w, h, x_re, y_re, ... score]
        """
        if not self.is_initialized or self.detector is None or frame is None:
            return []

        h, w = frame.shape[:2]
        with self.lock:
            try:
                self.detector.setInputSize((w, h))
                self.detector.setScoreThreshold(score_threshold)
                _, faces = self.detector.detect(frame)
                if faces is not None and len(faces) > 0:
                    return list(faces)
            except Exception as e:
                print(f"[FaceRecognitionService] Error in detect_faces: {e}")
        return []

    def validate_face_quality(self, frame: np.ndarray, face_info: np.ndarray) -> Tuple[bool, str, float]:
        """
        Validates quality of detected face:
        - Minimum dimensions
        - Blur (Laplacian variance)
        - Brightness
        Returns (is_valid, reason, quality_score)
        """
        x, y, w, h = face_info[0:4].astype(int)
        img_h, img_w = frame.shape[:2]

        # Bound coordinates
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(img_w, x + w)
        y2 = min(img_h, y + h)

        if w < 50 or h < 50:
            return False, f"Face too small ({w}x{h}). Minimum size is 50x50 pixels.", 0.2

        face_crop = frame[y1:y2, x1:x2]
        if face_crop.size == 0:
            return False, "Invalid face crop boundaries.", 0.0

        # Gray scale for blur & brightness
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        
        # Brightness test
        brightness = np.mean(gray)
        if brightness < 35:
            return False, "Lighting is too dark. Please ensure sufficient front lighting.", 0.3
        if brightness > 235:
            return False, "Lighting is overexposed. Reduce direct glare.", 0.3

        # Blur test using Laplacian variance
        blur_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur_var < 40.0:
            return False, "Face image is blurry. Please hold steady.", 0.4

        quality_score = min(1.0, round((blur_var / 300.0) * 0.5 + 0.5, 2))
        return True, "Quality passed", quality_score

    def generate_embedding(self, frame: np.ndarray, face_info: np.ndarray) -> Optional[np.ndarray]:
        """
        Aligns face and extracts 128-d feature embedding vector using SFace.
        """
        if not self.is_initialized or self.recognizer is None:
            return None

        with self.lock:
            try:
                aligned_face = self.recognizer.alignCrop(frame, face_info)
                embedding = self.recognizer.feature(aligned_face)
                # Ensure 2D (1, 128)
                if embedding.ndim == 1:
                    embedding = embedding.reshape(1, -1)
                return embedding.astype(np.float32)
            except Exception as e:
                print(f"[FaceRecognitionService] Error extracting feature: {e}")
                return None

    def compare_embedding(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Computes Cosine Similarity between two face embeddings.
        Returns float between 0.0 and 1.0.
        """
        if emb1 is None or emb2 is None:
            return 0.0

        with self.lock:
            try:
                # SFace match cosine metric returns similarity
                score = self.recognizer.match(emb1, emb2, cv2.FaceRecognizerSF_FR_COSINE)
                return float(max(0.0, min(1.0, score)))
            except Exception:
                # Manual cosine similarity fallback
                u = emb1.flatten()
                v = emb2.flatten()
                norm_u = np.linalg.norm(u)
                norm_v = np.linalg.norm(v)
                if norm_u == 0 or norm_v == 0:
                    return 0.0
                return float(np.dot(u, v) / (norm_u * norm_v))

    def recognize_face(self, frame: np.ndarray, face_info: np.ndarray, threshold: float = None) -> Tuple[Optional[int], str, float, str]:
        """
        Recognizes a face against the cached database of enrolled people.
        Returns: (person_id, person_name, confidence, status: 'KNOWN'|'UNKNOWN')
        """
        if threshold is None:
            threshold = Config.FACE_RECOGNITION_THRESHOLD

        embedding = self.generate_embedding(frame, face_info)
        if embedding is None:
            return None, "Unknown Person", 0.0, "UNKNOWN"

        best_person_id = None
        best_name = "Unknown Person"
        best_score = 0.0

        with self.lock:
            for pid, person_data in self.known_faces_cache.items():
                for sample_vector in person_data["vectors"]:
                    score = self.compare_embedding(embedding, sample_vector)
                    if score > best_score:
                        best_score = score
                        best_person_id = pid
                        best_name = person_data["name"]

        if best_score >= threshold and best_person_id is not None:
            return best_person_id, best_name, best_score, "KNOWN"
        else:
            return None, "Unknown Person", best_score, "UNKNOWN"

    def enroll_person_sample(self, person_id: int, frame: np.ndarray, face_info: np.ndarray, sample_image_rel_path: str = None) -> Tuple[bool, str, Optional[int]]:
        """
        Enrolls a single verified face sample for person_id:
        Extracts embedding, saves record to FaceEmbedding DB, updates memory cache.
        """
        embedding = self.generate_embedding(frame, face_info)
        if embedding is None:
            return False, "Failed to generate facial feature embedding.", None

        is_valid, reason, quality = self.validate_face_quality(frame, face_info)
        if not is_valid:
            return False, f"Quality check failed: {reason}", None

        try:
            emb_record = FaceEmbedding(
                person_id=person_id,
                embedding_json="",
                sample_image_path=sample_image_rel_path,
                quality_score=quality
            )
            emb_record.set_vector(embedding)
            db.session.add(emb_record)
            db.session.commit()

            # Update cache
            with self.lock:
                person = Person.query.get(person_id)
                if person:
                    if person_id not in self.known_faces_cache:
                        self.known_faces_cache[person_id] = {
                            "id": person_id,
                            "name": person.name,
                            "person_code": person.person_code or "N/A",
                            "vectors": []
                        }
                    self.known_faces_cache[person_id]["vectors"].append(embedding)

            return True, "Face enrolled successfully.", emb_record.id
        except Exception as e:
            db.session.rollback()
            return False, f"Database error during enrollment: {e}", None

# Global singleton
face_recognition_service = FaceRecognitionService()
