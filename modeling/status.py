"""Read-only, dependency-free status display for the server job."""

import argparse
import json
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument(
    "--run",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "runs/task3-20260925-v1",
)
args = parser.parse_args()
path = args.run / "status.json"
if not path.exists():
    raise SystemExit("No supervisor status yet")
print(json.dumps(json.loads(path.read_text()), indent=2))
for p in sorted((args.run / "models").glob("*/status.json")):
    status = json.loads(p.read_text())
    age = int(time.time() - status["updated_at"])
    print(
        f"{p.parent.name}: {status['state']}; epoch={status.get('epoch', status.get('selected_epoch', '-'))}; updated {age}s ago"
    )
print("Saved results:", args.run / "results")
