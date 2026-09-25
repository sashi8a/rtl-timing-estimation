from pathlib import Path

import pandas as pd
import pytest

from rtl_timing.labels import match_aliases, parse_label_report, target_library


def test_target_library_retains_general_gates_and_excludes_latches():
    text = 'library(x) {\n cell (NAND2_X1) { pin(Y) { function : "!(A & B)"; } }\n cell (DLL_X1) { latch(IQ,IQN) { data_in : "D"; } }\n cell (DFF_X1) { ff(IQ,IQN) { next_state : "D"; } }\n}\n'
    lib, keep, drop = target_library(text)
    assert keep == ["NAND2_X1", "DFF_X1"] and drop == ["DLL_X1"]
    assert "DLL_X1" not in lib and lib.count("{") == lib.count("}")


def test_alias_matching_rejects_ambiguity_and_register_merges():
    features = pd.DataFrame(
        {
            "endpoint_cell": ["a", "b", "c", "d"],
            "endpoint_id": ["x", "y", "z", "w"],
            "aliases": [["x"], ["y"], ["z"], ["missing"]],
        }
    )
    targets = pd.DataFrame({"aliases": [["x", "y"], ["z"], ["z"]]})
    assert match_aliases(features, targets).mapping_status.tolist() == [
        "ambiguous",
        "ambiguous",
        "ambiguous",
        "unmatched",
    ]
    assert match_aliases(features.iloc[:1], targets).mapping_status.tolist() == [
        "matched"
    ]


def test_label_parser_checks_pin_and_report_arithmetic(tmp_path: Path):
    path = tmp_path / "path.rpt"
    text = """Startpoint: input_data
Endpoint: reg
 0.0 0.0 clock clk (rise edge)
 0.0 0.0 clock network delay (ideal)
 0.01 0.1 0.1 ^ input_data (in)
 1 2.0 0.02 0.2 0.3 ^ a/Y (NAND2_X1)
 0.02 0.0 0.3 ^ reg/D (DFF_X1)
 0.3 data arrival time
"""
    path.write_text(text)
    result = parse_label_report(path, "reg", {"a": {}, "reg": {"type": "DFF_X1"}})
    assert result["arrival_ns"] == pytest.approx(0.3)
    assert result["startpoint_type"] == "primary_input"
    with pytest.raises(ValueError, match="Wrong endpoint"):
        parse_label_report(path, "other", {})
    path.write_text(text.replace("0.2 0.3", "0.7 0.3"))
    with pytest.raises(ValueError, match="increments"):
        parse_label_report(path, "reg", {"a": {}, "reg": {"type": "DFF_X1"}})


def test_direct_arrival_uses_max_not_min_or_wrong_transition():
    from rtl_timing.labels import parse_direct_arrivals

    assert parse_direct_arrivals("(core_clock ^) r 0.1:0.7 f 0.2:0.9\n") == {
        "rise": 0.7,
        "fall": 0.9,
    }
    with pytest.raises(ValueError, match="format"):
        parse_direct_arrivals("unexpected format")
