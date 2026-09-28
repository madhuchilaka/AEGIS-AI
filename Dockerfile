# Production Dockerfile for Intelligent Premises Monitoring & Security System
# Optimized for Render.com deployment with CPU-accelerated OpenCV & PyTorch

FROM python:3.11-slim

# Set environment flags
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system libraries required by OpenCV and NumPy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pre-install PyTorch CPU build to avoid downloading gigabytes of CUDA packages
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code, assets, and pretrained models
COPY . .

# Ensure directories for storage and database exist
RUN mkdir -p /app/storage/snapshots /app/storage/face_data /app/instance /app/models_data

# Expose web service port
EXPOSE 5000

# Run with Gunicorn using Render configuration
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]
