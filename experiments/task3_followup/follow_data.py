"""Bind follow-ups to the original immutable data, code, and paired controls."""

import copy
import importlib.metadata
import platform
import sys
from pathlib import Path

import bootstrap
from common import (
    checked_hashes,
    completed,
    digest,
    identity,
    read,
    require,
    write_json,
)

from data import load as base_load

HERE = Path(__file__).resolve().parent


def source_hashes():
    paths = list(HERE.glob("*.py")) + [
        HERE / "config.json",
        HERE / "rtl-task3-followup.service",
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
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


def prepare(base, run):
    base, run = Path(base).resolve(), Path(run).resolve()
    require(base != run, "Follow-up must not overwrite the original run")
    run.mkdir(parents=True, exist_ok=True)
    if (run / "manifest.json").exists():
        require(
            read(run / "manifest.json")["base_run"] == str(base), "Different base run"
        )
        load(run, full_check=True)
        return
    _records, arrays, frozen = base_load(base, full_check=True)
    config = read(HERE / "config.json")
    require(
        frozen["signature"] == config["base_signature"],
        "Unexpected original experiment",
    )
    require(
        completed(base / "results", frozen["signature"]), "Original results incomplete"
    )
    original_runtime = read(base / "runtime.json")
    current = runtime()
    require(
        current["python"] == original_runtime["python"]
        and current["packages"] == original_runtime["packages"],
        "Original environment changed",
    )
    require(arrays["neural"].shape[-1] == 33, "Unexpected original input layout")
    require(
        frozen["counts"] == {"train": 716, "validation": 337, "test": 251},
        "Original split differs",
    )
    references = [
        "prepared/manifest.json",
        "split.json",
        "runtime.json",
        "results/complete.json",
        "results/metrics.json",
        "results/test_predictions.parquet",
    ]
    paired = {}
    for seed in config["seeds"]:
        directory = base / "models" / f"N1-seed{seed}"
        require(
            completed(directory, frozen["signature"]), "Paired N1 reference incomplete"
        )
        paired[str(seed)] = read(directory / "details.json")["initial_mlp_sha256"]
        references += [
            f"models/N1-seed{seed}/{n}"
            for n in (
                "complete.json",
                "details.json",
                "selected.pt",
                "predictions.parquet",
            )
        ]
    manifest = {
        "base_run": str(base),
        "base_signature": frozen["signature"],
        "base_references": {p: digest(base / p) for p in references},
        "followup_config": config,
        "source": source_hashes(),
        "source_revision": read(HERE / "source_revision.json"),
        "runtime": current,
        "paired_initializations": paired,
        "counts": frozen["counts"],
    }
    manifest["signature"] = identity(manifest)
    write_json(run / "manifest.json", manifest)
    print(
        "Follow-up inputs frozen; original data and scalers reused unchanged",
        flush=True,
    )


def load(run, full_check=False):
    manifest = read(Path(run) / "manifest.json")
    require(
        identity({k: v for k, v in manifest.items() if k != "signature"})
        == manifest["signature"],
        "Follow-up manifest damaged",
    )
    require(
        manifest["source"] == source_hashes(),
        "Follow-up code/config/source revision changed",
    )
    require(runtime() == manifest["runtime"], "Follow-up runtime changed")
    checked_hashes(manifest["base_run"], manifest["base_references"])
    records, arrays, frozen = base_load(manifest["base_run"], full_check=full_check)
    require(frozen["signature"] == manifest["base_signature"], "Base signature changed")
    v = frozen["config"]["representations"].index("sog")
    arrays["neural"] = arrays["neural"][:, v : v + 1]
    arrays["mask"] = arrays["mask"][:, v : v + 1]
    derived = copy.deepcopy(frozen)
    derived["config"]["representations"] = ["sog"]
    derived["signature"] = manifest["signature"]
    derived["paired_initializations"] = manifest["paired_initializations"]
    return records, arrays, derived
