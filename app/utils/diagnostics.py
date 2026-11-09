"""
diagnostics.py — Lightweight system diagnostics helpers.
"""
import subprocess
import platform


def get_system_info() -> dict:
    info = {
        "platform": platform.platform(),
        "python":   platform.python_version(),
    }
    try:
        result = subprocess.run(
            ["tegrastats", "--interval", "1000", "--count", "1"],
            capture_output=True, text=True, timeout=3
        )
        info["tegrastats"] = result.stdout.strip()
    except FileNotFoundError:
        info["tegrastats"] = "not available"
    return info
