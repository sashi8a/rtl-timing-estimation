"""Fetch pinned source files, retaining provenance and upstream notices."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def fetch(root: Path, design_id: str) -> dict:
    cfg = json.loads((root / "configs/task1.json").read_text())
    design = next(
        d
        for d in json.loads((root / "data/manifests/designs.json").read_text())[
            "designs"
        ]
        if d["id"] == design_id
    )
    entries = []
    upstream = cfg["upstream_revision"]
    repository = design["source_repository"].removeprefix("https://github.com/")
    source_paths = design["source_files"] + design.get("notice_files", [])
    if "generated_constraints" not in design:
        source_paths += [design["sdc"], "LICENSE_BUILD_RUN_SCRIPTS"]
    downloads = [
        (
            f"https://raw.githubusercontent.com/{repository}/{design['source_revision']}/{p}",
            root / "data/raw" / design_id / Path(p).name,
        )
        for p in source_paths
    ]
    for name in ["nangate45.lib"] + [
        f"nangate45_{r}.lib" for r in cfg["representations"]
    ]:
        downloads.append(
            (
                f"https://raw.githubusercontent.com/hkust-zhiyao/RTL-Timer/{upstream}/vlg2bog/scr_ys/lib/{name}",
                root / "data/libraries" / name,
            )
        )
    for name in [
        "LICENSE",
        "report_example/timing_path.py",
        "vlg2bog/scr_ys/run_ys_template.ys",
    ]:
        downloads.append(
            (
                f"https://raw.githubusercontent.com/hkust-zhiyao/RTL-Timer/{upstream}/{name}",
                root / "third_party/rtl-timer" / name,
            )
        )
    for url, path in downloads:
        with urlopen(url, timeout=90) as response:
            payload = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        entries.append(
            {
                "url": url,
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    if "generated_constraints" in design:
        c = design["generated_constraints"]
        text = f"""# Generated from committed design manifest; ns and fF.
create_clock -name core_clock -period {c["period_ns"]} [get_ports {{{design["clock"]}}}]
set_input_delay {c["input_delay_ns"]} -clock core_clock [all_inputs -no_clocks]
set_input_transition {c["input_transition_ns"]} [all_inputs -no_clocks]
set_output_delay {c["output_delay_ns"]} -clock core_clock [all_outputs]
set_load {c["output_load_ff"]} [all_outputs]
"""
        path = root / "data/raw" / design_id / "generated.sdc"
        path.write_text(text)
        entries.append(
            {
                "generated_from": "data/manifests/designs.json",
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
    # Some JPEG source files refer to a missing simulation-only timescale header.
    raw = root / "data/raw" / design_id
    if (
        any('`include "timescale.v"' in p.read_text() for p in raw.glob("*.v"))
        and not (raw / "timescale.v").exists()
    ):
        path = raw / "timescale.v"
        path.write_text("`timescale 1ns/1ps\n")
        entries.append(
            {
                "generated": "simulation timescale header; no synthesized logic",
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    out = root / "data/raw" / design_id / "provenance.json"
    out.write_text(json.dumps(entries, indent=2) + "\n")
    return {"design": design_id, "files": len(entries)}
