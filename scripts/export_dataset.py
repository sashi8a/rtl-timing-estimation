"""Release one row per register bit only after independent artifact validation."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from validate_artifacts import validate

from rtl_timing.graph import is_register
from rtl_timing.labels import match_aliases, parse_direct_arrivals, parse_label_report
from rtl_timing.libraries import library_variant
from rtl_timing.provenance import digest, input_signature, reusable

REPS = ("sog", "aig", "aimg", "xag")


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def eligible_groups(joined):
    """A target bit needs exactly one eligible match in every representation."""
    return {
        cell: group
        for cell, group in joined.groupby("target_cell")
        if len(group) == len(REPS)
        and set(group.representation) == set(REPS)
        and group.training_eligible.all()
        and (group.mapping_status == "matched").all()
    }


def validate_design(root, design):
    design_id = design["id"]
    label_dir = root / "data/labels" / design_id
    summary = read(label_dir / "summary.json")
    require(
        reusable(label_dir, input_signature(root, design_id, "labels")),
        "Missing, stale, or damaged label provenance",
    )
    require(summary["units"] == {"time": "ns", "capacitance": "fF"}, "Wrong units")
    require("time 1ns" in (label_dir / "timing.log").read_text(), "STA unit mismatch")
    sdc_hash = digest(root / "data/raw" / design_id / Path(design["sdc"]).name)
    require(summary["sdc_sha256"] == sdc_hash, "Stale label constraints")
    require(
        summary["netlist_sha256"] == digest(label_dir / "netlist.json"),
        "Wrong target netlist",
    )
    require(
        summary["library_sha256"] == digest(label_dir / "target.lib"),
        "Wrong target library",
    )
    labels = pd.read_parquet(label_dir / "labels.parquet")
    joined = pd.read_parquet(label_dir / "feature_label_join.parquet")
    require(
        labels.target_cell.is_unique and labels.target_endpoint_id.is_unique,
        "Duplicate target identity",
    )
    require(labels.target_endpoint_id.notna().all(), "Missing target RTL identity")
    require(
        not joined.duplicated(["representation", "endpoint_id"]).any(),
        "Duplicate feature identity",
    )
    require(set(joined.representation) == set(REPS), "Missing feature view")
    endpoints = read(label_dir / "endpoints.json")
    require(
        len(endpoints) == len(labels) == summary["register_bits"],
        "Target coverage mismatch",
    )
    cells = read(label_dir / "netlist.json")["modules"][design["top"]]["cells"]
    require(
        set(labels.target_cell)
        == {name for name, cell in cells.items() if is_register(cell)},
        "Target register inventory is incomplete",
    )
    for i, (endpoint, row) in enumerate(
        zip(endpoints, labels.itertuples(), strict=True)
    ):
        require(endpoint["cell"] == row.target_cell, "Target endpoint order mismatch")
        require(
            endpoint["endpoint_id"] == row.target_endpoint_id,
            "Target RTL identity mismatch",
        )
        paths = {
            edge: parse_label_report(
                label_dir / f"path_{i}_{edge}.rpt", row.target_cell, cells
            )
            for edge in ("rise", "fall")
        }
        direct = parse_direct_arrivals((label_dir / f"arrival_{i}.rpt").read_text())
        valid = []
        for edge, path in paths.items():
            stored = getattr(row, f"{edge}_arrival_ns")
            if path is None:
                require(pd.isna(stored), "Untimed edge has a numeric label")
                require(
                    direct[edge] is None,
                    "Direct query has an arrival absent from path report",
                )
            else:
                require(direct[edge] is not None, "Missing direct arrival")
                require(
                    np.isclose(path["arrival_ns"], direct[edge], atol=1e-7, rtol=0),
                    "Direct/path arrival disagreement",
                )
                require(
                    np.isclose(stored, path["arrival_ns"], atol=1e-7, rtol=0),
                    "Stored edge label mismatch",
                )
                valid.append(path["arrival_ns"])
        require((row.label_status == "timed") == bool(valid), "Timing status mismatch")
        if valid:
            require(
                np.isfinite(row.arrival_ns)
                and np.isclose(row.arrival_ns, max(valid), atol=1e-7, rtol=0),
                "Wrong maximum arrival",
            )
            require(row.direct_arrival_crosscheck, "Missing arrival cross-check flag")
        else:
            require(pd.isna(row.arrival_ns), "Untimed bit has a numeric label")

    proofs = {"target": read(label_dir / "equivalence.json")["status"]}
    features = {}
    canonical_ids = None
    for rep in REPS:
        directory = root / "data/processed" / design_id / rep
        require(
            reusable(directory, input_signature(root, design_id, "features", rep)),
            f"Stale/damaged {rep} feature provenance",
        )
        validate(directory)
        feature_summary = read(directory / "summary.json")
        require(
            feature_summary.get("library_variant") == library_variant(root),
            "Mixed library variants",
        )
        require(
            feature_summary.get("sdc_sha256") == sdc_hash,
            "Feature/label constraint mismatch",
        )
        proofs[rep] = read(directory / "equivalence.json")["status"]
        features[rep] = pd.read_parquet(directory / "endpoint_features.parquet")
        ids = set(features[rep].endpoint_id)
        require(
            canonical_ids is None or ids == canonical_ids,
            "Cross-view endpoint identities differ",
        )
        canonical_ids = ids
        actual = joined[joined.representation == rep].set_index("endpoint_cell")
        expected = match_aliases(features[rep], labels).set_index("endpoint_cell")
        require(set(actual.index) == set(expected.index), "Incomplete feature join")
        actual = actual.loc[expected.index]
        require(
            (actual.endpoint_id == expected.endpoint_id).all(),
            "Join RTL identity differs",
        )
        require(
            (actual.mapping_status == expected.mapping_status).all(),
            "Join mapping differs from unique aliases",
        )
        matched = actual[actual.mapping_status == "matched"]
        require(matched.target_cell.is_unique, "Many-to-one target match")
        for cell, match in matched.iterrows():
            target = labels.loc[int(expected.loc[cell, "target_index"])]
            require(
                match.target_cell == target.target_cell, "Join maps to wrong target"
            )
            require(
                match.label_status == target.label_status, "Join timing status differs"
            )
            require(
                np.isclose(
                    match.arrival_ns,
                    target.arrival_ns,
                    atol=1e-7,
                    rtol=0,
                    equal_nan=True,
                ),
                "Join label differs",
            )

    functional_gate = all(status == "passed" for status in proofs.values())
    expected_eligible = (
        functional_gate
        & (joined.mapping_status == "matched")
        & (joined.label_status == "timed")
    )
    require(
        (joined.training_eligible == expected_eligible).all(),
        "Eligibility violates proof/mapping policy",
    )
    rows = []
    for cell, group in eligible_groups(joined).items():
        target = labels[labels.target_cell == cell].iloc[0]
        refs = {}
        for match in group.itertuples():
            directory = root / "data/processed" / design_id / match.representation
            refs[match.representation] = {
                "endpoint_id": match.endpoint_id,
                "endpoint_cell": match.endpoint_cell,
                **{
                    name: str((directory / f"{name}.parquet").relative_to(root))
                    for name in (
                        "endpoint_features",
                        "path_features",
                        "design_features",
                    )
                },
                "provenance": str((directory / "provenance.json").relative_to(root)),
                "provenance_sha256": digest(directory / "provenance.json"),
            }
        rows.append(
            {
                "design_id": design_id,
                "family": design["family"],
                "target_cell": cell,
                "target_endpoint_id": target.target_endpoint_id,
                "arrival_ns": target.arrival_ns,
                "rise_arrival_ns": target.rise_arrival_ns,
                "fall_arrival_ns": target.fall_arrival_ns,
                "startpoint_type": target.startpoint_type,
                "training_eligible": True,
                "library_variant": library_variant(root),
                "sdc_sha256": sdc_hash,
                "feature_views_json": json.dumps(refs, sort_keys=True),
                "labels": str((label_dir / "labels.parquet").relative_to(root)),
                "label_provenance": str(
                    (label_dir / "provenance.json").relative_to(root)
                ),
                "label_provenance_sha256": digest(label_dir / "provenance.json"),
            }
        )
    mapping = {
        rep: {
            status: int(
                (
                    (joined.representation == rep) & (joined.mapping_status == status)
                ).sum()
            )
            for status in ("matched", "unmatched", "ambiguous")
        }
        for rep in REPS
    }
    inventory = {
        "design_id": design_id,
        "family": design["family"],
        "status": "validated" if functional_gate else "excluded_proof",
        "proofs": proofs,
        "target_register_bits": len(labels),
        "feature_register_bits": len(canonical_ids),
        "timed_register_bits": int((labels.label_status == "timed").sum()),
        "untimed_register_bits": int((labels.label_status != "timed").sum()),
        "unmatched_target_register_bits": len(
            set(labels.target_cell) - set(joined.target_cell.dropna())
        ),
        "feature_mapping": mapping,
        "unmatched_target_register_bits_by_rep": {
            rep: len(
                set(labels.target_cell)
                - set(joined.loc[joined.representation == rep, "target_cell"].dropna())
            )
            for rep in REPS
        },
        "eligible_register_bits": len(rows),
        "excluded_register_bits": len(labels) - len(rows),
        "exclusion_reasons": [
            f"{rep} proof {status}"
            for rep, status in proofs.items()
            if status != "passed"
        ],
        "validation": "passed; identities, hashes, constraints, units, rise/fall paths, direct queries, increment sums, joins, proofs",
    }
    if len(rows) < len(labels) and functional_gate:
        inventory["exclusion_reasons"].append(
            "Some target bits lack four unique timed feature matches"
        )
    return rows, inventory


def export(root):
    designs = read(root / "data/manifests/designs.json")["designs"]
    rows, inventory = [], []
    for design in designs:
        try:
            released, info = validate_design(root, design)
            rows.extend(released)
        except (OSError, ValueError, KeyError, AssertionError) as error:
            info = {
                "design_id": design["id"],
                "family": design["family"],
                "status": "failed_validation",
                "eligible_register_bits": 0,
                "exclusion_reasons": [str(error) or type(error).__name__],
            }
        inventory.append(info)
        print(json.dumps(info), flush=True)
    output = root / "data/releases/task2"
    output.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if len(frame):
        require(
            not frame.duplicated(["design_id", "target_endpoint_id"]).any(),
            "Duplicate released register bit",
        )
        require(np.isfinite(frame.arrival_ns).all(), "Nonfinite released label")
    frame.to_parquet(output / "registers.parquet", index=False)
    families = sorted({d["family"] for d in designs})
    report = {
        "library_variant": library_variant(root),
        "label": "max(rise, fall) D-pin arrival, ns, post-synthesis without wire parasitics",
        "requested_designs": len(designs),
        "validated_designs": sum(d["status"] == "validated" for d in inventory),
        "eligible_designs": len({r["design_id"] for r in rows}),
        "eligible_families": len({r["family"] for r in rows}),
        "unique_eligible_register_bits": len(rows),
        "registers_sha256": digest(output / "registers.parquet"),
        "families": {
            family: {
                "designs": [d["id"] for d in designs if d["family"] == family],
                "eligible_designs": len(
                    {r["design_id"] for r in rows if r["family"] == family}
                ),
                "eligible_register_bits": sum(r["family"] == family for r in rows),
            }
            for family in families
        },
        "designs": inventory,
        "collection_runs": [
            str(p.relative_to(root))
            for p in sorted((root / "data/collection_runs").glob("*.json"))
        ],
        "recorded_collection_failures": [
            {"run": str(path.relative_to(root)), **record}
            for path in sorted((root / "data/collection_runs").glob("labels-*.json"))
            for record in read(path)["records"]
            if record["status"] in {"failed", "timeout"}
        ],
    }
    for path in (output / "manifest.json", root / "docs/results/task2_collection.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
    pd.DataFrame(
        [
            {k: v for k, v in d.items() if not isinstance(v, (dict, list))}
            for d in inventory
        ]
    ).to_csv(root / "docs/results/task2_inventory.csv", index=False)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = export(args.root.resolve())
    print(f"Released {result['unique_eligible_register_bits']} unique register bits")
