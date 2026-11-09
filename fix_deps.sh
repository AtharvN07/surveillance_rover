#!/bin/bash
# fix_deps.sh — Install all dependencies into the Python that is actually used
# Run once from ~/surveillance_rover/ : bash fix_deps.sh

set -e

echo "=== Detecting Python ==="
# Prefer python3.8 which is the JetPack 4.6 default
PYTHON=$(which python3.8 2>/dev/null || which python3)
echo "Python binary : $PYTHON"
echo "Python version: $($PYTHON --version)"
echo "Site-packages : $($PYTHON -c 'import site; print(site.getsitepackages())')"

echo ""
echo "=== Installing pip into this Python ==="
$PYTHON -m ensurepip --upgrade 2>/dev/null || true
$PYTHON -m pip install --upgrade pip --user 2>/dev/null || true

echo ""
echo "=== Installing dependencies ==="
$PYTHON -m pip install \
    "fastapi==0.115.0" \
    "uvicorn[standard]==0.30.6" \
    "websockets==12.0" \
    "python-multipart==0.0.9" \
    "pydantic==2.9.2" \
    "pyserial==3.5" \
    "psutil==6.0.0" \
    "anyio==4.5.2" \
    "httpx==0.27.2" \
    "numpy==1.24.4" \
    --user

echo ""
echo "=== Verifying ==="
$PYTHON -c "import fastapi; print('fastapi', fastapi.__version__)"
$PYTHON -c "import uvicorn; print('uvicorn', uvicorn.__version__)"
$PYTHON -c "import numpy; print('numpy', numpy.__version__)"
$PYTHON -c "import cv2; print('cv2', cv2.__version__)" 2>/dev/null || echo "cv2 not installed (install separately or use system opencv)"

echo ""
echo "=== Done. Now run: ==="
echo "  bash start.sh"
