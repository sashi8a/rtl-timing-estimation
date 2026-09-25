"""Validate pilot artifacts and create a reviewable set of raw-path examples."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from rtl_timing.labels import parse_direct_arrivals, parse_label_report, sha256

root = Path.cwd()
manifest = json.loads((root / "data/manifests/designs.json").read_text())
results, examples = [], []
for design in ("gcd", "timer32"):
    out = root / "data/labels" / design
    summary = json.loads((out / "summary.json").read_text())
    labels = pd.read_parquet(out / "labels.parquet")
    joins = pd.read_parquet(out / "feature_label_join.parquet")
    top = next(d["top"] for d in manifest["designs"] if d["id"] == design)
    cells = json.loads((out / "netlist.json").read_text())["modules"][top]["cells"]
    assert labels.target_cell.is_unique and labels.target_endpoint_id.is_unique
    assert labels.target_endpoint_id.notna().all()
    assert labels.direct_arrival_crosscheck.all()
    assert np.isfinite(labels.arrival_ns).all()
    assert np.allclose(
        labels.arrival_ns,
        labels[["rise_arrival_ns", "fall_arrival_ns"]].max(axis=1),
        atol=1e-7,
        rtol=0,
    )
    assert len(joins) == 4 * len(labels)
    assert (joins.mapping_status == "matched").all()
    assert not joins.duplicated(["representation", "endpoint_id"]).any()
    assert not joins.duplicated(["representation", "target_cell"]).any()
    for _, row in labels.iterrows():
        parsed = parse_label_report(root / row.report_path, row.target_cell, cells)
        direct = parse_direct_arrivals((root / row.direct_report_path).read_text())
        assert np.isclose(parsed["arrival_ns"], max(direct.values()), atol=1e-7, rtol=0)
    ordered = labels.sort_values(["arrival_ns", "target_endpoint_id"])
    for position in (0, len(ordered) // 2, len(ordered) - 1):
        row = ordered.iloc[position]
        example = {
            k: row[k]
            for k in (
                "design_id",
                "target_cell",
                "target_endpoint_id",
                "startpoint",
                "startpoint_type",
                "rise_arrival_ns",
                "fall_arrival_ns",
                "critical_edge",
                "arrival_ns",
                "increment_sum_ns",
                "report_path",
                "direct_report_path",
            )
        }
        text = (root / row.report_path).read_text()
        data_lines = text.split("data arrival time")[0].splitlines()
        example["raw_report_header"] = "\n".join(text.splitlines()[:6])
        example["raw_report_tail"] = "\n".join(data_lines[-7:]) + " data arrival time"
        examples.append(example)
    results.append(
        {
            "design": design,
            "label_bits": len(labels),
            "matched_feature_rows": len(joins),
            "training_eligible_register_bits": joins.loc[
                joins.training_eligible, "target_cell"
            ].nunique(),
            "target_proof": summary["target_proof"]["status"],
            "feature_proofs": summary["feature_proofs"],
            "arrival_min_ns": float(labels.arrival_ns.min()),
            "arrival_max_ns": float(labels.arrival_ns.max()),
            "cell_counts": pd.Series(
                [c["type"] for c in cells.values() if c["type"] != "$scopeinfo"]
            )
            .value_counts()
            .to_dict(),
            "direct_arrival_checks": len(labels),
            "labels_sha256": sha256(out / "labels.parquet"),
            "join_sha256": sha256(out / "feature_label_join.parquet"),
            "sdc_sha256": summary["sdc_sha256"],
            "library_sha256": summary["library_sha256"],
        }
    )
output = root / "docs/results"
(output / "task2_pilot.json").write_text(
    json.dumps({"results": results, "examples": examples}, indent=2) + "\n"
)
lines = [
    "# Task 2 pilot: inspect six matched register bits",
    "",
    "These are low-, middle-, and high-arrival examples from each design. All pilot labels were also checked against direct pin arrivals and the sum of the reported path increments. Times are ns. Matching uses RTL aliases, not timing values.",
    "",
    "| Design | Register bit | Source kind | Rise | Fall | Selected |",
    "| --- | --- | --- | ---: | ---: | ---: |",
]
for e in examples:
    lines.append(
        f"| {e['design_id']} | `{e['target_endpoint_id']}` | {e['startpoint_type']} | {e['rise_arrival_ns']:.9f} | {e['fall_arrival_ns']:.9f} | {e['arrival_ns']:.9f} |"
    )
for e in examples:
    lines.extend(
        [
            "",
            f"## {e['design_id']}: {e['target_endpoint_id']}",
            "",
            f"Mapped D pin: `{e['target_cell']}/D`. Winning transition: {e['critical_edge']}. Sum of path increments: {e['increment_sum_ns']:.9f} ns. Full report: `{e['report_path']}`.",
            "",
            "```text",
            e["raw_report_header"],
            "...",
            e["raw_report_tail"],
            "```",
        ]
    )
(output / "task2_pilot_review.md").write_text("\n".join(lines) + "\n")
print(json.dumps(results, indent=2))
