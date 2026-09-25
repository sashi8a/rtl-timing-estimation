"""Deadline-bounded feature and label collection; failed jobs never become examples."""

import json
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .eda import generate, verify_equivalence
from .labels import generate_labels
from .libraries import bog_library, library_variant
from .provenance import input_signature, reusable, seal_artifact
from .runtime import set_deadline, stage_timeout


def error_status(error):
    return (
        "timeout"
        if isinstance(error, (TimeoutError, subprocess.TimeoutExpired))
        else "failed"
    )


def run_collection(
    root: Path, designs=None, workers=4, deadline_minutes=40, resume=True
):
    if workers not in range(1, 5):
        raise ValueError("workers must be between 1 and 4")
    root = root.resolve()
    deadline = set_deadline(deadline_minutes)
    cfg = json.loads((root / "configs/task1.json").read_text())
    manifest = json.loads((root / "data/manifests/designs.json").read_text())["designs"]
    ids = designs or [d["id"] for d in manifest]
    if len(set(ids)) != len(ids) or set(ids) - {d["id"] for d in manifest}:
        raise ValueError("Design IDs must be unique members of the manifest")
    # Prepare deterministic derived libraries serially; no shared-file writers in workers.
    for rep in cfg["representations"]:
        bog_library(root, rep)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    status_path = root / "data/collection_runs" / f"labels-{run_id}.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    archive = root / "data/archive" / run_id
    records = []

    def fresh_directory(directory):
        if directory.exists():
            saved = archive / directory.relative_to(root)
            saved.parent.mkdir(parents=True, exist_ok=True)
            directory.rename(saved)
        directory.mkdir(parents=True, exist_ok=True)

    def run_design(design):
        results = []
        try:
            for rep in cfg["representations"]:
                stage_timeout()
                directory = root / "data/processed" / design / rep
                signature = input_signature(root, design, "features", rep)
                reused = resume and reusable(directory, signature)
                if not reused:
                    fresh_directory(directory)
                    generate(root, design, rep)
                    proof = verify_equivalence(root, design, rep)
                    if proof["status"] in {"timeout", "error"}:
                        raise (
                            TimeoutError("Proof timed out")
                            if proof["status"] == "timeout"
                            else RuntimeError(
                                "Proof execution error; inspect equivalence.log"
                            )
                        )
                    stage_timeout()
                    seal_artifact(directory, signature)
                results.append(
                    {
                        "design": design,
                        "stage": "features",
                        "representation": rep,
                        "status": "reused" if reused else "completed",
                    }
                )
                print(json.dumps(results[-1]), flush=True)
            stage_timeout()
            directory = root / "data/labels" / design
            signature = input_signature(root, design, "labels")
            reused = resume and reusable(directory, signature)
            if not reused:
                fresh_directory(directory)
                summary = generate_labels(root, design)
                if summary["target_proof"]["status"] in {"timeout", "error"}:
                    raise (
                        TimeoutError("Target proof timed out")
                        if summary["target_proof"]["status"] == "timeout"
                        else RuntimeError("Target proof execution error")
                    )
                stage_timeout()
                seal_artifact(directory, signature)
            results.append(
                {
                    "design": design,
                    "stage": "labels",
                    "status": "reused" if reused else "completed",
                }
            )
        except Exception as error:  # noqa: BLE001 -- retain failures and continue other designs
            results.append(
                {
                    "design": design,
                    "stage": "collection",
                    "status": error_status(error),
                    "error": str(error),
                }
            )
        print(json.dumps(results[-1]), flush=True)
        return results

    def save():
        payload = {
            "run_id": run_id,
            "deadline_epoch": deadline,
            "library_variant": library_variant(root),
            "requested_designs": ids,
            "records": records,
        }
        status_path.write_text(json.dumps(payload, indent=2) + "\n")
        return payload

    save()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_design, d) for d in ids]
        for future in as_completed(futures):
            records.extend(future.result())
            save()
    return save()
