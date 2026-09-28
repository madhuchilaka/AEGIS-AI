#!/usr/bin/env bash
# Render Build Script for Native Python Environment
set -o errexit

echo ">>> [Render Build] Upgrading pip..."
pip install --upgrade pip

echo ">>> [Render Build] Installing PyTorch CPU build..."
pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

echo ">>> [Render Build] Installing application requirements..."
pip install --no-cache-dir -r requirements.txt

echo ">>> [Render Build] Verifying database schema & tables..."
python -c "from app import create_app; from models import db; app = create_app(); app.app_context().push(); db.create_all()"

echo ">>> [Render Build] Build completed successfully!"
