import copy
import os
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import pandas as pd
import pytest
import torch
from common import (
    checked_hashes,
    code_hashes,
    digest,
    identity,
    read,
    write_json,
    write_npz,
)
from metrics import evaluate
from neural import (
    PathModel,
    epoch_order,
    optimizer_for,
    pool,
    temperature,
    training_epoch,
)

from data import assign_split, balanced_weights, load, neural_scaler


def test_family_split_and_identity():
    r = pd.DataFrame(
        {
            "family": ["a", "a", "b"],
            "design_id": ["x", "y", "z"],
            "target_endpoint_id": ["q", "q", "q"],
        }
    )
    assert assign_split(r, {"train": ["a"], "test": ["b"]}).tolist() == [
        "train",
        "train",
        "test",
    ]
    with pytest.raises(ValueError, match="overlaps"):
        assign_split(r, {"train": ["a"], "test": ["a", "b"]})
    with pytest.raises(ValueError, match="Duplicate"):
        assign_split(pd.concat([r, r.iloc[:1]]), {"train": ["a"], "test": ["b"]})


def test_balancing_hierarchy():
    r = pd.DataFrame(
        {"family": ["a"] * 5 + ["b"] * 2, "design_id": ["x"] * 4 + ["y"] + ["z"] * 2}
    )
    r["w"] = balanced_weights(r)
    assert r.w.mean() == pytest.approx(1)
    assert r.groupby("family").w.sum().tolist() == pytest.approx([3.5, 3.5])
    assert r.groupby("design_id").w.sum().tolist() == pytest.approx([1.75, 1.75, 3.5])


def test_scaler_train_only_equal_endpoint_weights_and_masks():
    x = np.zeros((3, 4, 3, 2))
    mask = np.zeros((3, 4, 3), dtype=bool)
    mask[0, :, :1] = True
    mask[1:, :, :] = True
    x[0, :, 0, 0] = 2
    x[1, :, :, 0] = 4
    x[2, :, :, 0] = 10000
    result, scaler = neural_scaler(x, mask, np.array([True, True, False]))
    assert np.asarray(scaler["mean"])[:, 0].tolist() == pytest.approx([3] * 4)
    assert scaler["keep"] == [True, False]
    assert result.shape[-1] == 5
    assert (result[~mask] == 0).all()
    x[2] *= 100
    _, other = neural_scaler(x, mask, np.array([True, True, False]))
    assert scaler == other


def test_pooling_bias_padding_cardinality_and_gradients():
    x = torch.tensor(
        [[1.0, 0.0, 999.0], [2.0, 999.0, 999.0]],
        dtype=torch.float64,
        requires_grad=True,
    )
    mask = torch.tensor([[True, True, False], [True, False, False]])
    smooth = pool(x, mask, 0.1)
    hard = pool(x, mask)
    assert smooth[0].item() == pytest.approx(0.9306898218)
    assert smooth[1].item() == 2
    assert torch.all(smooth <= hard)
    assert torch.all(smooth >= hard - 0.1 * mask.sum(-1).log())
    smooth.sum().backward()
    assert (x.grad[~mask] == 0).all()
    assert x.grad[0, 1] > 0
    assert torch.allclose(pool(x, mask, 1e-6), hard, atol=2e-6)
    assert torch.allclose(pool(x[:, [1, 0, 2]], mask[:, [1, 0, 2]], 0.1), smooth)
    assert torch.allclose(pool(x.repeat(1, 2), mask.repeat(1, 2), 0.1), smooth)
    with pytest.raises(ValueError, match="Empty"):
        pool(x, torch.zeros_like(mask))


