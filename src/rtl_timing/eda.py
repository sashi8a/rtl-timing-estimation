"""Pinned-container synthesis and BOG timing extraction."""

import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from .graph import load_bog


def container(root: Path, command: str, log: Path):
    cfg = json.loads((root / "configs/eda.json").read_text())
    name = "rtl-timing-" + uuid.uuid4().hex[:12]
    argv = cfg["docker_prefix"] + [
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{root.resolve()}:/work",
        "-w",
        "/work",
        cfg["image"],
        "bash",
        "-c",
        f"source {shlex.quote(cfg['environment_script'])} >/dev/null && {command}",
    ]
    with log.open("w") as out:
        try:
            subprocess.run(
                argv, stdout=out, stderr=subprocess.STDOUT, check=True, timeout=600
            )
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            subprocess.run(
                cfg["docker_prefix"] + ["stop", "--time", "2", name],
                stdout=out,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=30,
            )
            raise


def normalize_mapped_verilog(text: str) -> str:
    """OpenSTA's gate-netlist reader rejects signed declaration qualifiers.

    At this stage arithmetic is already mapped to cells and explicit bit wiring.
    Preserve the raw export and verify normalized logic with equivalence checks.
    """
    return re.sub(
        r"^(\s*(?:wire|input|output))\s+signed\b", r"\1", text, flags=re.MULTILINE
    )


