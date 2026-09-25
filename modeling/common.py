"""Atomic local artifacts and fail-closed identities; no network services."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, writer):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    try:
        writer(Path(tmp))
        with open(tmp, "rb") as stream:
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path, value):
    atomic(
        path,
        lambda p: p.write_text(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ),
    )


def write_npz(path, **arrays):
    def writer(p):
        with p.open("wb") as stream:
            np.savez_compressed(stream, **arrays)

    atomic(path, writer)


def checked_hashes(root, hashes):
    for name, expected in hashes.items():
        path = (Path(root) / name).resolve()
        require(path.is_relative_to(Path(root).resolve()), f"Path escapes root: {name}")
        require(
            path.is_file() and digest(path) == expected,
            f"Stale or damaged input: {name}",
        )


def code_hashes():
    paths = list((ROOT / "modeling").glob("*.py"))
    paths += [
        ROOT / "modeling" / n for n in ("config.json", "pyproject.toml", "uv.lock")
    ]
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)}


def seal(directory, signature, names):
    write_json(
        Path(directory) / "complete.json",
        {
            "signature": signature,
            "outputs": {n: digest(Path(directory) / n) for n in names},
        },
    )


def completed(directory, signature):
    path = Path(directory) / "complete.json"
    if not path.exists():
        return False
    record = read(path)
    require(record["signature"] == signature, f"Stale completed run: {directory}")
    checked_hashes(directory, record["outputs"])
    return True
