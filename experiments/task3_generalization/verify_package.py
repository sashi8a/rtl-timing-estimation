"""Offline hash verification after rsync, using Python's standard library only."""

import argparse
import hashlib
import json
from pathlib import Path


def verify(run):
    run = Path(run).resolve()

    def read(path):
        return json.loads(path.read_text())

    def check(root, hashes):
        for name, expected in hashes.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError(f"Path escape: {name}")
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != expected:
                raise ValueError(f"Hash mismatch: {path}")

    m = read(run / "manifest.json")
    unsigned = {k: v for k, v in m.items() if k != "signature"}
    if (
        hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        != m["signature"]
    ):
        raise ValueError("Manifest signature differs")
    check(run, m["outputs"])
    check(run / "source_snapshot", m["source"])
    freeze = read(run / "model_freeze.json")
    if freeze["signature"] != m["signature"]:
        raise ValueError("Freeze signature differs")
    check(run, freeze["models"])
    seals = list((run / "models").glob("fold*/*/complete.json"))
    if len(seals) != 40:
        raise ValueError(f"Expected 40 model seals, got {len(seals)}")
    for path in seals + [run / "results/complete.json"]:
        s = read(path)
        if s["signature"] != m["signature"]:
            raise ValueError(f"Stale seal: {path}")
        check(path.parent, s["outputs"])
    coverage = read(run / "results/coverage.json")
    for k, v in {
        "learned_runs": 40,
        "neural_epochs": 7200,
        "designs": 17,
        "families": 8,
        "register_bits": 1053,
        "prediction_rows": 12636,
    }.items():
        if coverage[k] != v:
            raise ValueError(f"Coverage mismatch: {k}")
    print(json.dumps({"verified": True, **coverage}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, type=Path)
    a = p.parse_args()
    verify(a.run)
