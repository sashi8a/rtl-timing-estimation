"""Run original Task 2 validation read-only, using the original environment."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from common import digest, require, write_json
from export_dataset import validate_design

if __name__ == "__main__":
    release = pd.read_parquet(ROOT / "data/releases/task2/registers.parquet")
    designs = json.loads((ROOT / "data/manifests/designs.json").read_text())["designs"]
    reports = []
    for design in designs:
        if design["id"] not in set(release.design_id):
            continue
        rows, report = validate_design(ROOT, design)
        actual = (
            release[release.design_id == design["id"]]
            .sort_values("target_endpoint_id")
            .reset_index(drop=True)
        )
        expected = (
            pd.DataFrame(rows).sort_values("target_endpoint_id").reset_index(drop=True)
        )
        pd.testing.assert_frame_equal(
            actual, expected[actual.columns], check_dtype=False
        )
        require(report["status"] == "validated", f"Failed validation: {design['id']}")
        reports.append(report)
        print(design["id"], "validated without rewriting artifacts", flush=True)
    require(len(reports) == 19, "Incomplete Task 2 preflight")
    write_json(
        Path(sys.argv[1]) / "task2_preflight.json",
        {
            "release_sha256": digest(ROOT / "data/releases/task2/registers.parquet"),
            "designs": reports,
        },
    )
