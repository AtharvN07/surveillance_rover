"""
run.py — Entry point for the Mac processing server.
Pulls MJPEG from Jetson -> YOLO inference -> dashboard.
"""

import asyncio
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Rover Mac Server")
    parser.add_argument("--jetson", default="192.168.31.122", help="Jetson IP")
    parser.add_argument("--port", type=int, default=9000, help="Mac server port")
    parser.add_argument("--model", default="yolo11n.pt", help="YOLO model")
    args = parser.parse_args()

    import os
    os.environ["JETSON_IP"] = args.jetson
    os.environ["YOLO_MODEL"] = args.model
    os.environ["PORT"] = str(args.port)

    # Now import and run the app
    import uvicorn
    from server import app
    print(f"\n  Rover Mac Server")
    print(f"  Dashboard : http://localhost:{args.port}")
    print(f"  Jetson    : {args.jetson}:8000")
    print(f"  YOLO      : {args.model}\n")
    uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()
