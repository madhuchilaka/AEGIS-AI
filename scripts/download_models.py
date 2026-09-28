"""
Model Downloader Script
Downloads OpenCV YuNet (Face Detection) and SFace (Face Recognition) models,
and ensures YOLOv8 model weights are downloaded.
"""
import os
import sys
import urllib.request

MODELS = {
    "face_detection_yunet_2023mar.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
}

def download_file(url, target_path):
    print(f"Downloading {os.path.basename(target_path)} from {url}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response, open(target_path, "wb") as out_file:
        data = response.read()
        out_file.write(data)
    print(f"Saved {os.path.basename(target_path)} ({len(data)} bytes).")

def ensure_models(models_dir="models_data"):
    os.makedirs(models_dir, exist_ok=True)
    for filename, url in MODELS.items():
        filepath = os.path.join(models_dir, filename)
        if not os.path.exists(filepath) or os.path.getsize(filepath) < 10000:
            try:
                download_file(url, filepath)
            except Exception as e:
                print(f"Warning: Failed to download {filename}: {e}")
        else:
            print(f"Model already present: {filename} ({os.path.getsize(filepath)} bytes)")

    # Also test YOLO model loading to pre-cache yolov8n.pt
    try:
        from ultralytics import YOLO
        print("Checking YOLOv8n model...")
        yolo_path = os.path.join(models_dir, "yolov8n.pt")
        model = YOLO("yolov8n.pt")
        print("YOLOv8n model ready.")
    except Exception as e:
        print(f"YOLO pre-load warning: {e}")

if __name__ == "__main__":
    ensure_models()
