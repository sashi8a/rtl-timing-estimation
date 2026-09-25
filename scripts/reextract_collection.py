"""Recompute feature tables from existing reports without rerunning EDA."""

import json
from pathlib import Path

from rtl_timing.features import extract
from rtl_timing.graph import load_bog

root = Path.cwd()
manifest = json.loads((root / "data/manifests/designs.json").read_text())
for design in manifest["designs"]:
    for directory in sorted((root / "data/processed" / design["id"]).glob("*")):
        if not (directory / "summary.json").exists():
            continue
        bog = load_bog(directory / "bog.json", design["top"], directory.name)
        endpoints = json.loads((directory / "endpoints.json").read_text())
        summary = json.loads((directory / "summary.json").read_text())
        summary.update(bog.summary())
        summary.update(extract(directory, bog, design["id"], directory.name, endpoints))
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(design["id"], directory.name, summary["path_rows"], flush=True)
