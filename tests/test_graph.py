import pytest

from rtl_timing.graph import Bog


def cell(kind, inputs, outputs):
    return {
        "type": kind,
        "port_directions": {
            **{k: "input" for k in inputs},
            **{k: "output" for k in outputs},
        },
        "connections": {
            **{k: [v] for k, v in inputs.items()},
            **{k: [v] for k, v in outputs.items()},
        },
    }


def fixture():
    return {
        "ports": {"clk": {"direction": "input", "bits": [1]}},
        "netnames": {"source": {"bits": [2]}, "target": {"bits": [5]}},
        "cells": {
            "r0": cell("DFF_X1", {"D": 2, "CK": 1}, {"Q": 2}),
            "a": cell("AND2_X1", {"A1": 2, "A2": 2}, {"ZN": 3}),
            "i": cell("INV_X1", {"A": 3}, {"ZN": 4}),
            "r1": cell("DFF_X1", {"D": 4, "CK": 1}, {"Q": 5}),
        },
    }


def test_cone_counts_distinct_registers_and_depth():
    bog = Bog(fixture(), "aig")
    assert bog.cone(4) == ({"r0"}, set(), {"a", "i"})
    assert bog.summary()["max_combinational_depth"] == 2
    assert bog.summary()["register_bits"] == 2
    ep = list(bog.endpoints())[1]
    assert ep["endpoint_id"] == "target[0]"
    assert bog.sample_paths(ep) == bog.sample_paths(ep)
    requested, paths = bog.sample_paths(ep)
    assert requested == 1 and len(paths) == 1
    assert paths[0][0][0] == "r0"


def test_direct_register_path():
    m = fixture()
    m["cells"]["r1"]["connections"]["D"] = [2]
    bog = Bog(m, "aig")
    assert bog.cone(2) == ({"r0"}, set(), set())
    assert bog.sample_paths(list(bog.endpoints())[1])[1] == [[("r0", "Q")]]


def test_reject_combinational_loop():
    m = fixture()
    m["cells"]["a"]["connections"]["A1"] = [4]
    with pytest.raises(ValueError, match="loop"):
        Bog(m, "aig")


def test_operator_vocabulary_is_checked():
    m = fixture()
    m["cells"]["a"]["type"] = "XOR2_X1"
    with pytest.raises(ValueError, match="Unsupported"):
        Bog(m, "aig")


def test_missing_alias_and_primary_input_are_explicit():
    m = fixture()
    m["netnames"].pop("target")
    m["ports"]["data"] = {"direction": "input", "bits": [8]}
    m["cells"]["r1"]["connections"]["D"] = [8]
    bog = Bog(m, "aig")
    assert bog.summary()["endpoints_without_alias"] == 1
    assert bog.cone(8) == (set(), {"data[0]"}, set())
