"""Rebuild the original allowlists from raw immutable development-only tables."""

import json

import bootstrap  # noqa: F401
import numpy as np
import pandas as pd
from common import ROOT, require

from data import CONE, DESIGN, ENDPOINT, PATH, encode_paths

NUMERIC = (
    [f"path.{n}" for n in PATH]
    + ["path.is_register_launch"]
    + [f"cone.{n}" for n in CONE]
    + [f"design.{n}" for n in DESIGN]
)


def collect(records, config):
    tree_names, rows, bags, sog, depths = [], [], [], [], []
    cache = {}
    for r in records.itertuples():
        vector, views = [], []
        for rep in config["representations"]:
            v = json.loads(r.feature_views_json)[rep]
            key = (r.design_id, rep)
            if key not in cache:
                d = pd.read_parquet(ROOT / v["design_features"])
                e = pd.read_parquet(ROOT / v["endpoint_features"])
                p = pd.read_parquet(ROOT / v["path_features"])
                require(
                    len(d) == 1 and e.endpoint_id.is_unique, "Ambiguous feature records"
                )
                require(
                    not p.duplicated(["endpoint_id", "path_id"]).any(),
                    "Duplicate sampled path identity",
                )
                require(
                    set(p.startpoint_type) <= {"register", "primary_input"},
                    "Unknown path source type",
                )
                require(
                    (p.path_depth == p.path_operator_count).all(),
                    "Depth/operator duplicate assumption differs",
                )
                require(
                    (e.design_id == r.design_id).all()
                    and (p.design_id == r.design_id).all(),
                    "Design mismatch",
                )
                require(
                    (d.representation == rep).all()
                    and (e.representation == rep).all()
                    and (p.representation == rep).all(),
                    "View mismatch",
                )
                cache[key] = (
                    d.iloc[0],
                    e.set_index("endpoint_id"),
                    {k: g.sort_values("path_id") for k, g in p.groupby("endpoint_id")},
                )
            d, e, grouped = cache[key]
            endpoint = e.loc[v["endpoint_id"]]
            require(
                endpoint.endpoint_cell == v["endpoint_cell"], "Endpoint cell mismatch"
            )
            require(endpoint.timing_status == "timed", "Untimed endpoint")
            p = grouped[v["endpoint_id"]]
            require(
                len(p) > 0 and (p.endpoint_cell == v["endpoint_cell"]).all(),
                "Empty or mismatched bag",
            )
            path = encode_paths(p)
            context = np.r_[
                endpoint[CONE].to_numpy(dtype=float), d[DESIGN].to_numpy(dtype=float)
            ]
            neural = np.column_stack(
                [
                    path,
                    (p.startpoint_type == "register").astype(float),
                    np.tile(context, (len(p), 1)),
                ]
            )
            require(np.isfinite(neural).all(), "Missing/nonfinite neural inputs")
            views.append(neural)
            values = np.r_[
                endpoint[ENDPOINT].to_numpy(dtype=float),
                d[DESIGN].to_numpy(dtype=float),
                len(p),
                path.mean(axis=0),
                path.max(axis=0),
                path.std(axis=0),
            ]
            require(np.isfinite(values).all(), "Missing/nonfinite tree inputs")
            vector.extend(values.tolist())
            if r.Index == 0:
                tree_names += [
                    f"{rep}.{n}"
                    for n in [f"cone.{n}" for n in ENDPOINT]
                    + [f"design.{n}" for n in DESIGN]
                    + ["path.count"]
                    + [f"path.{s}.{n}" for s in ("mean", "max", "std") for n in PATH]
                ]
            if rep == "sog":
                sog.append(float(endpoint.bog_arrival_ns))
                depths.append(float(p.path_depth.max()))
        rows.append(vector)
        bags.append(views)
    x_tree = np.asarray(rows)
    max_paths = config["max_paths"]
    require(max(len(b) for row in bags for b in row) <= max_paths, "Path cap exceeded")
    x = np.zeros((len(records), 4, max_paths, len(PATH) + 1 + len(CONE) + len(DESIGN)))
    mask = np.zeros(x.shape[:3], dtype=bool)
    for i, views in enumerate(bags):
        for v, b in enumerate(views):
            x[i, v, : len(b)] = b
            mask[i, v, : len(b)] = True
    return (
        {"tree": x_tree, "neural": x, "mask": mask, "sog": np.asarray(sog)},
        {"tree": tree_names, "neural": NUMERIC},
        np.asarray(depths),
    )
