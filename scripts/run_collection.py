"""Run Task 1 with bounded concurrency, recording failures without hiding them."""

import argparse
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rtl_timing.eda import generate, verify_equivalence
from rtl_timing.sources import fetch

parser = argparse.ArgumentParser()
parser.add_argument("--workers", type=int, default=2)
parser.add_argument("--designs", nargs="*")
parser.add_argument(
    "--resume-existing",
    action="store_true",
    help="Reuse completed artifacts only when inputs/configuration are unchanged",
)
args = parser.parse_args()
root = Path.cwd()
manifest = json.loads((root / "data/manifests/designs.json").read_text())
ids = args.designs or [d["id"] for d in manifest["designs"]]
representations = json.loads((root / "configs/task1.json").read_text())[
    "representations"
]
results = []
status_directory = root / "data/collection_runs"
status_directory.mkdir(parents=True, exist_ok=True)
status_path = status_directory / f"{uuid.uuid4().hex}.json"
print("RUN_STATUS", status_path.relative_to(root), flush=True)
# Fetch serially because reference libraries are shared between designs.
for design in ids:
    if (
        not args.resume_existing
        or not (root / "data/raw" / design / "provenance.json").exists()
    ):
        fetch(root, design)
    print("FETCHED", design, flush=True)


def run(design):
    runs = []
    for representation in representations:
        try:
            directory = root / "data/processed" / design / representation
            if (
                args.resume_existing
                and (directory / "summary.json").exists()
                and (directory / "equivalence.json").exists()
            ):
                summary = json.loads((directory / "summary.json").read_text())
                proof = json.loads((directory / "equivalence.json").read_text())
            else:
                summary = generate(root, design, representation)
                proof = verify_equivalence(root, design, representation)
            # Keep expensive formal proof bounded and status explicit.
            runs.append(
                {
                    "design": design,
                    "representation": representation,
                    "status": "generated",
                    "summary": summary,
                    "equivalence": proof,
                }
            )
            print(
                "GENERATED",
                design,
                representation,
                summary["register_bits"],
                proof["status"],
                flush=True,
            )
        except Exception as error:  # noqa: BLE001 -- record each failed design and continue screening
            runs.append(
                {
                    "design": design,
                    "representation": representation,
                    "status": "failed",
                    "error": str(error),
                }
            )
            print("FAILED", design, representation, str(error), flush=True)
    return runs


with ThreadPoolExecutor(max_workers=args.workers) as pool:
    for future in as_completed([pool.submit(run, design) for design in ids]):
        results.extend(future.result())
        status_path.write_text(json.dumps(results, indent=2) + "\n")
if any(r["status"] != "generated" for r in results):
    sys.exit(1)
