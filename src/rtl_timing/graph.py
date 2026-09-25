"""Structural BOG features; independent of target labels and STA report formats."""

import hashlib
import json
import random
from pathlib import Path

import networkx as nx

OPERATORS = {
    "AND2_X1": "and",
    "OR2_X1": "or",
    "INV_X1": "not",
    "XOR2_X1": "xor",
    "MUX2_X1": "mux",
    "BUF_X1": "buf",
}
ALLOWED = {
    "sog": {"and", "or", "not", "xor", "mux", "buf"},
    "aig": {"and", "not", "buf"},
    "aimg": {"and", "not", "mux", "buf"},
    "xag": {"and", "not", "xor", "buf"},
}


def is_register(cell):
    return cell["type"].startswith(("DFF", "SDFF"))


class Bog:
    def __init__(self, module: dict, representation: str, allowed_cell_types=None):
        self.module = module
        self.cells = {
            name: cell
            for name, cell in module["cells"].items()
            if cell["type"] != "$scopeinfo"
        }
        self.representation = representation
        self.drivers = {}
        self.aliases = {}
        self.inputs = {}
        for name, net in module["netnames"].items():
            offset = net.get("offset", 0)
            width = len(net["bits"])
            for index, bit in enumerate(net["bits"]):
                if isinstance(bit, int) and not net.get("hide_name", 0):
                    bit_index = offset + (
                        width - 1 - index if net.get("upto", 0) else index
                    )
                    self.aliases.setdefault(bit, []).append(f"{name}[{bit_index}]")
        for name, port in module["ports"].items():
            if port["direction"] == "input":
                for index, bit in enumerate(port["bits"]):
                    self.inputs[bit] = f"{name}[{index}]"
        for name, cell in self.cells.items():
            if not is_register(cell) and (
                cell["type"] not in allowed_cell_types
                if allowed_cell_types is not None
                else OPERATORS.get(cell["type"]) not in ALLOWED[representation]
            ):
                raise ValueError(f"Unsupported cell: {name} {cell['type']}")
            for port, direction in cell["port_directions"].items():
                if direction == "output":
                    for bit in cell["connections"][port]:
                        if bit in self.drivers:
                            raise ValueError(f"Multiple drivers for bit {bit}")
                        self.drivers[bit] = (name, port)
        self.dag = nx.DiGraph()
        for name, cell in self.cells.items():
            if not is_register(cell):
                self.dag.add_node(name)
                for bit in self.input_bits(cell):
                    driver = self.drivers.get(bit)
                    if driver and not is_register(self.cells[driver[0]]):
                        self.dag.add_edge(driver[0], name)
        if not nx.is_directed_acyclic_graph(self.dag):
            raise ValueError("Combinational loop in BOG")

    @staticmethod
    def input_bits(cell):
        return [
            bit
            for port, direction in cell["port_directions"].items()
            if direction == "input"
            for bit in cell["connections"][port]
        ]

    def endpoints(self):
        for name, cell in sorted(self.cells.items()):
            if is_register(cell):
                q = cell["connections"].get("Q", [])
                d = cell["connections"].get("D", [])
                if len(q) != 1 or len(d) != 1:
                    raise ValueError(f"Expected single-bit D/Q cell: {name}")
                aliases = sorted(self.aliases.get(q[0], []))
                yield {
                    "cell": name,
                    "d_bit": d[0],
                    "q_bit": q[0],
                    "aliases": aliases,
                    "endpoint_id": aliases[0] if aliases else None,
                }

    def cone(self, bit):
        registers, inputs, operators, seen = set(), set(), set(), set()
        stack = [bit]
        while stack:
            bit = stack.pop()
            if bit in seen:
                continue
            seen.add(bit)
            driver = self.drivers.get(bit)
            if driver:
                name, _ = driver
                cell = self.cells[name]
                if is_register(cell):
                    registers.add(name)
                else:
                    operators.add(name)
                    stack.extend(self.input_bits(cell))
            elif bit in self.inputs:
                inputs.add(self.inputs[bit])
        return registers, inputs, operators

    def sample_paths(self, endpoint, seed=42, cap=32):
        """Topology candidates only. Timing-arc validation is a separate stage."""
        registers, _, _ = self.cone(endpoint["d_bit"])
        requested = min(cap, len(registers))
        digest = hashlib.sha256(
            f"{seed}:{endpoint['cell']}:{self.representation}".encode()
        ).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        paths = {}
        for _ in range(max(100, requested * 50)):
            if len(paths) >= requested:
                break
            bit = endpoint["d_bit"]
            backwards = []
            while bit in self.drivers:
                name, port = self.drivers[bit]
                cell = self.cells[name]
                if is_register(cell):
                    path = [(name, port)] + list(reversed(backwards))
                    paths[tuple(path)] = path
                    break
                candidates = [
                    (p, b)
                    for p, direction in sorted(cell["port_directions"].items())
                    if direction == "input"
                    for b in cell["connections"][p]
                    if isinstance(b, int)
                ]
                if not candidates:
                    break
                input_port, bit = rng.choice(candidates)
                backwards.append((name, input_port))
        return requested, list(paths.values())

    def summary(self):
        registers = list(self.endpoints())
        depth = {}
        for node in nx.topological_sort(self.dag):
            depth[node] = 1 + max(
                (depth[p] for p in self.dag.predecessors(node)), default=0
            )
        return {
            "register_bits": len(registers),
            "combinational_operators": len(self.dag),
            "total_cells": len(self.cells),
            "max_combinational_depth": max(depth.values(), default=0),
            "endpoints_without_alias": sum(e["endpoint_id"] is None for e in registers),
            "net_count": len(
                {
                    bit
                    for net in self.module["netnames"].values()
                    for bit in net["bits"]
                    if isinstance(bit, int)
                }
            ),
            "operator_counts": {
                op: sum(OPERATORS.get(c["type"]) == op for c in self.cells.values())
                for op in ("and", "or", "not", "xor", "mux", "buf")
            },
        }


def load_bog(path: Path, top: str, representation: str):
    return Bog(json.loads(path.read_text())["modules"][top], representation)