def test_equal_mixing_and_paired_initialization():
    torch.manual_seed(11)
    a = PathModel(6, [8, 4], False)
    torch.manual_seed(11)
    b = PathModel(6, [8, 4], True)
    x, mask = torch.randn(5, 4, 3, 6), torch.ones(5, 4, 3, dtype=torch.bool)
    assert torch.equal(a(x, mask), b(x, mask))
    assert torch.equal(b.logits.softmax(0), torch.full((4,), 0.25))
    _, views = a(x, mask, return_views=True)
    assert torch.allclose(a(x, mask), views.mean(-1))
    assert torch.equal(epoch_order(30, 11, 1), epoch_order(30, 11, 1))
    assert not torch.equal(epoch_order(30, 11, 1), epoch_order(30, 11, 2))


def test_metrics_design_macro_is_not_pooled():
    r = pd.DataFrame(
        {"design_id": ["a", "b", "b", "b"], "family": ["f", "g", "g", "g"]}
    )
    out = evaluate(r, np.array([1.0, 2.0, 2.0, 2.0]), np.array([5.0, 2.0, 2.0, 2.0]))
    assert out["macro_design_mae_ns"] == 2
    assert out["pooled"]["mae_ns"] == 1
    assert out["designs"]["b"]["pearson"] is None
    assert out["high_arrival_tail"]["b"]["n"] == 3


def test_stale_input_rejected(tmp_path):
    p = tmp_path / "input"
    p.write_text("original")
    hashes = {"input": digest(p)}
    checked_hashes(tmp_path, hashes)
    p.write_text("changed")
    with pytest.raises(ValueError, match="Stale"):
        checked_hashes(tmp_path, hashes)


@pytest.mark.parametrize("name", ["N0", "N1", "N2"])
def test_cuda_training_smoke(name):
    if not torch.cuda.is_available():
        pytest.skip("CUDA test requires the GPU server")
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(11)
    model = PathModel(6, [8, 4], name == "N2").cuda()
    cfg = {
        "learning_rate": 0.001,
        "weight_decay": 0.0001,
        "batch_size": 4,
        "gradient_clip": 1.0,
        "smooth_epochs": 2,
        "temperature_start": 0.1,
        "temperature_end": 0.005,
    }
    optimizer = optimizer_for(model, cfg)
    x, mask, y = (
        torch.randn(8, 4, 3, 6, device="cuda"),
        torch.ones(8, 4, 3, dtype=torch.bool, device="cuda"),
        torch.ones(8, device="cuda"),
    )
    for epoch in [1, 2, 3]:
        loss, _, _ = training_epoch(model, optimizer, x, mask, y, 11, epoch, cfg, name)
        assert np.isfinite(loss)
    assert temperature(cfg, name, 3) is None


def toy_run(path):
    from common import ROOT

    cfg = copy.deepcopy(read(ROOT / "modeling/config.json"))
    cfg["neural"].update(
        epochs=3, smooth_epochs=2, candidate_epochs=[2, 3], hidden=[8, 4], batch_size=4
    )
    rng = np.random.default_rng(1)
    x = rng.normal(size=(16, 4, 3, 6)).astype("float32")
    a = {
        "neural": x,
        "mask": np.ones(x.shape[:3], dtype=bool),
        "y": rng.uniform(0.1, 1.0, 16),
        "tree": rng.normal(size=(16, 4)),
        "weights": np.ones(16),
        "sog": np.ones(16),
    }
    p = path / "prepared"
    p.mkdir(parents=True)
    write_npz(p / "arrays.npz", **a)
    records = pd.DataFrame(
        {
            "design_id": ["train"] * 8 + ["v1"] * 2 + ["v2"] * 2 + ["test"] * 4,
            "family": ["f"] * 8 + ["g"] * 4 + ["h"] * 4,
            "target_endpoint_id": [f"q{i}" for i in range(16)],
            "target_cell": [f"q{i}" for i in range(16)],
            "partition": ["train"] * 8 + ["validation"] * 4 + ["test"] * 4,
        }
    )
    records.to_parquet(p / "records.parquet", index=False)
    frozen = {
        "config": cfg,
        "code": code_hashes(),
        "inputs": {},
        "target_scale_ns": 0.5,
        "outputs": {n: digest(p / n) for n in ["arrays.npz", "records.parquet"]},
    }
    frozen["signature"] = identity(frozen)
    write_json(p / "manifest.json", frozen)


