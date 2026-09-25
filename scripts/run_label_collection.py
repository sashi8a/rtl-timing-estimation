"""Generate/resume the retained dataset with bounded workers and a wall-clock deadline."""

import argparse
import json
import sys
from pathlib import Path

from rtl_timing.collection import run_collection

parser = argparse.ArgumentParser()
parser.add_argument("--designs", nargs="+")
parser.add_argument("--workers", type=int, default=4)
parser.add_argument("--deadline-minutes", type=float, default=40)
parser.add_argument("--no-resume", action="store_true")
args = parser.parse_args()
result = run_collection(
    Path.cwd(), args.designs, args.workers, args.deadline_minutes, not args.no_resume
)
print(json.dumps(result, indent=2))
if any(row["status"] in {"failed", "timeout"} for row in result["records"]):
    sys.exit(1)
