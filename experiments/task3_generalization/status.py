"""Read-only compact progress; no fitting or mutation."""

import argparse
import json
from pathlib import Path


def status(run):
    run = Path(run)

    def read(p):
        return json.loads(p.read_text())

    states = [read(p) for p in sorted((run / "models").glob("fold*/*/status.json"))]
    return {
        "supervisor": read(run / "status.json")
        if (run / "status.json").exists()
        else None,
        "completed_runs": sum(s["state"] == "complete" for s in states),
        "required_runs": 40,
        "neural_epochs": sum(s.get("epoch") or 0 for s in states),
        "required_neural_epochs": 7200,
        "active": [s for s in states if s["state"] != "complete"],
        "failure_records": len(list((run / "failures").glob("*.json"))),
        "sealed_results": (run / "results/complete.json").exists(),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path)
    a = p.parse_args()
    print(json.dumps(status(a.run), indent=2))