def test_full_runner_resume_matches_uninterrupted(tmp_path, monkeypatch):
    import train

    straight, resumed = tmp_path / "straight", tmp_path / "resumed"
    toy_run(straight)
    toy_run(resumed)
    train.run_model(straight, "N2", 11, "cpu")
    original = train.write_json

    def stop_after_first_checkpoint(path, value):
        if Path(path).name == "status.json" and value.get("epoch") == 1:
            raise RuntimeError("simulated interruption")
        original(path, value)

    monkeypatch.setattr(train, "write_json", stop_after_first_checkpoint)
    with pytest.raises(RuntimeError, match="simulated"):
        train.run_model(resumed, "N2", 11, "cpu")
    monkeypatch.setattr(train, "write_json", original)
    train.run_model(resumed, "N2", 11, "cpu")
    a = torch.load(straight / "models/N2-seed11/selected.pt", weights_only=False)
    b = torch.load(resumed / "models/N2-seed11/selected.pt", weights_only=False)
    assert a["epoch"] == b["epoch"]
    assert all(torch.equal(a["model"][k], b["model"][k]) for k in a["model"])
    assert read(straight / "models/N2-seed11/metrics.json") == read(
        resumed / "models/N2-seed11/metrics.json"
    )
    train.run_model(resumed, "N2", 11, "cpu")  # Verified completion is safely skipped.
    checkpoint = resumed / "models/N2-seed11/selected.pt"
    checkpoint.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="Stale or damaged"):
        train.run_model(resumed, "N2", 11, "cpu")


def test_prepared_output_integrity(tmp_path):
    toy_run(tmp_path)
    load(tmp_path)
    (tmp_path / "prepared/arrays.npz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Stale or damaged"):
        load(tmp_path)


def test_queue_records_failures(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import run

    monkeypatch.setattr(
        run.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=7)
    )
    with pytest.raises(RuntimeError, match="exited 7"):
        run.launch_queue(tmp_path, [("T0", 0)], "test")
    files = list((tmp_path / "failures").glob("*.json"))
    assert len(files) == 1
    assert read(files[0])["returncode"] == 7


def test_empty_statistics_encoding_is_narrow():
    from data import OPS, PATH, encode_paths

    frame = pd.DataFrame([{name: 0.0 for name in PATH[:-1]}])
    frame["startpoint_type"] = "primary_input"
    for kind in ("fanout", "capacitance_ff"):
        for stat in ("sum", "mean", "std"):
            frame[f"{kind}_{stat}"] = np.nan
    result = encode_paths(frame)
    assert np.isfinite(result).all() and result[0, -1] == 1
    frame["path_depth"] = 1
    frame[OPS[0]] = 1
    with pytest.raises(ValueError, match="nonempty"):
        encode_paths(frame)


def test_curve_exports(tmp_path):
    from curves import export_curves

    metrics = {
        "macro_design_mae_ns": 0.5,
        "pooled": {"mae_ns": 0.4, "rmse_ns": 0.6},
        "designs": {"d": {"mae_ns": 0.5}},
    }
    write_json(
        tmp_path / "models/N0-seed11/history.json",
        [
            {
                "epoch": 1,
                "training_hard": metrics,
                "validation_hard": metrics,
                "representation_weights": [0.25] * 4,
                "batches": [
                    {"batch": 0, "loss_scaled": 0.3, "gradient_norm_before_clip": 0.2}
                ],
            }
        ],
    )
    export_curves(tmp_path)
    curve = pd.read_csv(tmp_path / "results/learning_curves.csv")
    assert curve.iloc[0].validation_macro_design_mae_ns == 0.5
    assert len(pd.read_csv(tmp_path / "results/per_design_curves.csv")) == 2
    assert len(pd.read_csv(tmp_path / "results/batch_diagnostics.csv")) == 1
