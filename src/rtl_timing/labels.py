"""Independent post-synthesis arrival labels and explicit feature/target joins."""

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .eda import container, normalize_mapped_verilog, verify_mapped_netlist
from .graph import Bog, is_register

CELL_PATTERN = re.compile(
    r"^(?:AND\d+|OR\d+|NAND\d+|NOR\d+|AOI\d+|OAI\d+|XOR\d+|XNOR\d+|MUX\d+|BUF|INV|DFF|DFFR|DFFS|DFFRS)_X\d+$"
)
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def target_library(text):
    """Keep ordinary combinational gates and DFFs; preserve original cell timing."""
    selected, excluded, pieces, previous = [], [], [], 0
    for match in re.finditer(r"^\s*cell\s*\(\s*(\w+)\s*\)\s*\{", text, re.MULTILINE):
        start = text.index("{", match.start())
        depth, quoted, escaped = 1, False, False
        end = start + 1
        while depth and end < len(text):
            c = text[end]
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
            end += 1
        if depth:
            raise ValueError("Unbalanced Liberty cell")
        name = match.group(1)
        pieces.append(text[previous : match.start()])
        if CELL_PATTERN.fullmatch(name):
            pieces.append(text[match.start() : end])
            selected.append(name)
        else:
            excluded.append(name)
        previous = end
    if not selected:
        raise ValueError("No target cells selected")
    pieces.append(text[previous:])
    return "".join(pieces), selected, excluded


def parse_label_report(path, endpoint_cell, cells):
    text = path.read_text()
    if "Startpoint:" not in text:
        if "No paths found" not in text:
            raise ValueError(f"Unexpected empty/error timing report: {path}")
        return None
    endpoint = re.search(r"^Endpoint: (\S+)", text, re.MULTILINE)
    if not endpoint or endpoint.group(1) != endpoint_cell:
        raise ValueError(f"Wrong endpoint in {path}")
    startpoint = re.search(r"^Startpoint: (\S+)", text, re.MULTILINE).group(1)
    pins, final_pin_arrival = [], None
    arrival, increments = None, []
    for line in text.splitlines():
        if "data arrival time" in line:
            arrival = float(line.split()[0])
            break
        # Every timing-table row has at least delay and accumulated time columns.
        row = re.match(rf"^\s*((?:{NUMBER}\s+){{2,5}})(.*)$", line)
        if not row:
            continue
        nums = [float(v) for v in row.group(1).split()]
        increments.append(nums[-2])
        pin = re.match(r"[\^v]\s+(\S+)\s+\(([^)]+)\)", row.group(2))
        if pin and pin.group(2) not in {"in", "out"}:
            name = pin.group(1)
            if name.rsplit("/", 1)[0] not in cells:
                raise ValueError(f"Unknown path cell {name}")
            pins.append(name)
            final_pin_arrival = nums[-1]
    if arrival is None or not np.isfinite(arrival):
        raise ValueError(f"Invalid arrival in {path}")
    if not pins or pins[-1] != endpoint_cell + "/D":
        raise ValueError(f"Path does not end at requested D pin: {path}")
    if not np.isclose(arrival, final_pin_arrival, atol=1e-7, rtol=0):
        raise ValueError("Arrival differs from endpoint pin time")
    if not np.isclose(arrival, sum(increments), atol=1e-6, rtol=0):
        raise ValueError("Path delay increments do not sum to arrival")
    return {
        "arrival_ns": arrival,
        "startpoint": startpoint,
        "startpoint_type": "register"
        if startpoint in cells and is_register(cells[startpoint])
        else "primary_input",
        "pins": pins,
        "increment_sum_ns": sum(increments),
    }


def match_aliases(features, targets):
    """Unique, one-to-one matching; never pick the first ambiguous candidate."""
    reverse = {}
    for i, row in targets.iterrows():
        for alias in row.aliases:
            reverse.setdefault(alias, set()).add(i)
    matches = []
    for _, row in features.iterrows():
        candidates = set().union(*(reverse.get(a, set()) for a in row.aliases))
        matches.append(next(iter(candidates)) if len(candidates) == 1 else None)
    repeated = {i for i in matches if i is not None and matches.count(i) > 1}
    result = []
    for (_, row), target in zip(features.iterrows(), matches, strict=True):
        candidates = set().union(*(reverse.get(a, set()) for a in row.aliases))
        status = (
            "matched"
            if target is not None and target not in repeated
            else "ambiguous"
            if candidates
            else "unmatched"
        )
        result.append(
            {
                "endpoint_cell": row.endpoint_cell,
                "endpoint_id": row.endpoint_id,
                "mapping_status": status,
                "target_index": target if status == "matched" else None,
            }
        )
    return pd.DataFrame(result)


