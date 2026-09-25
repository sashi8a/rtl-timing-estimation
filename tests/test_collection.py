import json
import subprocess
import time

import pytest

from rtl_timing.collection import error_status, run_collection
from rtl_timing.provenance import input_signature, reusable, seal_artifact
from rtl_timing.runtime import DeadlineExceeded, stage_timeout


def test_reuse_rejects_changed_inputs_outputs_and_incomplete_runs(tmp_path):
    signature = {"input_key": "first", "inputs": {}}
    output = tmp_path / "summary.json"
    output.write_text('{"status":"complete"}')
    assert not reusable(tmp_path, signature)
    seal_artifact(tmp_path, signature)
    assert reusable(tmp_path, signature)
    assert not reusable(tmp_path, {"input_key": "different"})
    output.write_text('{"status":"tampered"}')
    assert not reusable(tmp_path, signature)
    output.unlink()
    assert not reusable(tmp_path, signature)


def test_deadline_limits_stage_and_failure_status(monkeypatch):
    monkeypatch.setenv("RTL_TIMING_DEADLINE", str(time.time() + 3))
    assert 0 < stage_timeout() <= 3
    monkeypatch.setenv("RTL_TIMING_DEADLINE", str(time.time() - 1))
    with pytest.raises(DeadlineExceeded):
        stage_timeout()
    assert error_status(DeadlineExceeded()) == "timeout"
    assert error_status(subprocess.TimeoutExpired("yosys", 1)) == "timeout"
    assert error_status(ValueError()) == "failed"


def test_constraint_change_invalidates_feature_reuse(tmp_path):
    for directory in (
        "configs",
        "data/manifests",
        "data/raw/a",
        "data/libraries",
        "src/rtl_timing",
    ):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    (tmp_path / "configs/task1.json").write_text('{"bog_library_variant":"upstream"}')
    (tmp_path / "configs/eda.json").write_text("{}")
    for name in ("uv.lock", "pyproject.toml", ".python-version"):
        (tmp_path / name).write_text("locked environment")
    (tmp_path / "data/manifests/designs.json").write_text('{"designs":[{"id":"a"}]}')
    (tmp_path / "data/libraries/nangate45_aig.lib").write_text("library(x) {}")
    for module in ("eda", "graph", "libraries", "runtime", "provenance", "features"):
        (tmp_path / f"src/rtl_timing/{module}.py").write_text("# source snapshot")
    sdc = tmp_path / "data/raw/a/generated.sdc"
    sdc.write_text("create_clock -period 10")
    before = input_signature(tmp_path, "a", "features", "aig")
    output = tmp_path / "result"
    output.mkdir()
    (output / "summary.json").write_text("{}")
    seal_artifact(output, before)
    assert reusable(output, before)
    sdc.write_text("create_clock -period 20")
    assert not reusable(output, input_signature(tmp_path, "a", "features", "aig"))
    sdc.write_text("create_clock -period 10")
    assert reusable(output, input_signature(tmp_path, "a", "features", "aig"))
    (tmp_path / "uv.lock").write_text("changed dependencies")
    assert not reusable(output, input_signature(tmp_path, "a", "features", "aig"))


def test_collection_reports_failures_without_overwriting_existing_artifacts(
    tmp_path, monkeypatch
):
    import rtl_timing.collection as module

    (tmp_path / "configs").mkdir()
    (tmp_path / "data/manifests").mkdir(parents=True)
    (tmp_path / "configs/task1.json").write_text('{"representations":["sog"]}')
    (tmp_path / "data/manifests/designs.json").write_text(
        '{"designs":[{"id":"a"},{"id":"b"}]}'
    )
    monkeypatch.setattr(module, "bog_library", lambda *args: None)
    monkeypatch.setattr(module, "library_variant", lambda *args: "upstream")
    monkeypatch.setattr(module, "set_deadline", lambda minutes: time.time() + 60)
    monkeypatch.setattr(module, "stage_timeout", lambda: 60)
    monkeypatch.setattr(
        module, "input_signature", lambda *args: {"input_key": "new", "inputs": {}}
    )
    monkeypatch.setattr(
        module, "generate", lambda *args: (_ for _ in ()).throw(ValueError("bad graph"))
    )
    old = tmp_path / "data/processed/a/sog"
    old.mkdir(parents=True)
    (old / "old.txt").write_text("retain me")
    result = run_collection(tmp_path, workers=2)
    assert len(result["records"]) == 2
    assert all(r["status"] == "failed" for r in result["records"])
    assert any(
        p.read_text() == "retain me"
        for p in (tmp_path / "data/archive").rglob("old.txt")
    )
    status = next((tmp_path / "data/collection_runs").glob("*.json"))
    assert json.loads(status.read_text())["records"] == result["records"]
    with pytest.raises(ValueError, match="workers"):
        run_collection(tmp_path, workers=5)
