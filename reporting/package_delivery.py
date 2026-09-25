"""Package current documentation/code, compact data and all completed model runs."""

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    "task3-20260925-v1",
    "task3-followup-20260925-v1",
    "task3-generalization-20260925-v1",
]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    for name in RUNS:
        run = ROOT / "runs" / name
        if json.loads((run / "status.json").read_text())["state"] != "complete":
            raise ValueError(f"Incomplete study: {name}")
        for seal in run.rglob("complete.json"):
            info = json.loads(seal.read_text())
            for relative, expected in info["outputs"].items():
                target = (seal.parent / relative).resolve()
                if (
                    not target.is_relative_to(run.resolve())
                    or digest(target) != expected
                ):
                    raise ValueError(f"Stale result: {target}")
    source = (
        subprocess.check_output(
            ["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    files = {p for n in source if n and (p := ROOT / n).is_file()}
    for name in RUNS:
        files.update(
            p
            for p in (ROOT / "runs" / name).rglob("*")
            if p.is_file()
            and not p.name.startswith(".")
            and not any(part in ["__pycache__", ".venv", ".git"] for part in p.parts)
        )
    for folder in ["data/processed", "data/labels"]:
        files.update((ROOT / folder).rglob("*.parquet"))
    files.update(p for p in (ROOT / "data/releases/task2").rglob("*") if p.is_file())
    for name in ["task3_followup", "task3_generalization"]:
        files.add(ROOT / "experiments" / name / "source_revision.json")
    forbidden = [
        p
        for p in files
        if p.relative_to(ROOT).parts[0] == "personal"
        or p.relative_to(ROOT).as_posix() == "docs/interview-guide.md"
    ]
    if forbidden:
        raise ValueError(
            f"Personal material cannot enter reviewer archive: {forbidden}"
        )
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in sorted(files)}
    manifest = {
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_status": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).splitlines(),
        "files": hashes,
        "studies": RUNS,
        "raw_eda_bundle": "docs/results/task2_artifact_bundle.json",
        "note": "Private review package; all modeling artifacts, compact dataset, current methods/results, and exact per-file hashes. Raw EDA archive is separate.",
    }
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    archive = out / "rtl-timing-review.zip"
    temporary = out / "rtl-timing-review.zip.tmp"
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for relative in hashes:
            z.write(ROOT / relative, relative)
        z.writestr(
            "DELIVERY-MANIFEST.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None:
            raise ValueError("ZIP integrity error")
        for relative, expected in hashes.items():
            with z.open(relative) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != expected:
                raise ValueError(f"Archive differs: {relative}")
    temporary.replace(archive)
    sha = digest(archive)
    (out / "rtl-timing-review.zip.sha256").write_text(f"{sha}  rtl-timing-review.zip\n")
    print(
        json.dumps(
            {
                "archive": str(archive),
                "payload_files": len(hashes),
                "bytes": archive.stat().st_size,
                "sha256": sha,
                "verified": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
