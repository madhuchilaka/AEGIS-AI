import base64
import cv2
import numpy as np
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from models import db, Person, FaceEmbedding, Event
from routes import login_required, admin_required
from services.face_recognition_service import face_recognition_service
from services.storage_service import storage_service

people_bp = Blueprint("people", __name__)

@people_bp.route("/people")
@login_required
def index():
    persons = Person.query.order_by(Person.created_at.desc()).all()
    return render_template("people.html", persons=persons)

@people_bp.route("/face-enrollment")
@login_required
def face_enrollment():
    person_id = request.args.get("person_id")
    selected_person = None
    if person_id:
        selected_person = Person.query.get(person_id)
    persons = Person.query.filter_by(status="active").all()
    return render_template("face_enrollment.html", selected_person=selected_person, persons=persons)

# --- REST APIs ---

@people_bp.route("/api/people", methods=["GET"])
@login_required
def list_people():
    persons = Person.query.order_by(Person.created_at.desc()).all()
    return jsonify([p.to_dict() for p in persons])

@people_bp.route("/api/people", methods=["POST"])
@login_required
@admin_required
def create_person():
    data = request.get_json() or request.form
    name = data.get("name", "").strip()
    person_code = data.get("person_code", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    notes = data.get("notes", "").strip()

    if not name:
        return jsonify({"status": "error", "message": "Person name is required"}), 400

    # Check unique person_code if provided
    if person_code:
        existing = Person.query.filter_by(person_code=person_code).first()
        if existing:
            return jsonify({"status": "error", "message": f"Person code '{person_code}' already exists"}), 400

    person = Person(
        name=name,
        person_code=person_code or None,
        email=email or None,
        phone=phone or None,
        notes=notes or None,
        status="active"
    )
    db.session.add(person)
    db.session.commit()

    return jsonify({"status": "success", "message": "Person created successfully", "person": person.to_dict()})

@people_bp.route("/api/people/<int:id>", methods=["GET"])
@login_required
def get_person(id):
    person = Person.query.get_or_404(id)
    recent_events = [e.to_dict() for e in person.events.order_by(Event.timestamp.desc()).limit(15).all()]
    embeddings = [emb.to_dict() for emb in person.embeddings.all()]
    data = person.to_dict()
    data["recent_events"] = recent_events
    data["samples"] = embeddings
    return jsonify({"status": "success", "person": data})

@people_bp.route("/api/people/<int:id>", methods=["PUT"])
@login_required
@admin_required
def update_person(id):
    person = Person.query.get_or_404(id)
    data = request.get_json() or {}

    if "name" in data and data["name"].strip():
        person.name = data["name"].strip()
    if "person_code" in data:
        code = data["person_code"].strip()
        if code and code != person.person_code:
            existing = Person.query.filter_by(person_code=code).first()
            if existing:
                return jsonify({"status": "error", "message": f"Code '{code}' already taken"}), 400
        person.person_code = code or None
    if "email" in data:
        person.email = data["email"].strip() or None
    if "phone" in data:
        person.phone = data["phone"].strip() or None
    if "status" in data:
        person.status = data["status"]
    if "notes" in data:
        person.notes = data["notes"]

    db.session.commit()
    face_recognition_service.train_database()
    return jsonify({"status": "success", "message": "Person updated successfully", "person": person.to_dict()})

@people_bp.route("/api/people/<int:id>", methods=["DELETE"])
@login_required
@admin_required
def delete_person(id):
    person = Person.query.get_or_404(id)
    # Remove all face sample files from disk
    for emb in person.embeddings:
        if emb.sample_image_path:
            storage_service.delete_file(emb.sample_image_path)

    db.session.delete(person)
    db.session.commit()

    # Re-train face recognition memory cache
    face_recognition_service.train_database()
    return jsonify({"status": "success", "message": f"Person '{person.name}' and all face records deleted."})

@people_bp.route("/api/people/<int:id>/toggle-status", methods=["POST"])
@login_required
@admin_required
def toggle_status(id):
    person = Person.query.get_or_404(id)
    person.status = "inactive" if person.status == "active" else "active"
    db.session.commit()
    face_recognition_service.train_database()
    return jsonify({"status": "success", "new_status": person.status})

@people_bp.route("/api/face/enroll", methods=["POST"])
@login_required
@admin_required
def enroll_face():
    """
    Accepts face image via multipart file upload OR base64 data URL.
    Detects face, validates quality, extracts embedding, saves sample crop and vector.
    """
    person_id = request.form.get("person_id")
    if not person_id:
        # Check JSON payload
        json_data = request.get_json(silent=True) or {}
        person_id = json_data.get("person_id")

    if not person_id:
        return jsonify({"status": "error", "message": "person_id is required"}), 400

    person = Person.query.get(person_id)
    if not person:
        return jsonify({"status": "error", "message": "Person not found"}), 404

    frame = None

    # Option A: file upload
    if "image" in request.files:
        file = request.files["image"]
        if file.filename != "":
            img_bytes = file.read()
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Option B: base64 data string (from webcam snapshot canvas)
    if frame is None:
        json_data = request.get_json(silent=True) or request.form
        image_data = json_data.get("image_base64")
        if image_data:
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            try:
                img_bytes = base64.b64decode(image_data)
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Base64 decode failed: {e}"}), 400

    if frame is None or frame.size == 0:
        return jsonify({"status": "error", "message": "No valid image data provided"}), 400

    # 1. Detect faces
    faces = face_recognition_service.detect_faces(frame, score_threshold=0.5)
    if not faces:
        return jsonify({"status": "error", "message": "No face detected in image. Please center your face with good lighting."}), 422

    if len(faces) > 1:
        return jsonify({"status": "error", "message": f"Multiple faces ({len(faces)}) detected. Please ensure only one person is in frame."}), 422

    best_face = faces[0]

    # 2. Validate quality
    is_valid, reason, quality = face_recognition_service.validate_face_quality(frame, best_face)
    if not is_valid:
        return jsonify({"status": "error", "message": f"Image quality check failed: {reason}"}), 422

    # 3. Save face sample crop to disk
    x, y, w, h = best_face[0:4].astype(int)
    img_h, img_w = frame.shape[:2]
    # Add a little margin
    pad_x, pad_y = int(w * 0.2), int(h * 0.2)
    x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
    x2, y2 = min(img_w, x + w + pad_x), min(img_h, y + h + pad_y)
    face_crop = frame[y1:y2, x1:x2]

    try:
        sample_path = storage_service.save_face_sample(face_crop if face_crop.size > 0 else frame, person.id)
    except Exception as e:
        sample_path = None

    # 4. Enroll face sample into DB & memory cache
    success, msg, emb_id = face_recognition_service.enroll_person_sample(person.id, frame, best_face, sample_path)
    if not success:
        return jsonify({"status": "error", "message": msg}), 500

    return jsonify({
        "status": "success",
        "message": "Face sample enrolled successfully!",
        "embedding_id": emb_id,
        "sample_image": sample_path,
        "quality_score": quality,
        "total_samples": person.embeddings.count()
    })

@people_bp.route("/api/face/train", methods=["POST"])
@login_required
@admin_required
def train_faces():
    """Re-trains/reloads recognition database into memory"""
    face_recognition_service.train_database()
    return jsonify({
        "status": "success",
        "message": "Face recognition database updated successfully.",
        "enrolled_count": len(face_recognition_service.known_faces_cache)
    })

@people_bp.route("/api/face/delete-sample/<int:embedding_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_sample(embedding_id):
    emb = FaceEmbedding.query.get_or_404(embedding_id)
    if emb.sample_image_path:
        storage_service.delete_file(emb.sample_image_path)
    person_id = emb.person_id
    db.session.delete(emb)
    db.session.commit()
    face_recognition_service.train_database()
    return jsonify({"status": "success", "message": "Face sample deleted"})
