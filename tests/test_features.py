from pathlib import Path

import pytest
from test_graph import fixture

from rtl_timing.features import parse_path, statistics
from rtl_timing.graph import Bog


def test_statistics_zero_and_empty():
    assert statistics([0, 2], "x") == {
        "x_sum": 2.0,
        "x_mean": 1.0,
        "x_variance": 1.0,
        "x_std": 1.0,
    }
    assert all(v is None for v in statistics([], "x").values())
    with pytest.raises(ValueError):
        statistics([float("nan")], "x")


def test_parse_uses_cells_not_report_line_count(tmp_path: Path):
    report = tmp_path / "path.rpt"
    report.write_text("""Startpoint: r0
Endpoint: r1
 0.0 0.0 0.0 ^ r0/CK (DFF_X1)
 2 3.0 0.1 0.2 0.2 ^ r0/Q (DFF_X1)
 0.1 0.0 0.2 ^ a/A1 (AND2_X1)
 1 2.0 0.2 0.3 0.5 ^ a/ZN (AND2_X1)
 0.2 0.0 0.5 ^ i/A (INV_X1)
 1 1.0 0.3 0.4 0.9 v i/ZN (INV_X1)
 0.3 0.0 0.9 v r1/D (DFF_X1)
 0.900000000 data arrival time
""")
    feature = parse_path(report, Bog(fixture(), "aig"))
    assert feature["bog_arrival_ns"] == 0.9
    assert feature["path_depth"] == 2
    assert feature["operator_and_count"] == 1
    assert feature["operator_not_count"] == 1
    assert feature["fanout_sum"] == 4
    assert feature["capacitance_ff_sum"] == 6
    assert feature["slew_ns_sum"] == pytest.approx(0.9)


def test_mapped_netlist_normalization_only_changes_declarations():
    from rtl_timing.eda import normalize_mapped_verilog

    text = "  wire signed [31:0] count;\n// wire signed is a comment\n  assign x = count[0];\n"
    assert (
        normalize_mapped_verilog(text)
        == "  wire [31:0] count;\n// wire signed is a comment\n  assign x = count[0];\n"
    )
