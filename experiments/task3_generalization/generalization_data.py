"""Immutable fold preparation; training workers load only training partitions."""

import importlib.metadata
import platform
import shutil
import sys
from pathlib import Path

import bootstrap
import numpy as np
import pandas as pd
from common import (
    ROOT,
    atomic,
    checked_hashes,
    code_hashes,
    completed,
    digest,
    identity,
    read,
    require,
    write_json,
    write_npz,
)
from raw_features import collect

from data import balanced_weights, collect_input_hashes, neural_scaler

HERE = Path(__file__).resolve().parent


def source_hashes():
    paths = list(HERE.rglob("*.py")) + [
        HERE / "config.json",
        HERE / "rtl-task3-generalization.service",
        HERE / "source_revision.json",
    ]
    return {str(p.relative_to(bootstrap.ROOT)): digest(p) for p in sorted(paths)}


def runtime():
    import torch

    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {
            p: importlib.metadata.version(p)
            for p in ("numpy", "pandas", "pyarrow", "torch", "scikit-learn", "scipy")
        },
        "installed_packages": {
            d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
        },
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


def assign_folds(records, config):
    families = [f for pair in config["folds"] for f in pair]
    require(len(families) == len(set(families)) == 8, "Family overlap")
    require(
        set(records.family) == set(families),
        "Unexpected/missing family; AES/UART forbidden",
    )
    require(
        not records.duplicated(["design_id", "target_endpoint_id"]).any(),
        "Duplicate endpoint",
    )
    require(
        records.groupby("design_id").family.nunique().eq(1).all(),
        "Design spans families",
    )
    result = records.family.map(
        {f: i + 1 for i, pair in enumerate(config["folds"]) for f in pair}
    ).to_numpy()
    require(
        [int((result == i).sum()) for i in range(1, 5)] == config["eval_counts"],
        "Fold counts changed",
    )
    return result


def fit_preprocessing(raw, y, records, train, schema):
    # Only these slices determine all fitted quantities and feature layout.
    keep = np.ptp(raw["tree"][train], axis=0) > 0
    scaled, scaler = neural_scaler(raw["neural"], raw["mask"], train)
    scale = float(np.median(y[train]))
    require(scale > 0, "Nonpositive training median")
    columns = np.asarray(schema["neural"])[scaler["keep"]].tolist() + [
        f"representation.{r}" for r in ("sog", "aig", "aimg", "xag")
    ]
    fitted = {
        "scaler": scaler,
        "tree_keep": keep.tolist(),
        "tree_columns": np.asarray(schema["tree"])[keep].tolist(),
        "neural_columns": columns,
        "context_indices": [
            i for i, n in enumerate(columns) if n.startswith("design.")
        ],
        "target_scale_ns": scale,
        "quartiles_ns": np.quantile(y[train], [0.25, 0.5, 0.75]).tolist(),
    }
    transformed = {
        "tree": raw["tree"][:, keep],
        "neural": scaled,
        "mask": raw["mask"],
        "sog": raw["sog"],
        "y": y,
    }
    return transformed, fitted, balanced_weights(records[train])