def generate(root: Path, design_id: str, representation: str):
    root = root.resolve()
    design = next(
        d
        for d in json.loads((root / "data/manifests/designs.json").read_text())[
            "designs"
        ]
        if d["id"] == design_id
    )
    out = root / "data/processed" / design_id / representation
    out.mkdir(parents=True, exist_ok=True)
    # A failed rerun must not inherit completion/proof markers from an older run.
    for marker in ("summary.json", "equivalence.json", "feature_validation.json"):
        (out / marker).unlink(missing_ok=True)
    relative = out.relative_to(root).as_posix()
    library = f"data/libraries/nangate45_{representation}.lib"
    sources = " ".join(
        f"data/raw/{design_id}/{Path(p).name}" for p in design["source_files"]
    )
    top = design["top"]
    # Adapted from RTL-Timer run_ys_template.ys; explicitly flatten for graph traversal.
    script = f"""read_liberty -lib {library}
read_verilog -I data/raw/{design_id} {sources}
hierarchy -check -top {top}
proc
flatten
opt -fast
fsm
opt -fast
memory
opt -fast
techmap
opt -fast
rename -wire t:$*DFF*
write_json {relative}/premap.json
dfflibmap -liberty {library}
abc -liberty {library}
clean
check -assert
write_verilog -norename -noattr -noexpr {relative}/bog.v
write_json {relative}/bog.json
stat -top {top}
"""
    (out / "synthesis.ys").write_text(script)
    started = time.monotonic()
    container(root, f"yosys -s {relative}/synthesis.ys", out / "synthesis.log")
    raw_netlist = (out / "bog.v").read_text()
    (out / "bog.raw.v").write_text(raw_netlist)
    (out / "bog.v").write_text(normalize_mapped_verilog(raw_netlist))
    bog = load_bog(out / "bog.json", top, representation)
    endpoints = list(bog.endpoints())
    cfg = json.loads((root / "configs/task1.json").read_text())
    for ep in endpoints:
        regs, inputs, operators = bog.cone(ep["d_bit"])
        ep.update(
            driving_register_count=len(regs),
            primary_input_count=len(inputs),
            cone_operator_count=len(operators),
        )
        requested, candidates = bog.sample_paths(
            ep, cfg["seed"], cfg["max_random_paths"]
        )
        ep.update(random_paths_requested=requested, topology_path_candidates=candidates)
    (out / "endpoints.json").write_text(json.dumps(endpoints, indent=2) + "\n")
    # Per-endpoint queries avoid global top-N truncation. Full text retained for audit.
    tcl = f"""read_lef /OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty {library}
read_verilog {relative}/bog.v
link_design {top}
read_sdc data/raw/{design_id}/{Path(design["sdc"]).name}
report_units
check_setup -verbose
"""
    for index, ep in enumerate(endpoints):
        pin = ep["cell"] + "/D"
        if any(c in pin for c in "{}\n"):
            raise ValueError("Unsupported Tcl identifier in endpoint")
        for edge in ("rise", "fall"):
            tcl += f"report_checks -to [get_pins {{{pin}}}] -path_delay max_{edge} -group_path_count 1 -endpoint_path_count 1 -format full -fields {{capacitance slew fanout input_pin net}} -digits 9 > {relative}/path_{index}_{edge}.rpt\n"
        for j, candidate in enumerate(ep["topology_path_candidates"]):
            start_cell, start_port = candidate[0]
            args = f"-from [get_pins {{{start_cell}/{start_port}}}]"
            for cell, port in candidate[1:]:
                args += f" -through [get_pins {{{cell}/{port}}}]"
            for edge in ("rise", "fall"):
                tcl += f"report_checks {args} -to [get_pins {{{pin}}}] -path_delay max_{edge} -group_path_count 1 -endpoint_path_count 1 -format full -fields {{capacitance slew fanout input_pin net}} -digits 9 > {relative}/sample_{index}_{j}_{edge}.rpt\n"
    tcl += "exit\n"
    (out / "timing.tcl").write_text(tcl)
    container(root, f"openroad -exit {relative}/timing.tcl", out / "timing.log")
    timing_log = (out / "timing.log").read_text()
    if "time 1ns" not in timing_log or "capacitance 1fF" not in timing_log:
        raise ValueError("Unexpected STA units: explicit conversion required")
    from .features import extract

    validation = extract(out, bog, design_id, representation, endpoints)
    summary = {**bog.summary(), **validation}
    summary.update(
        design_id=design_id,
        representation=representation,
        duration_seconds=time.monotonic() - started,
        bog_sha256=hashlib.sha256((out / "bog.json").read_bytes()).hexdigest(),
        sdc_sha256=hashlib.sha256(
            (root / "data/raw" / design_id / Path(design["sdc"]).name).read_bytes()
        ).hexdigest(),
        library_sha256=hashlib.sha256((root / library).read_bytes()).hexdigest(),
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def verify_equivalence(root: Path, design_id: str, representation: str):
    """Check mapped BOG against the common pre-mapping logic with Yosys."""
    root = root.resolve()
    design = next(
        d
        for d in json.loads((root / "data/manifests/designs.json").read_text())[
            "designs"
        ]
        if d["id"] == design_id
    )
    out = root / "data/processed" / design_id / representation
    top = design["top"]
    return verify_mapped_netlist(
        root, out, top, f"data/libraries/nangate45_{representation}.lib"
    )


def verify_mapped_netlist(root: Path, out: Path, top: str, library: str):
    """Inductive mapping check; assumes state alignment, not a reset-sequence proof."""
    relative = out.relative_to(root).as_posix()
    script = f"""read_json {relative}/premap.json
hierarchy -top {top}
rename {top} gold
design -stash reference
read_liberty {library}
read_verilog {relative}/bog.v
hierarchy -top {top}
proc
flatten
opt
rename {top} gate
design -copy-from reference -as gold gold
equiv_make gold gate equiv
hierarchy -top equiv
clk2fflogic
opt_clean
equiv_simple
equiv_induct -seq 4
equiv_status -assert
"""
    (out / "equivalence.ys").write_text(script)
    status = "passed"
    try:
        container(root, f"yosys -s {relative}/equivalence.ys", out / "equivalence.log")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        status = "unproven"
    result = {
        "status": status,
        "scope": "mapped BOG versus premap elaboration; not original RTL frontend equivalence",
        "proof_semantics": "inductive equivalence after state alignment; not reset-sequence reachability",
    }
    (out / "equivalence.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
