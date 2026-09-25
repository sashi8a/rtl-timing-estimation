"""Cross-check extracted artifacts; fails rather than inventing missing data."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def validate(root: Path):
    summary = json.loads((root / "summary.json").read_text())
    endpoints = pd.read_parquet(root / "endpoint_features.parquet")
    paths = pd.read_parquet(root / "path_features.parquet")
    assert len(endpoints) == summary["register_bits"] == summary["total_endpoints"]
    assert len(paths) == summary["path_rows"]
    assert endpoints.endpoint_cell.is_unique
    assert paths.path_id.is_unique
    assert endpoints.endpoint_id.notna().all(), "Missing RTL aliases"
    assert endpoints.endpoint_id.is_unique, "Ambiguous canonical RTL aliases"
    assert set(paths.endpoint_cell) <= set(endpoints.endpoint_cell)
    assert np.isfinite(paths.bog_arrival_ns).all()
    assert (paths.path_depth >= 0).all()
    assert (paths.path_depth == paths.path_operator_count).all()
    assert (
        paths.filter(regex="^operator_.*_count$").sum(axis=1)
        == paths.path_operator_count
    ).all()
    critical = (
        paths[paths.path_kind == "critical"].set_index("endpoint_cell").bog_arrival_ns
    )
    assert critical.index.is_unique
    assert set(critical.index) == set(
        endpoints.loc[endpoints.timing_status == "timed", "endpoint_cell"]
    )
    assert len(critical) == summary["timed_endpoints"]
    maxima = paths.groupby("endpoint_cell").bog_arrival_ns.max()
    assert ((maxima - critical) <= 1e-7).all(), "Sample exceeds maximum-arrival path"
    for feature in ("fanout", "capacitance_ff", "slew_ns"):
        assert np.allclose(
            paths[f"{feature}_std"] ** 2, paths[f"{feature}_variance"], equal_nan=True
        )
    assert endpoints.bog_rank_percentile.dropna().between(0, 1).all()
    return {
        "directory": str(root),
        "endpoint_rows": len(endpoints),
        "path_rows": len(paths),
        "checks": "passed",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    print(json.dumps(validate(parser.parse_args().directory), indent=2))
