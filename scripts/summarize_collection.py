"""Produce a compact, shareable inventory from actual generated artifacts."""

import csv
import hashlib
import json
from pathlib import Path

root = Path.cwd()
manifest = json.loads((root / "data/manifests/designs.json").read_text())
rows = []
for design in manifest["designs"]:
    for representation in ("sog", "aig", "aimg", "xag"):
        directory = root / "data/processed" / design["id"] / representation
        row = {
            "design": design["id"],
            "family": design["family"],
            "category": design["category"],
            "representation": representation,
            "status": "not_completed",
        }
        if (directory / "summary.json").exists():
            summary = json.loads((directory / "summary.json").read_text())
            row.update(
                {
                    key: summary[key]
                    for key in (
                        "register_bits",
                        "combinational_operators",
                        "max_combinational_depth",
                        "timed_endpoints",
                        "path_rows",
                        "valid_sampled_paths",
                        "rejected_sampled_candidates",
                    )
                }
            )
            row["status"] = "features_generated"
            proof = directory / "equivalence.json"
            row["equivalence"] = (
                json.loads(proof.read_text())["status"] if proof.exists() else "not_run"
            )
            row["endpoint_table_sha256"] = hashlib.sha256(
                (directory / "endpoint_features.parquet").read_bytes()
            ).hexdigest()
            row["path_table_sha256"] = hashlib.sha256(
                (directory / "path_features.parquet").read_bytes()
            ).hexdigest()
        rows.append(row)
output = root / "docs/results"
output.mkdir(parents=True, exist_ok=True)
fields = list(dict.fromkeys(k for r in rows for k in r))
with (output / "task1_inventory.csv").open("w") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
complete = [
    d["id"]
    for d in manifest["designs"]
    if all(r["status"] == "features_generated" for r in rows if r["design"] == d["id"])
]
summary = {
    "candidate_designs": len(manifest["designs"]),
    "families": len({d["family"] for d in manifest["designs"]}),
    "designs_with_four_representations": complete,
    "completed_representation_runs": sum(
        r["status"] == "features_generated" for r in rows
    ),
    "formally_proven_runs": sum(r.get("equivalence") == "passed" for r in rows),
    "unproven_runs": sum(r.get("equivalence") == "unproven" for r in rows),
    "proofs_not_run": sum(r.get("equivalence") == "not_run" for r in rows),
    "prediction_target": "arrival_time",
    "target_labels_generated": any((root / "data/labels").glob("*/summary.json")),
    "label_designs_available": sorted(
        p.parent.name for p in (root / "data/labels").glob("*/summary.json")
    ),
}
(output / "task1_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
