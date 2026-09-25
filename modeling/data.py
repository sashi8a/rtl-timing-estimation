"""Freeze existing feature views, split and train-only preprocessing."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from common import (
    ROOT,
    atomic,
    checked_hashes,
    code_hashes,
    digest,
    identity,
    read,
    require,
    write_json,
    write_npz,
)

OPS = [f"operator_{op}_count" for op in ("and", "or", "not", "xor", "mux", "buf")]
DESIGN = [
    "register_bits",
    "combinational_operators",
    "max_combinational_depth",
    "net_count",
] + OPS
CONE = ["driving_register_count", "primary_input_count"]
ENDPOINT = CONE + ["bog_arrival_ns", "bog_rank_percentile"]
PATH = (
    ["bog_arrival_ns", "path_depth"]
    + OPS
    + [
        f"{kind}_{stat}"
        for kind in ("fanout", "capacitance_ff", "slew_ns")
        for stat in ("sum", "mean", "std")
    ]
    + ["empty_driver_statistics"]
)


def encode_paths(frame):
    """Explicit empty-set encoding only for verified zero-gate input paths."""
    values = frame[PATH[:-1]].copy()
    drivers = [
        f"{kind}_{stat}"
        for kind in ("fanout", "capacitance_ff")
        for stat in ("sum", "mean", "std")
    ]
    missing = values[drivers].isna()
    empty = missing.all(axis=1)
    require((~missing.any(axis=1) | empty).all(), "Partially missing driver statistics")
    require(
        (
            ~empty
            | (
                (frame.path_depth == 0)
                & (frame.startpoint_type == "primary_input")
                & frame[OPS].sum(axis=1).eq(0)
            )
        ).all(),
        "Missing statistics on nonempty path",
    )
    values.loc[empty, drivers] = 0.0
    values["empty_driver_statistics"] = empty.astype(float)
    result = values.to_numpy(dtype=float)
    require(np.isfinite(result).all(), "Unexpected missing/nonfinite path feature")
    return result


def assign_split(records, split):
    lookup = {}
    for part, families in split.items():
        for family in families:
            require(family not in lookup, f"Family overlaps: {family}")
            lookup[family] = part
    require(
        set(lookup) == set(records.family),
        "Split must cover exactly the release families",
    )
    result = records.family.map(lookup).to_numpy()
    require(
        not records.duplicated(["design_id", "target_endpoint_id"]).any(),
        "Duplicate register identity",
    )
    require(
        records.groupby("design_id").family.nunique().eq(1).all(),
        "Design crosses families",
    )
    return result


def balanced_weights(records):
    families = records.family.nunique()
    designs = records.groupby("family").design_id.nunique().to_dict()
    counts = records.groupby("design_id").size().to_dict()
    return np.array(
        [
            len(records) / (families * designs[r.family] * counts[r.design_id])
            for r in records.itertuples()
        ]
    )


def neural_scaler(x, mask, train):
    """Equal total weight per endpoint per view, excluding padded paths."""
    weights = mask[train] / mask[train].sum(axis=2, keepdims=True)
    mean = (x[train] * weights[..., None]).sum(axis=(0, 2)) / train.sum()
    var = (((x[train] - mean[None, :, None, :]) ** 2) * weights[..., None]).sum(
        axis=(0, 2)
    ) / train.sum()
    keep = (var > 1e-20).any(axis=0)
    scale = np.sqrt(var)
    scale[scale < 1e-10] = 1.0
    result = (x - mean[None, :, None, :]) / scale[None, :, None, :]
    result = result[..., keep]
    result[~mask] = 0
    reps = np.broadcast_to(
        np.eye(x.shape[1])[None, :, None, :], (*mask.shape, x.shape[1])
    )
    result = np.concatenate([result, reps], axis=-1)
    result[~mask] = 0
    require(np.isfinite(result).all(), "Nonfinite scaled features")
    return result.astype(np.float32), {
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "keep": keep.tolist(),
    }


def collect_input_hashes(records):
    hashes = {}

    def add(name, expected=None):
        value = digest(ROOT / name)
        require(expected is None or value == expected, f"Stale provenance: {name}")
        require(
            name not in hashes or hashes[name] == value, f"Inconsistent hash: {name}"
        )
        hashes[name] = value

    for name in [
        "data/releases/task2/registers.parquet",
        "data/releases/task2/manifest.json",
        "data/manifests/designs.json",
    ]:
        add(name)
    provs = {}
    for r in records.itertuples():
        provs[r.label_provenance] = r.label_provenance_sha256
        for v in json.loads(r.feature_views_json).values():
            provs[v["provenance"]] = v["provenance_sha256"]
    for name, expected in provs.items():
        add(name, expected)
        p = read(ROOT / name)
        require(identity(p["inputs"]) == p["input_key"], f"Invalid signature: {name}")
        for f, h in p["inputs"]["files"].items():
            if f not in hashes:
                add(f, h)
            else:
                require(hashes[f] == h, f"Stale input reference: {f}")
        for f, h in p["outputs"].items():
            add(str(Path(name).parent / f), h)
    return hashes


def prepare(run):
    run = Path(run)
    destination = run / "prepared"
    config = read(ROOT / "modeling/config.json")
    require(
        digest(ROOT / "data/releases/task2/registers.parquet")
        == config["release_sha256"],
        "Release hash differs",
    )
    if (destination / "manifest.json").exists():
        load(run, full_check=True)
        return
    records = (
        pd.read_parquet(ROOT / "data/releases/task2/registers.parquet")
        .sort_values(["design_id", "target_endpoint_id"])
        .reset_index(drop=True)
    )
    require(records.training_eligible.all(), "Ineligible release record")
    manifest = read(ROOT / "data/releases/task2/manifest.json")
    require(
        len(records) == manifest["unique_eligible_register_bits"] == 1304,
        "Release count differs",
    )
    require(
        all(
            d["status"] == "validated"
            and all(v == "passed" for v in d["proofs"].values())
            for d in manifest["designs"]
        ),
        "Failed mapping gate",
    )
    partitions = assign_split(records, config["split"])
    train = partitions == "train"
    hashes = collect_input_hashes(records)
    print(f"Checked {len(hashes)} source/artifact hashes", flush=True)
    tree_names, rows, bags, sog = [], [], [], []
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
                    for n in ENDPOINT
                    + DESIGN
                    + ["path_count"]
                    + [f"paths.{s}.{n}" for s in ("mean", "max", "std") for n in PATH]
                ]
            if rep == "sog":
                sog.append(float(endpoint.bog_arrival_ns))
        rows.append(vector)
        bags.append(views)
    x_tree = np.asarray(rows)
    keep = np.ptp(x_tree[train], axis=0) > 0
    max_paths = max(len(b) for row in bags for b in row)
    x = np.zeros((len(records), 4, max_paths, len(PATH) + 1 + len(CONE) + len(DESIGN)))
    mask = np.zeros(x.shape[:3], dtype=bool)
    for i, views in enumerate(bags):
        for v, b in enumerate(views):
            x[i, v, : len(b)] = b
            mask[i, v, : len(b)] = True
    x_neural, scaler = neural_scaler(x, mask, train)
    y = records.arrival_ns.to_numpy(dtype=float)
    require(np.isfinite(y).all() and (y >= 0).all(), "Invalid arrival labels")
    target_scale = float(np.median(y[train]))
    require(target_scale > 0, "Nonpositive target scale")
    weights = np.ones(len(records))
    weights[train] = balanced_weights(records[train])
    identities = records[
        ["design_id", "family", "target_endpoint_id", "target_cell"]
    ].copy()
    identities["partition"] = partitions
    destination.mkdir(parents=True, exist_ok=True)
    atomic(
        destination / "records.parquet", lambda p: identities.to_parquet(p, index=False)
    )
    write_npz(
        destination / "arrays.npz",
        tree=x_tree[:, keep],
        neural=x_neural,
        mask=mask,
        y=y,
        sog=np.asarray(sog),
        weights=weights,
    )
    frozen = {
        "config": config,
        "inputs": hashes,
        "code": code_hashes(),
        "tree_columns": np.asarray(tree_names)[keep].tolist(),
        "tree_candidate_columns": tree_names,
        "neural_numeric_columns": PATH + ["is_register_launch"] + CONE + DESIGN,
        "scaler": scaler,
        "target_scale_ns": target_scale,
        "empty_driver_statistics_paths": {
            rep: int(
                sum(b[vi][:, PATH.index("empty_driver_statistics")].sum() for b in bags)
            )
            for vi, rep in enumerate(config["representations"])
        },
        "counts": identities.groupby("partition").size().to_dict(),
        "outputs": {
            n: digest(destination / n) for n in ("records.parquet", "arrays.npz")
        },
    }
    frozen["signature"] = identity(frozen)
    write_json(destination / "manifest.json", frozen)
    write_json(
        run / "split.json",
        {
            "families": config["split"],
            "counts": frozen["counts"],
            "signature": frozen["signature"],
            "endpoints": identities.to_dict(orient="records"),
        },
    )
    print(
        f"Prepared {frozen['counts']}; tree={x_tree[:, keep].shape}, neural={x_neural.shape}",
        flush=True,
    )


def load(run, full_check=False):
    p = Path(run) / "prepared"
    manifest = read(p / "manifest.json")
    unsigned = {k: v for k, v in manifest.items() if k != "signature"}
    require(identity(unsigned) == manifest["signature"], "Preparation manifest damaged")
    require(
        code_hashes() == manifest["code"],
        "Modeling code/config/lock changed; use a new run directory",
    )
    checked_hashes(p, manifest["outputs"])
    if full_check:
        checked_hashes(ROOT, manifest["inputs"])
    with np.load(p / "arrays.npz", allow_pickle=False) as archive:
        arrays = dict(archive)
    return pd.read_parquet(p / "records.parquet"), arrays, manifest
