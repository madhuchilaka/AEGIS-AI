import os

# Render assigns a dynamic port via the PORT environment variable
port = os.environ.get("PORT", "5000")
bind = f"0.0.0.0:{port}"

# IMPORTANT: Exactly 1 worker process is required so that:
# 1. Background CameraService worker thread runs in a single shared process.
# 2. In-memory face embedding cache is shared across all incoming requests.
# 3. Model weights (YOLO, SFace, YuNet) are loaded only once in memory.
workers = 1

# Use multi-threaded gthread worker for concurrent requests, SSE feeds, and video streams
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# Timeout: 120 seconds to support long-polling SSE alerts and AI inference
timeout = 120
keepalive = 5

# Standard out logging for Render log aggregation
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

# Graceful worker shutdown timeout
graceful_timeout = 30
