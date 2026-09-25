"""Versioned BOG libraries; never overwrite pinned upstream files."""

import json
import re
from pathlib import Path

VARIANTS = ("upstream", "reset_v1")


def cell_blocks(text):
    blocks = {}
    for match in re.finditer(r"^\s*cell\s*\(\s*(\w+)\s*\)\s*\{", text, re.MULTILINE):
        pos = text.index("{", match.start()) + 1
        depth, quoted, escaped = 1, False, False
        while depth and pos < len(text):
            c = text[pos]
            if quoted:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    quoted = False
            elif c == '"':
                quoted = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            pos += 1
        if depth:
            raise ValueError("Unbalanced Liberty cell")
        blocks[match.group(1)] = text[match.start() : pos]
    return blocks


def extend_reset_cells(upstream, full):
    original = cell_blocks(upstream)
    additions = {name: cell_blocks(full)[name] for name in ("DFFR_X1", "DFFS_X1")}
    if set(original) & set(additions):
        raise ValueError("Upstream already contains the additional reset cells")
    end = upstream.rfind("}")
    if end < 0:
        raise ValueError("Missing library closing brace")
    result = upstream[:end] + "\n".join(additions.values()) + "\n" + upstream[end:]
    actual = cell_blocks(result)
    assert set(actual) == set(original) | set(additions)
    assert all(actual[name] == block for name, block in original.items())
    return result


def library_variant(root):
    variant = json.loads((root / "configs/task1.json").read_text()).get(
        "bog_library_variant", "upstream"
    )
    if variant not in VARIANTS:
        raise ValueError(f"Unknown BOG library variant: {variant}")
    return variant


def bog_library(root: Path, representation: str):
    original = root / "data/libraries" / f"nangate45_{representation}.lib"
    if library_variant(root) == "upstream":
        return original
    derived = root / "data/libraries/reset_v1" / original.name
    contents = extend_reset_cells(
        original.read_text(), (root / "data/libraries/nangate45.lib").read_text()
    )
    derived.parent.mkdir(parents=True, exist_ok=True)
    if not derived.exists() or derived.read_text() != contents:
        derived.write_text(contents)
    return derived
