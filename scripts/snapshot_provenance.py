"""Hash the final reproducible inputs and generated artifacts, without timestamps."""

import hashlib
import json
from pathlib import Path

root = Path.cwd()
patterns = [
    "configs/*.json",
    "data/manifests/*.json",
    "src/rtl_timing/*.py",
    "scripts/*.py",
    "uv.lock",
    ".python-version",
    "pyproject.toml",
    "data/raw/*/*",
    "data/libraries/*.lib",
    "data/processed/*/*/*.parquet",
    "data/processed/*/*/*.json",
    "data/processed/*/*/*.ys",
    "data/processed/*/*/*.tcl",
    "data/processed/*/*/bog.v",
    "data/labels/*/*.parquet",
    "data/labels/*/*.json",
    "data/labels/*/*.ys",
    "data/labels/*/*.tcl",
    "data/labels/*/*.v",
    "data/labels/*/*.lib",
    "data/labels/*/*.rpt",
]
paths = sorted(
    {
        p
        for pattern in patterns
        for p in root.glob(pattern)
        if p.is_file() and not p.name.startswith("._")
    }
)
result = {
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
}
output = root / "docs/results/task1_artifact_hashes.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(
        {
            "scope": "Final input and artifact snapshot; not a claim that every stage used identical historical code",
            "sha256": result,
        },
        indent=2,
    )
    + "\n"
)
print(len(result), "files hashed")
