"""Reproduce or summarize bounded diagnostic proofs without promoting their status."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from rtl_timing.eda import container

parser = argparse.ArgumentParser()
parser.add_argument(
    "--run",
    action="store_true",
    help="Rerun diagnostic variants; otherwise read retained logs",
)
args = parser.parse_args()
root = Path.cwd()
manifest = json.loads((root / "data/manifests/designs.json").read_text())
results = []
for design in ("timer32", "pwm256"):
    top = next(d["top"] for d in manifest["designs"] if d["id"] == design)
    directory = root / "data/processed" / design / "sog"
    base = (directory / "equivalence.ys").read_text()
    for variant in ("preclock", "deeper", "sync_assumption"):
        if variant == "preclock":
            script = base.replace("\nclk2fflogic\n", "\n")
            for name in ("gold", "gate"):
                script = script.replace(
                    f"rename {top} {name}",
                    f"clk2fflogic\nopt_clean\nrename {top} {name}",
                )
        elif variant == "deeper":
            script = base.replace(
                "equiv_simple\n", "equiv_simple -undef -seq 8\n"
            ).replace("equiv_induct -seq 4", "equiv_induct -undef -seq 16")
        else:
            script = base.replace("clk2fflogic", "async2sync")
        source = directory / f"equivalence_{variant}.ys"
        log = directory / f"equivalence_{variant}.log"
        if args.run:
            source.write_text(script)
            try:
                container(root, f"yosys -s {source.relative_to(root)}", log)
            except Exception as error:  # noqa: BLE001 -- failure is diagnostic evidence
                print(design, variant, type(error).__name__, flush=True)
        text = log.read_text()
        results.append(
            {
                "design": design,
                "representation": "sog",
                "variant": variant,
                "status": "passed_under_sync_assumption"
                if variant == "sync_assumption"
                and "Equivalence successfully proven" in text
                else "passed"
                if "Equivalence successfully proven" in text
                else "unproven",
                "unproven_signals": re.findall(
                    r"^\s*Unproven \$equiv.*$", text, re.MULTILINE
                ),
                "script_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                "changes_training_eligibility": False,
            }
        )
output = root / "docs/results/equivalence_diagnostics.json"
output.write_text(
    json.dumps(
        {
            "scope": "Two representative SOG mappings, not a diagnosis of all unproven runs",
            "sync_assumption": "async2sync assumes clock-synchronized asynchronous signals and negative hold time; not full asynchronous equivalence",
            "results": results,
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps(results, indent=2))
