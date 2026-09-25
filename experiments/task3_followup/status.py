"""Dependency-free remote progress command."""

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument(
    "--run",
    type=Path,
    default=Path(__file__).resolve().parents[2] / "runs/task3-followup-20260925-v1",
)
args = parser.parse_args()
print((args.run / "status.json").read_text())
for directory in sorted((args.run / "models").glob("*")):
    if (directory / "complete.json").exists():
        print(directory.name, "complete")
    elif (directory / "status.json").exists():
        s = json.loads((directory / "status.json").read_text())
        print(directory.name, s["state"], "epoch", s.get("epoch", "-"))
print("Results:", args.run / "results")
