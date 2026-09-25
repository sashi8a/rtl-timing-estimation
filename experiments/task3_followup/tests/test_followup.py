import copy
from pathlib import Path
from types import SimpleNamespace

import calibration
import numpy as np
import pandas as pd
import pytest
import torch
from common import read, seal, write_json
from follow_finish import freeze_selections
from follow_model import SOGModel
from neural import PathModel, epoch_order
from train import state_digest


def test_calibration_known_affine_and_clipping():
    x = np.linspace(0, 10, 40)
    fit = calibration.fit(x, 1.4 * x + 0.2)
    assert fit["a"] == pytest.approx(1.4)
    assert fit["b_ns"] == pytest.approx(0.2)
    raw, clipped = calibration.prediction({"a": 1.0, "b_ns": -2.0}, [1.0, 3.0])
    assert raw.tolist() == [-1.0, 1.0]
    assert clipped.tolist() == [0.0, 1.0]


def test_calibration_constant_input_and_nonnegative_slope():
    c = calibration.fit(np.ones(5), np.array([1.0, 2.0, 3.0, 10.0, 20.0]))
    assert c["a"] + c["b_ns"] == pytest.approx(3.0)
    c = calibration.fit(np.arange(5.0), np.arange(5.0)[::-1])
    assert c["a"] >= 0


def test_calibration_invalid_inputs_and_solver_failure(monkeypatch):
    with pytest.raises(ValueError, match="Nonfinite"):
        calibration.fit([np.nan], [1.0])
    with pytest.raises(ValueError, match="shape"):
        calibration.fit([], [])
    monkeypatch.setattr(
        calibration,
        "linprog",
        lambda *a, **kw: SimpleNamespace(success=False, message="synthetic failure"),
    )
    with pytest.raises(ValueError, match="solver failed"):
        calibration.fit([1.0, 2.0], [1.0, 2.0])


def test_fit_ignores_validation_and_test_labels(tmp_path, monkeypatch):
    records = pd.DataFrame(
        {
            "design_id": ["train"] * 4 + ["val", "test"],
            "family": ["a"] * 4 + ["b", "c"],
            "partition": ["train"] * 4 + ["validation", "test"],
            "target_endpoint_id": list("abcdef"),
        }
    )
    arrays = {"sog": np.arange(6.0), "y": 2 * np.arange(6.0) + 1}
    monkeypatch.setattr(
        calibration, "load", lambda run: (records, arrays, {"signature": "test"})
    )
    calibration.run_calibration(tmp_path / "a")
    arrays["y"][4:] += 1e6
    calibration.run_calibration(tmp_path / "b")
    assert read(tmp_path / "a/models/C0/coefficients.json") == read(
        tmp_path / "b/models/C0/coefficients.json"
    )


def test_sog_forward_pairing_masks_and_padding():
    torch.manual_seed(11)
    base = PathModel(6, [8, 4], False)
    torch.manual_seed(11)
    sog = SOGModel(6, [8, 4])
    assert state_digest(sog) == state_digest(base)
    x = torch.randn(3, 1, 4, 6)
    mask = torch.tensor([[[True, True, False, False]]] * 3)
    for tau in [None, 0.1, 0.005]:
        _, views = base(x.expand(-1, 4, -1, -1), mask.expand(-1, 4, -1), tau, True)
        assert torch.equal(sog(x, mask, tau), views[:, 0])
        modified = x.clone()
        modified[~mask] = 1e5
        assert torch.equal(sog(x, mask, tau), sog(modified, mask, tau))
    assert torch.equal(epoch_order(716, 11, 1), epoch_order(716, 11, 1))
    with pytest.raises(ValueError, match="exactly one"):
        sog(x.expand(-1, 4, -1, -1), mask.expand(-1, 4, -1))


def test_evaluation_gate_and_stale_selections(tmp_path):
    with pytest.raises(ValueError, match="Unfinished"):
        freeze_selections(tmp_path, "sig", [11])
    assert not (tmp_path / "selection_freeze.json").exists()
    for name, artifact in [
        ("C0", "coefficients.json"),
        ("N1-SOG-seed11", "selected.pt"),
    ]:
        p = tmp_path / "models" / name
        write_json(p / artifact, {"example": True})
        seal(p, "sig", [artifact])
    freeze_selections(tmp_path, "sig", [11])
    (tmp_path / "models/C0/coefficients.json").write_text("changed")
    with pytest.raises(ValueError, match="Stale"):
        freeze_selections(tmp_path, "sig", [11])


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_interrupted_resume_is_identical(tmp_path, monkeypatch, device):
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("Requires GPU server")
    import follow_train
    from bootstrap import ROOT

    cfg = copy.deepcopy(read(ROOT / "modeling/config.json"))
    cfg["representations"] = ["sog"]
    cfg["neural"].update(
        hidden=[8, 4], epochs=3, smooth_epochs=2, candidate_epochs=[2, 3], batch_size=4
    )
    torch.manual_seed(11)
    initial = state_digest(PathModel(6, [8, 4], False))
    frozen = {
        "signature": "fixture",
        "config": cfg,
        "target_scale_ns": 0.5,
        "paired_initializations": {"11": initial},
    }
    rng = np.random.default_rng(1)
    arrays = {
        "neural": rng.normal(size=(12, 1, 3, 6)).astype("float32"),
        "mask": np.ones((12, 1, 3), dtype=bool),
        "y": rng.uniform(0.1, 1.0, 12),
    }
    records = pd.DataFrame(
        {
            "design_id": ["train"] * 8 + ["val"] * 4,
            "family": ["a"] * 8 + ["b"] * 4,
            "partition": ["train"] * 8 + ["validation"] * 4,
            "target_endpoint_id": [str(i) for i in range(12)],
        }
    )
    monkeypatch.setattr(follow_train, "load", lambda run: (records, arrays, frozen))
    straight, resumed = tmp_path / "straight", tmp_path / "resumed"
    follow_train.run_model(straight, "N1-SOG", 11, device)
    original = follow_train.write_json

    def interrupt(path, value):
        if Path(path).name == "status.json" and value.get("epoch") == 1:
            raise RuntimeError("simulated interruption")
        original(path, value)

    monkeypatch.setattr(follow_train, "write_json", interrupt)
    with pytest.raises(RuntimeError, match="simulated"):
        follow_train.run_model(resumed, "N1-SOG", 11, device)
    monkeypatch.setattr(follow_train, "write_json", original)
    follow_train.run_model(resumed, "N1-SOG", 11, device)
    a = torch.load(
        straight / "models/N1-SOG-seed11/selected.pt",
        map_location="cpu",
        weights_only=False,
    )
    b = torch.load(
        resumed / "models/N1-SOG-seed11/selected.pt",
        map_location="cpu",
        weights_only=False,
    )
    assert a["epoch"] == b["epoch"]
    assert all(torch.equal(a["model"][k], b["model"][k]) for k in a["model"])
    assert read(straight / "models/N1-SOG-seed11/metrics.json") == read(
        resumed / "models/N1-SOG-seed11/metrics.json"
    )
    assert not (resumed / "results").exists()  # Training does not evaluate test data.