def prepare(base, run):
    base, run = Path(base).resolve(), Path(run).resolve()
    require(base != run, "Cannot overwrite base")
    if (run / "manifest.json").exists():
        require(read(run / "manifest.json")["base_run"] == str(base), "Base differs")
        load_manifest(run, full_check=True)
        return
    config = read(HERE / "config.json")
    original = read(base / "prepared/manifest.json")
    require(
        identity({k: v for k, v in original.items() if k != "signature"})
        == original["signature"]
        == config["base_signature"],
        "Base manifest differs",
    )
    require(code_hashes() == original["code"], "Original code changed")
    require(completed(base / "results", original["signature"]), "Base incomplete")
    current = runtime()
    old = read(base / "runtime.json")
    require(
        current["python"] == old["python"] and current["packages"] == old["packages"],
        "Locked environment differs",
    )
    require(
        digest(ROOT / "data/releases/task2/registers.parquet")
        == config["release_sha256"],
        "Release changed",
    )
    release = read(ROOT / "data/releases/task2/manifest.json")
    require(
        all(
            d["status"] == "validated"
            and all(v == "passed" for v in d["proofs"].values())
            for d in release["designs"]
        ),
        "Mapping proof failed",
    )
    records = pd.read_parquet(ROOT / "data/releases/task2/registers.parquet")
    records = (
        records[~records.family.isin(config["excluded_families"])]
        .sort_values(["design_id", "target_endpoint_id"])
        .reset_index(drop=True)
    )
    require(
        len(records) == 1053
        and records.design_id.nunique() == 17
        and records.training_eligible.all(),
        "Development coverage/eligibility differs",
    )
    folds = assign_folds(records, config)
    inputs = collect_input_hashes(records)
    print(
        f"Verified {len(inputs)} raw input hashes; collecting development-only features",
        flush=True,
    )
    raw, schema, depth = collect(records, config)
    y = records.arrival_ns.to_numpy(float)
    require(np.isfinite(y).all() and (y >= 0).all(), "Invalid labels")
    meta = records[["design_id", "family", "target_endpoint_id", "target_cell"]].copy()
    meta["evaluation_fold"] = folds
    outputs = {}
    for fold in range(1, 5):
        train = folds != fold
        arrays, fitted, weights = fit_preprocessing(raw, y, records, train, schema)
        folder = run / f"fold{fold}"
        for part, idx in [("train", train), ("evaluation", ~train)]:
            values = {k: v[idx] for k, v in arrays.items()}
            m = meta[idx].copy()
            if part == "train":
                values["weights"] = weights
            else:
                m["target_launch_type"] = records.loc[idx, "startpoint_type"].to_numpy()
                m["sog_max_sampled_path_depth"] = depth[idx]
            write_npz(folder / f"{part}.npz", **values)
            atomic(
                folder / f"{part}.parquet", lambda p, m=m: m.to_parquet(p, index=False)
            )
        fitted.update(
            fold=fold,
            training_families=sorted(records[train].family.unique()),
            evaluation_families=config["folds"][fold - 1],
            counts={"train": int(train.sum()), "evaluation": int((~train).sum())},
            schema=schema,
        )
        write_json(folder / "preprocessing.json", fitted)
        for p in folder.iterdir():
            if p.is_file():
                outputs[str(p.relative_to(run))] = digest(p)
    manifest = {
        "base_run": str(base),
        "base_signature": original["signature"],
        "base_references": {
            p: digest(base / p) for p in ["prepared/manifest.json", "runtime.json"]
        },
        "config": config,
        "inputs": inputs,
        "original_code": code_hashes(),
        "source": source_hashes(),
        "source_revision": read(HERE / "source_revision.json"),
        "runtime": current,
        "outputs": outputs,
        "fold_membership": meta.to_dict("records"),
    }
    for name in manifest["source"]:
        destination = run / "source_snapshot" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    manifest["signature"] = identity(manifest)
    write_json(run / "manifest.json", manifest)
    print(
        "Four folds frozen; evaluation partitions excluded from training loaders",
        flush=True,
    )


def load_manifest(run, full_check=False):
    run = Path(run)
    m = read(run / "manifest.json")
    require(
        identity({k: v for k, v in m.items() if k != "signature"}) == m["signature"],
        "Damaged manifest",
    )
    require(
        m["source"] == source_hashes() and m["original_code"] == code_hashes(),
        "Code/config/revision changed",
    )
    require(m["runtime"] == runtime(), "Runtime changed")
    checked_hashes(m["base_run"], m["base_references"])
    checked_hashes(run, m["outputs"])
    if full_check:
        checked_hashes(ROOT, m["inputs"])
    return m


def load_partition(run, fold, part, manifest=None):
    require(part in ("train", "evaluation"), "Unknown partition")
    m = manifest or load_manifest(run)
    folder = Path(run) / f"fold{fold}"
    with np.load(folder / f"{part}.npz", allow_pickle=False) as archive:
        a = dict(archive)
    return (
        pd.read_parquet(folder / f"{part}.parquet"),
        a,
        read(folder / "preprocessing.json"),
        m,
    )
