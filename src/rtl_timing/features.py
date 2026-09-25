"""OpenSTA path parsing and named features (ns, fF).

Statistics adapt RTL-Timer timing_path.py's sum/mean/variance aggregation.
Unlike its report-specific indexing, operators are counted from mapped cells.
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .graph import OPERATORS, is_register


def statistics(values, prefix):
    if not values:
        return {f"{prefix}_{stat}": None for stat in ("sum", "mean", "variance", "std")}
    a = np.asarray(values, dtype=float)
    if not np.isfinite(a).all():
        raise ValueError(f"Nonfinite {prefix}")
    return {
        f"{prefix}_sum": float(a.sum()),
        f"{prefix}_mean": float(a.mean()),
        f"{prefix}_variance": float(a.var()),
        f"{prefix}_std": float(a.std()),
    }


def parse_path(path: Path, bog):
    text = path.read_text()
    if "Startpoint:" not in text:
        return None
    lines = text.splitlines()
    arrival = None
    pins, operators = [], []
    fanout, caps, slew = [], [], []
    for line in lines:
        if "data arrival time" in line:
            arrival = float(line.split()[0])
            break
        # Bounded numeric columns avoid expensive whitespace backtracking on headers.
        match = re.match(
            r"^\s*((?:[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\s+){3,5})"
            r"[\^v]\s+(\S+)\s+\(([^)]+)\)\s*$",
            line,
        )
        if not match:
            continue
        nums, pin, kind = match.groups()
        if kind in ("in", "out"):
            continue
        if "/" not in pin:
            continue
        instance, port = pin.rsplit("/", 1)
        cell = bog.cells.get(instance)
        if cell is None:
            raise ValueError(f"Path cell absent from graph: {instance}")
        values = [float(v) for v in nums.split()]
        if len(values) not in (3, 5):
            raise ValueError(f"Unexpected STA columns: {line}")
        pins.append(pin)
        output = cell["port_directions"].get(port) == "output"
        if output and not is_register(cell):
            operators.append(instance)
        # Output loads are counted once. Slew includes source Q and endpoint D,
        # excludes clock pins and duplicate combinational input observations.
        if output:
            if len(values) != 5:
                raise ValueError(f"Missing output fanout/capacitance: {line}")
            fanout.append(values[0])
            caps.append(values[1])
        if output or (is_register(cell) and port == "D"):
            slew.append(values[-3])
    if arrival is None or not np.isfinite(arrival):
        raise ValueError(f"Missing arrival in {path}")
    unique = list(dict.fromkeys(operators))
    startpoint = re.search(r"^Startpoint: (\S+)", text, re.MULTILINE).group(1)
    start_type = (
        "register"
        if startpoint in bog.cells and is_register(bog.cells[startpoint])
        else "primary_input"
    )
    result = {
        "startpoint": startpoint,
        "startpoint_type": start_type,
        "bog_arrival_ns": arrival,
        "path_depth": len(unique),
        "path_operator_count": len(unique),
        "pins": pins,
    }
    for operator in ("and", "or", "not", "xor", "mux", "buf"):
        result[f"operator_{operator}_count"] = sum(
            OPERATORS[bog.cells[c]["type"]] == operator for c in unique
        )
    result.update(statistics(fanout, "fanout"))
    result.update(statistics(caps, "capacitance_ff"))
    result.update(statistics(slew, "slew_ns"))
    return result


def extract(out, bog, design_id, representation, endpoints):
    path_rows, endpoint_rows = [], []
    sampled_valid = sampled_invalid = sampled_duplicates = 0
    for index, ep in enumerate(endpoints):
        base = {
            "design_id": design_id,
            "representation": representation,
            "endpoint_cell": ep["cell"],
            "endpoint_id": ep["endpoint_id"],
        }
        critical = []
        seen_paths = set()
        for edge in ("rise", "fall"):
            feature = parse_path(out / f"path_{index}_{edge}.rpt", bog)
            if feature:
                critical.append((edge, feature))
        endpoint = {
            **base,
            "aliases": ep["aliases"],
            "driving_register_count": ep["driving_register_count"],
            "primary_input_count": ep["primary_input_count"],
            "timing_status": "timed" if critical else "no_timed_path",
        }
        if critical:
            edge, feature = max(critical, key=lambda item: item[1]["bog_arrival_ns"])
            path_rows.append(
                {
                    **base,
                    "path_id": f"{index}:critical",
                    "path_kind": "critical",
                    "edge": edge,
                    **feature,
                }
            )
            endpoint["bog_arrival_ns"] = feature["bog_arrival_ns"]
            seen_paths.add(tuple(feature["pins"]))
        for j, candidate in enumerate(ep["topology_path_candidates"]):
            features = []
            for edge in ("rise", "fall"):
                feature = parse_path(out / f"sample_{index}_{j}_{edge}.rpt", bog)
                if feature:
                    actual = feature["pins"]
                    expected = [f"{cell}/{pin}" for cell, pin in candidate] + [
                        ep["cell"] + "/D"
                    ]
                    pos = 0
                    for pin in actual:
                        if pos < len(expected) and pin == expected[pos]:
                            pos += 1
                    if pos == len(expected):
                        features.append((edge, feature))
            if features:
                edge, feature = max(
                    features, key=lambda item: item[1]["bog_arrival_ns"]
                )
                path_rows.append(
                    {
                        **base,
                        "path_id": f"{index}:sample:{j}",
                        "path_kind": "sampled",
                        "edge": edge,
                        **feature,
                    }
                )
                signature = tuple(feature["pins"])
                if signature in seen_paths:
                    path_rows.pop()
                    sampled_duplicates += 1
                else:
                    seen_paths.add(signature)
                    sampled_valid += 1
            else:
                sampled_invalid += 1
        endpoint_rows.append(endpoint)
    ep_df = pd.DataFrame(endpoint_rows)
    # Average rank for ties; zero = slowest. Untimed endpoints remain null.
    valid = (
        ep_df["bog_arrival_ns"].notna()
        if "bog_arrival_ns" in ep_df
        else pd.Series(False, index=ep_df.index)
    )
    ep_df["bog_rank_percentile"] = np.nan
    ep_df.loc[valid, "bog_rank_percentile"] = (
        ep_df.loc[valid, "bog_arrival_ns"].rank(method="average", ascending=False) - 1
    ) / max(int(valid.sum()) - 1, 1)
    ep_df["bog_rank_group"] = np.minimum(np.floor(ep_df["bog_rank_percentile"] * 4), 3)
    ep_df.to_parquet(out / "endpoint_features.parquet", index=False)
    pd.DataFrame(path_rows).to_parquet(out / "path_features.parquet", index=False)
    summary = {
        "timed_endpoints": int(valid.sum()),
        "total_endpoints": len(ep_df),
        "valid_sampled_paths": sampled_valid,
        "rejected_sampled_candidates": sampled_invalid,
        "duplicate_sampled_paths_removed": sampled_duplicates,
        "path_rows": len(path_rows),
        "units": {"time": "ns", "capacitance": "fF"},
        "rank_is_input_feature_only": True,
    }
    design_features = bog.summary()
    counts = design_features.pop("operator_counts", {})
    design_features.update({f"operator_{k}_count": v for k, v in counts.items()})
    pd.DataFrame(
        [{"design_id": design_id, "representation": representation, **design_features}]
    ).to_parquet(out / "design_features.parquet", index=False)
    (out / "feature_validation.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
