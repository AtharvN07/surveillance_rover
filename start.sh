#!/bin/bash
# start.sh — Launch the rover server using the correct Python that has the packages
# Run from: ~/surveillance_rover/

# Find the python3 that actually has uvicorn installed
PYTHON=""
for candidate in \
    "$HOME/.local/bin/python3.8" \
    "$HOME/.local/bin/python3" \
    "/usr/bin/python3.8" \
    "/usr/local/bin/python3.8" \
    "/usr/bin/python3"; do
    if $candidate -c "import uvicorn" 2>/dev/null; then
        PYTHON=$candidate
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "uvicorn not found in any Python. Running fix_deps.sh first..."
    bash fix_deps.sh
    PYTHON=$(which python3.8 || which python3)
fi

echo "Using Python: $PYTHON"
$PYTHON --version

# Load env if present
if [ -f config/rover.env ]; then
    set -a; source config/rover.env; set +a
fi

exec $PYTHON -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