def parse_direct_arrivals(text):
    """Pinned OpenSTA reports (clock edge) r min:max f min:max."""
    values = {"rise": [], "fall": []}
    for line in text.splitlines():
        match = re.fullmatch(
            rf"\([^\n]+\) r ({NUMBER}):({NUMBER}) f ({NUMBER}):({NUMBER})", line.strip()
        )
        if not match:
            raise ValueError(f"Unexpected direct arrival format: {line}")
        values["rise"].append(float(match.group(2)))
        values["fall"].append(float(match.group(4)))
    return {e: max(v) if v else None for e, v in values.items()}


def generate_labels(root: Path, design_id: str):
    root = root.resolve()
    design = next(
        d
        for d in json.loads((root / "data/manifests/designs.json").read_text())[
            "designs"
        ]
        if d["id"] == design_id
    )
    out = root / "data/labels" / design_id
    out.mkdir(parents=True, exist_ok=True)
    for marker in ("summary.json", "equivalence.json"):
        (out / marker).unlink(missing_ok=True)
    relative = out.relative_to(root).as_posix()
    # Per-design library path prevents concurrent writers to a shared output.
    library = out / "target.lib"
    contents, selected, excluded = target_library(
        (root / "data/libraries/nangate45.lib").read_text()
    )
    library.write_text(contents)
    lib = library.relative_to(root).as_posix()
    sources = " ".join(
        f"data/raw/{design_id}/{Path(p).name}" for p in design["source_files"]
    )
    top = design["top"]
    script = f"""read_liberty -lib {lib}
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
dfflibmap -liberty {lib}
abc -liberty {lib}
clean
check -assert
write_verilog -norename -noattr -noexpr {relative}/bog.v
write_json {relative}/netlist.json
stat -top {top}
"""
    (out / "synthesis.ys").write_text(script)
    container(root, f"yosys -s {relative}/synthesis.ys", out / "synthesis.log")
    raw = (out / "bog.v").read_text()
    (out / "netlist.raw.v").write_text(raw)
    (out / "bog.v").write_text(normalize_mapped_verilog(raw))
    module = json.loads((out / "netlist.json").read_text())["modules"][top]
    graph = Bog(module, "target", allowed_cell_types=set(selected))
    endpoints = list(graph.endpoints())
    (out / "endpoints.json").write_text(json.dumps(endpoints, indent=2) + "\n")
    sdc = root / "data/raw" / design_id / Path(design["sdc"]).name
    tcl = f"""read_lef /OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty {lib}
read_verilog {relative}/bog.v
link_design {top}
read_sdc {sdc.relative_to(root).as_posix()}
report_units
check_setup -verbose
"""
    for i, ep in enumerate(endpoints):
        pin = ep["cell"] + "/D"
        if any(c in pin for c in "{}\n"):
            raise ValueError("Unsupported Tcl pin name")
        for edge in ("rise", "fall"):
            tcl += f"report_checks -to [get_pins {{{pin}}}] -path_delay max_{edge} -group_path_count 1 -endpoint_path_count 1 -format full -fields {{capacitance slew fanout input_pin net}} -digits 9 > {relative}/path_{i}_{edge}.rpt\n"
        # Unlike report_checks, report_arrival does not implement > redirection.
        tcl += f'puts "BEGIN_DIRECT_ARRIVAL_{i}"\nreport_arrival -digits 9 [get_pins {{{pin}}}]\nputs "END_DIRECT_ARRIVAL_{i}"\n'
    tcl += "exit\n"
    (out / "timing.tcl").write_text(tcl)
    container(root, f"openroad -exit {relative}/timing.tcl", out / "timing.log")
    log = (out / "timing.log").read_text()
    if "time 1ns" not in log or "capacitance 1fF" not in log:
        raise ValueError("Unexpected units")
    for i in range(len(endpoints)):
        direct = re.search(
            rf"BEGIN_DIRECT_ARRIVAL_{i}\n(.*?)END_DIRECT_ARRIVAL_{i}", log, re.DOTALL
        )
        if not direct:
            raise ValueError("Missing direct arrival query output")
        (out / f"arrival_{i}.rpt").write_text(direct.group(1))
    rows = []
    for i, ep in enumerate(endpoints):
        paths = {
            e: parse_label_report(out / f"path_{i}_{e}.rpt", ep["cell"], graph.cells)
            for e in ("rise", "fall")
        }
        valid = {e: p for e, p in paths.items() if p is not None}
        direct = parse_direct_arrivals((out / f"arrival_{i}.rpt").read_text())
        for edge, path in paths.items():
            if path is not None and (
                direct[edge] is None
                or not np.isclose(path["arrival_ns"], direct[edge], atol=1e-7, rtol=0)
            ):
                raise ValueError(
                    f"Direct arrival disagrees with path report: {ep['cell']} {edge}"
                )
        row = {
            "design_id": design_id,
            "target_cell": ep["cell"],
            "target_endpoint_id": ep["endpoint_id"],
            "aliases": ep["aliases"],
            "label_status": "timed" if valid else "no_timed_path",
            "arrival_ns": None,
            "direct_arrival_crosscheck": bool(valid),
        }
        row.update(
            {
                f"{e}_arrival_ns": p["arrival_ns"] if p else None
                for e, p in paths.items()
            }
        )
        if valid:
            edge = max(valid, key=lambda e: valid[e]["arrival_ns"])
            row.update(valid[edge])
            row.update(
                critical_edge=edge,
                report_path=f"{relative}/path_{i}_{edge}.rpt",
                direct_report_path=f"{relative}/arrival_{i}.rpt",
            )
        rows.append(row)
    labels = pd.DataFrame(rows)
    if not labels.target_cell.is_unique:
        raise ValueError("Duplicate target register cells")
    labels.to_parquet(out / "labels.parquet", index=False)
    proof = verify_mapped_netlist(root, out, top, lib)
    proof["scope"] = (
        "target mapped circuit versus its premap elaboration; not original RTL frontend equivalence"
    )
    (out / "equivalence.json").write_text(json.dumps(proof, indent=2) + "\n")
    feature_proofs = {
        rep: json.loads(
            (root / "data/processed" / design_id / rep / "equivalence.json").read_text()
        )["status"]
        for rep in ("sog", "aig", "aimg", "xag")
    }
    functional_gate = proof["status"] == "passed" and all(
        s == "passed" for s in feature_proofs.values()
    )
    joins, coverage = [], {}
    for rep in feature_proofs:
        feature_summary = json.loads(
            (root / "data/processed" / design_id / rep / "summary.json").read_text()
        )
        if feature_summary.get("sdc_sha256") != sha256(sdc):
            raise ValueError(
                f"Feature constraints missing or stale for {design_id}/{rep}; regenerate features"
            )
        features = pd.read_parquet(
            root / "data/processed" / design_id / rep / "endpoint_features.parquet"
        )
        mapping = match_aliases(features, labels)
        mapping["target_index"] = pd.array(mapping["target_index"], dtype="Int64")
        mapping["representation"] = rep
        mapping["design_id"] = design_id
        mapping = mapping.merge(
            labels[["target_cell", "arrival_ns", "label_status"]]
            .rename_axis("target_index")
            .reset_index(),
            on="target_index",
            how="left",
            validate="many_to_one",
        )
        mapping["training_eligible"] = (
            functional_gate
            & (mapping.mapping_status == "matched")
            & (mapping.label_status == "timed")
        )
        joins.append(mapping)
        coverage[rep] = mapping.mapping_status.value_counts().to_dict()
    joined = pd.concat(joins, ignore_index=True)
    joined.to_parquet(out / "feature_label_join.parquet", index=False)
    summary = {
        "design_id": design_id,
        "timing_stage": "post_synthesis_no_wire_parasitics",
        "register_bits": len(labels),
        "timed_register_bits": int((labels.label_status == "timed").sum()),
        "feature_mapping": coverage,
        "target_proof": proof,
        "feature_proofs": feature_proofs,
        "training_eligible_join_rows": int(joined.training_eligible.sum()),
        "sdc_sha256": sha256(sdc),
        "library_sha256": sha256(library),
        "source_library_sha256": sha256(root / "data/libraries/nangate45.lib"),
        "selected_cells": selected,
        "excluded_cells": excluded,
        "netlist_sha256": sha256(out / "netlist.json"),
        "units": {"time": "ns", "capacitance": "fF"},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
