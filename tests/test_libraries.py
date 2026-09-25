import json

import pytest

from rtl_timing.libraries import (
    bog_library,
    cell_blocks,
    extend_reset_cells,
    library_variant,
)


def test_reset_extension_changes_only_two_cells():
    original = 'library(x) {\n cell (AND2_X1) { pin(Z) { function : "A & B"; } }\n cell (DFFRS_X1) { ff(IQ,IQN) { next_state : "D"; } }\n}\n'
    full = 'library(x) {\n cell (DFFR_X1) { ff(IQ,IQN) { clear : "!RN"; } }\n cell (DFFS_X1) { ff(IQ,IQN) { preset : "!SN"; } }\n cell (NAND2_X1) { pin(Z) { function : "!(A&B)"; } }\n}\n'
    result = cell_blocks(extend_reset_cells(original, full))
    assert set(result) == {"AND2_X1", "DFFRS_X1", "DFFR_X1", "DFFS_X1"}
    assert all(result[k] == v for k, v in cell_blocks(original).items())


def test_library_variant_rejects_unknown(tmp_path):
    (tmp_path / "configs").mkdir()
    p = tmp_path / "configs/task1.json"
    p.write_text(json.dumps({"bog_library_variant": "unsafe"}))
    with pytest.raises(ValueError, match="Unknown"):
        library_variant(tmp_path)
    p.write_text("{}")
    assert library_variant(tmp_path) == "upstream"


def test_selecting_reset_variant_preserves_upstream_file(tmp_path):
    (tmp_path / "configs").mkdir()
    libs = tmp_path / "data/libraries"
    libs.mkdir(parents=True)
    original = libs / "nangate45_aig.lib"
    text = "library(x) {\n cell (AND2_X1) { area : 1; }\n}\n"
    original.write_text(text)
    (libs / "nangate45.lib").write_text(
        "library(x) {\n cell (DFFR_X1) { area : 2; }\n cell (DFFS_X1) { area : 3; }\n}\n"
    )
    config = tmp_path / "configs/task1.json"
    config.write_text('{"bog_library_variant":"upstream"}')
    assert bog_library(tmp_path, "aig") == original
    config.write_text('{"bog_library_variant":"reset_v1"}')
    selected = bog_library(tmp_path, "aig")
    assert selected == libs / "reset_v1/nangate45_aig.lib"
    assert original.read_text() == text
    assert set(cell_blocks(selected.read_text())) == {"AND2_X1", "DFFR_X1", "DFFS_X1"}
