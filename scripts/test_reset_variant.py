"""Reproduce the bounded, isolated reset-cell adoption experiment."""

import argparse
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rtl_timing.eda import generate, verify_equivalence
from rtl_timing.libraries import bog_library, cell_blocks
from rtl_timing.runtime import set_deadline


def check_libraries(root):
    checks = {}
    full = cell_blocks((root / "data/libraries/nangate45.lib").read_text())
    for rep in ("sog", "aig", "aimg", "xag"):
        original = cell_blocks(
            (root / f"data/libraries/nangate45_{rep}.lib").read_text()
        )
        derived = cell_blocks(bog_library(root, rep).read_text())
        assert set(derived) - set(original) == {"DFFR_X1", "DFFS_X1"}
        assert set(original) <= set(derived)
        assert all(derived[name] == block for name, block in original.items())
        assert all(
            derived[name].lstrip() == full[name].lstrip()
            for name in ("DFFR_X1", "DFFS_X1")
        )
        checks[rep] = {
            "original_cells": sorted(original),
            "added_cells": sorted(set(derived) - set(original)),
            "original_cell_blocks_unchanged": True,
            "added_blocks_match_source": True,
        }
    return checks


def experiment(root, minutes):
    set_deadline(min(minutes, 20))
    out = (
        root
        / "data/experiments"
        / time.strftime("reset_v1-%Y%m%dT%H%M%SZ", time.gmtime())
    )
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(root / "configs", out / "configs")
    shutil.copytree(root / "data/manifests", out / "data/manifests")
    shutil.copytree(root / "data/libraries", out / "data/libraries")
    config = json.loads((out / "configs/task1.json").read_text())
    config["bog_library_variant"] = "reset_v1"
    (out / "configs/task1.json").write_text(json.dumps(config, indent=2) + "\n")
    for design in ("timer32", "pwm256", "gcd"):
        shutil.copytree(root / "data/raw" / design, out / "data/raw" / design)
    libraries = check_libraries(out)

    def run(pair):
        design, rep = pair
        result = {"design": design, "representation": rep}
        try:
            summary = generate(out, design, rep)
            result.update(verify_equivalence(out, design, rep))
            result["timed_endpoints"] = summary["timed_endpoints"]
        except Exception as error:  # noqa: BLE001 -- preserve all experiment failures
            result.update(status="failed", error=str(error))
        print(json.dumps(result), flush=True)
        return result

    pairs = [
        (design, rep)
        for design in ("timer32", "pwm256", "gcd")
        for rep in config["representations"]
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, pairs))
    decision = {
        "variant": "reset_v1",
        "adopt": all(r["status"] == "passed" for r in results),
        "proof_method": "unchanged clk2fflogic/equiv_simple/equiv_induct -seq 4",
        "libraries": libraries,
        "results": results,
    }
    (out / "decision.json").write_text(json.dumps(decision, indent=2) + "\n")
    return decision


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run", action="store_true", help="Run the 12 isolated EDA checks"
    )
    parser.add_argument("--deadline-minutes", type=float, default=20)
    args = parser.parse_args()
    root = Path.cwd()
    if args.run:
        result = experiment(root, args.deadline_minutes)
    else:
        result = check_libraries(root)
        (root / "docs/results/reset_library_validation.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
    print(json.dumps(result, indent=2))
