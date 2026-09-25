"""Fail-closed reuse of completed artifacts with matching inputs and outputs."""

import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path

from .libraries import bog_library


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def input_signature(root, design_id, kind, representation=None):
    design = next(
        d
        for d in json.loads((root / "data/manifests/designs.json").read_text())[
            "designs"
        ]
        if d["id"] == design_id
    )
    config = {
        "design": design,
        "eda": json.loads((root / "configs/eda.json").read_text()),
        "task1": json.loads((root / "configs/task1.json").read_text()),
        "kind": kind,
        "representation": representation,
        "python_version": list(sys.version_info[:3]),
        "packages": {
            name: version(name) for name in ("numpy", "pandas", "pyarrow", "networkx")
        },
    }
    paths = list((root / "data/raw" / design_id).glob("*"))
    paths.extend(
        root / name for name in ("uv.lock", "pyproject.toml", ".python-version")
    )
    modules = ["eda", "graph", "libraries", "runtime", "provenance"]
    if kind == "features":
        paths.append(bog_library(root, representation))
        modules.append("features")
    elif kind == "labels":
        paths.append(root / "data/libraries/nangate45.lib")
        modules.append("labels")
        for rep in config["task1"]["representations"]:
            directory = root / "data/processed" / design_id / rep
            paths.extend(
                directory / name
                for name in (
                    "summary.json",
                    "equivalence.json",
                    "endpoint_features.parquet",
                    "path_features.parquet",
                    "design_features.parquet",
                    "provenance.json",
                )
            )
    else:
        raise ValueError(f"Unknown artifact kind: {kind}")
    paths.extend(root / "src/rtl_timing" / f"{name}.py" for name in modules)
    files = {
        p.relative_to(root).as_posix(): digest(p)
        for p in sorted(set(paths))
        if not p.name.startswith("._")
    }
    inputs = {"config": config, "files": files}
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return {"input_key": key, "inputs": inputs}


def seal_artifact(directory, signature):
    outputs = {
        p.name: digest(p)
        for p in sorted(directory.iterdir())
        if p.is_file() and p.name != "provenance.json" and not p.name.startswith("._")
    }
    record = {**signature, "outputs": outputs}
    (directory / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")


def reusable(directory, signature):
    try:
        record = json.loads((directory / "provenance.json").read_text())
        return (
            record["input_key"] == signature["input_key"]
            and bool(record["outputs"])
            and all(
                (directory / name).is_file() and digest(directory / name) == expected
                for name, expected in record["outputs"].items()
            )
        )
    except (OSError, ValueError, KeyError):
        return False
