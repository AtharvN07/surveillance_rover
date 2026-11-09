#!/bin/bash
# install_py38.sh — install uvicorn + fastapi directly into python3.8
# bypassing the PyPI aarch64 wheel version cap

set -e
PY=/usr/local/bin/python3.8

echo "=== Upgrading pip for python3.8 ==="
$PY -m pip install --upgrade pip --user

echo "=== Installing core deps ==="
$PY -m pip install \
    "h11==0.14.0" \
    "click==8.0.4" \
    "typing_extensions==4.1.1" \
    --user --no-deps

echo "=== Installing uvicorn from GitHub (no wheel needed) ==="
$PY -m pip install \
    "https://github.com/encode/uvicorn/archive/refs/tags/0.20.0.tar.gz" \
    --user --no-deps

echo "=== Installing starlette ==="
$PY -m pip install "starlette==0.20.4" --user --no-deps

echo "=== Installing fastapi ==="
$PY -m pip install "fastapi==0.89.1" --user --no-deps

echo "=== Installing remaining deps ==="
$PY -m pip install \
    "anyio==3.6.2" \
    "sniffio==1.2.0" \
    "idna==3.4" \
    "pydantic==1.10.13" \
    "python-multipart==0.0.5" \
    "websockets==10.4" \
    --user

echo "=== Verify ==="
$PY -c "import uvicorn; print('uvicorn', uvicorn.__version__)"
$PY -c "import fastapi; print('fastapi', fastapi.__version__)"
