"""Validate every representation and report cross-representation endpoint coverage."""

import json
import sys
import traceback
from pathlib import Path

import pandas as pd
from validate_artifacts import validate

root = Path.cwd()
manifest = json.loads((root / "data/manifests/designs.json").read_text())
results = []
for design in manifest["designs"]:
    identities = {}
    for representation in ("sog", "aig", "aimg", "xag"):
        directory = root / "data/processed" / design["id"] / representation
        row = {
            "design": design["id"],
            "representation": representation,
            "status": "passed",
        }
        try:
            validate(directory)
        except Exception:  # noqa: BLE001 -- report all artifact failures together
            row["status"] = "failed"
            row["error"] = traceback.format_exc()[-2000:]
        else:
            endpoints = pd.read_parquet(directory / "endpoint_features.parquet")
            identities[representation] = set(endpoints.endpoint_id)
            row.update(
                endpoint_rows=len(endpoints),
                timed_endpoints=int((endpoints.timing_status == "timed").sum()),
            )
        results.append(row)
    same = len(identities) == 4 and all(
        v == next(iter(identities.values())) for v in identities.values()
    )
    for row in results[-4:]:
        row["same_endpoint_ids_across_representations"] = same
    print(
        design["id"],
        "checked",
        "same endpoints" if same else "endpoint mismatch",
        flush=True,
    )
output = root / "docs/results/task1_validation.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(results, indent=2) + "\n")
if any(
    r["status"] != "passed" or not r["same_endpoint_ids_across_representations"]
    for r in results
):
    sys.exit(1)
