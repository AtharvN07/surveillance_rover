# Mac Server — Rover Processing Node

Heavy inference runs here. Jetson handles camera + motors only.

## Start

```bash
pip3 install -r requirements.txt
python3 run.py --jetson 192.168.31.122
```

Dashboard: http://localhost:9000

## YOLO models

| Model | File | Speed | Accuracy |
|-------|------|-------|----------|
| nano | yolo11n.pt | fastest | good |
| small | yolo11s.pt | medium | better |
| medium | yolo11m.pt | slower | best |

The first run auto-downloads the model (~6 MB for nano).

## Optional: VLM scene understanding

Set in environment:
```bash
export OPENAI_API_KEY=sk-...
```

Then the scan map endpoint will include natural-language descriptions of what the rover sees.
