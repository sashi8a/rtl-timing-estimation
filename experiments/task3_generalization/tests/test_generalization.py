import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from common import completed, read, seal, write_json
from generalization_data import assign_folds, fit_preprocessing
from generalization_finish import (
    aggregate,
    depth_bin,
    freeze_models,
    jobs,
    validate_predictions,
)
from generalization_train import (
    ContextModel,
    paired_identity,
    restore,
    setup,
    state_digest,
    torch_save,
)
from neural import epoch_order, optimizer_for, pool, training_epoch
from raw_features import NUMERIC

CONFIG = read(Path(__file__).resolve().parents[1] / "config.json")


def fixture():
    rng = np.random.default_rng(7)
    records = pd.DataFrame(
        {
            "design_id": ["a", "a", "b", "c", "held", "held"],
            "family": ["f1", "f1", "f1", "f2", "held", "held"],
        }
    )
    raw = {
        "tree": rng.normal(size=(6, 3)),
        "neural": rng.normal(size=(6, 4, 3, 3)),
        "mask": np.ones((6, 4, 3), bool),
        "sog": np.arange(6.0),
    }
    raw["tree"][:4, 2] = 1
    raw["neural"][:4, :, :, 2] = 5
    return (
        raw,
        np.arange(1.0, 7),
        records,
        np.arange(6) < 4,
        {
            "tree": ["path.x", "design.x", "design.constant"],
            "neural": ["path.x", "design.x", "design.constant"],
        },
    )


def test_fold_coverage_and_exclusion():
    rows = []
    for pair, count in zip(CONFIG["folds"], CONFIG["eval_counts"], strict=True):
        for i in range(count):
            rows.append(
                {
                    "family": pair[i % 2],
                    "design_id": pair[i % 2],
                    "target_endpoint_id": str(i),
                }
            )
    records = pd.DataFrame(rows)
    folds = assign_folds(records, CONFIG)
    assert len(folds) == 1053
    for f in range(1, 5):
        assert set(records[folds == f].family).isdisjoint(records[folds != f].family)
    records.loc[0, "family"] = "uart"
    with pytest.raises(ValueError):
        assign_folds(records, CONFIG)
    bad = copy.deepcopy(CONFIG)
    bad["folds"][0][0] = bad["folds"][1][0]
    with pytest.raises(ValueError):
        assign_folds(pd.DataFrame(rows), bad)


def test_train_only_scaling_weights_and_namespaces():
    raw, y, records, train, schema = fixture()
    a, f, w = fit_preprocessing(raw, y, records, train, schema)
    changed = copy.deepcopy(raw)
    for key in ["tree", "neural", "sog"]:
        changed[key][~train] += 12345
    yy = y.copy()
    yy[~train] *= 1000
    aa, ff, ww = fit_preprocessing(changed, yy, records, train, schema)
    assert f == ff
    for key in a:
        np.testing.assert_array_equal(a[key][train], aa[key][train])
    np.testing.assert_array_equal(w, ww)
    np.testing.assert_allclose(w, [0.5, 0.5, 1, 2])
    np.testing.assert_allclose(
        f["scaler"]["mean"], raw["neural"][train].mean(axis=(0, 2))
    )
    assert f["target_scale_ns"] == 2.5 and f["context_indices"] == [1]
    assert len(NUMERIC) == len(set(NUMERIC)) == 31
    assert (
        "path.operator_and_count" in NUMERIC and "design.operator_and_count" in NUMERIC
    )
    # Identical fitted training inputs yield identical training updates despite changed held-out data.
    setup()
    cfg = CONFIG["neural"]

    def fit_once(arrays):
        torch.manual_seed(11)
        model = ContextModel(arrays["neural"].shape[-1], cfg["hidden"])
        opt = optimizer_for(model, cfg)
        training_epoch(
            model,
            opt,
            torch.tensor(arrays["neural"][train]),
            torch.tensor(arrays["mask"][train]),
            torch.tensor(
                arrays["y"][train] / f["target_scale_ns"], dtype=torch.float32
            ),
            11,
            1,
            cfg,
            "N1",
        )
        return state_digest(model)

    assert fit_once(a) == fit_once(aa)


def test_context_mask_initialization_and_pooling():
    setup()
    torch.manual_seed(11)
    full = ContextModel(9, [64, 32])
    torch.manual_seed(11)
    ablated = ContextModel(9, [64, 32], [2, 4])
    assert state_digest(full) == state_digest(ablated)
    x = torch.randn(7, 4, 3, 9)
    mask = torch.ones((7, 4, 3), dtype=torch.bool)
    mask[:, :, 2] = False
    changed = x.clone()
    changed[:, :, :, 2] = 1000
    changed[:, :, :, 4] = -999
    for tau in [None, 0.1]:
        torch.testing.assert_close(
            ablated(x, mask, tau), ablated(changed, mask, tau), rtol=0, atol=0
        )
        padded = x.clone()
        padded[:, :, 2] = 1e6
        torch.testing.assert_close(
            ablated(x, mask, tau), ablated(padded, mask, tau), rtol=0, atol=0
        )
    assert not torch.equal(ablated(x, mask), ablated(x + 1, mask))
    scores = torch.tensor([[[2.0, 100.0]]])
    m = torch.tensor([[[True, False]]])
    for tau in [None, 0.1]:
        torch.testing.assert_close(pool(scores, m, tau), torch.tensor([[2.0]]))
    assert paired_identity(9, CONFIG["neural"], 7, 11) == paired_identity(
        9, CONFIG["neural"], 7, 11
    )
    assert not torch.equal(epoch_order(7, 11, 1), epoch_order(7, 22, 1))


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_interruption_recovery_exact(tmp_path, device):
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("CUDA unavailable")
    setup()
    cfg = CONFIG["neural"]
    seed = 11
    torch.manual_seed(17)
    x = torch.randn(8, 4, 3, 9, device=device)
    mask = torch.ones((8, 4, 3), dtype=torch.bool, device=device)
    y = torch.rand(8, device=device)
    pair = paired_identity(9, cfg, 8, seed)
    torch.manual_seed(seed)
    model = ContextModel(9, cfg["hidden"]).to(device)
    opt = optimizer_for(model, cfg)
    training_epoch(model, opt, x, mask, y, seed, 1, cfg, "N1")
    saved = {
        "signature": "sig",
        "name": "N1",
        "seed": seed,
        "paired": pair,
        "epoch": 1,
        "history": [{"epoch": 1}],
        "model": model.state_dict(),
        "optimizer": opt.state_dict(),
        "rng_cpu": torch.get_rng_state(),
        "rng_cuda": torch.cuda.get_rng_state_all() if device == "cuda" else [],
    }
    torch_save(tmp_path / "latest.pt", saved)
    training_epoch(model, opt, x, mask, y, seed, 2, cfg, "N1")
    expected = state_digest(model)
    resumed = ContextModel(9, cfg["hidden"]).to(device)
    ropt = optimizer_for(resumed, cfg)
    saved = torch.load(tmp_path / "latest.pt", map_location=device, weights_only=False)
    hist, first = restore(saved, resumed, ropt, "sig", "N1", seed, pair, device)
    assert first == 2 and hist == [{"epoch": 1}]
    training_epoch(resumed, ropt, x, mask, y, seed, 2, cfg, "N1")
    assert state_digest(resumed) == expected
    with pytest.raises(ValueError, match="Stale"):
        restore(saved, resumed, ropt, "changed", "N1", seed, pair, device)


def test_aggregate_is_over_designs_not_folds():
    # Unequal fold sizes: one high-error design vs three zero-error designs.
    frame = pd.DataFrame(
        {
            "model": ["SOG"] * 4,
            "seed": [0] * 4,
            "evaluation_fold": [1, 2, 2, 2],
            "design_id": ["a", "b", "c", "d"],
            "family": ["a", "b", "c", "d"],
            "arrival_ns": [1.0, 1.0, 1.0, 1.0],
            "prediction_ns": [5.0, 1.0, 1.0, 1.0],
            "arrival_quartile": [1] * 4,
            "sog_depth_bin": ["0"] * 4,
            "target_launch_type": ["register"] * 4,
        },
        index=[10, 20, 30, 40],
    )
    metrics, tables = aggregate(frame)
    assert metrics["SOG-seed0"]["overall"]["macro_design_mae_ns"] == 1
    assert tables["seed_summary"].iloc[0].mean_macro_design_mae_ns == 1
    assert list(depth_bin(pd.Series([0, 1, 5, 6, 10, 11, 20, 21]))) == [
        "0",
        "1–5",
        "1–5",
        "6–10",
        "6–10",
        "11–20",
        "11–20",
        ">20",
    ]
    with pytest.raises(ValueError):
        validate_predictions(frame)


def test_freeze_gate_and_epoch_enforcement(tmp_path):
    m = {"config": CONFIG, "signature": "sig"}
    with pytest.raises(ValueError, match="Incomplete"):
        freeze_models(tmp_path, m)
    assert not (tmp_path / "model_freeze.json").exists()
    from generalization_train import directory

    for f, n, s in jobs(CONFIG):
        d = directory(tmp_path, f, n, s)
        d.mkdir(parents=True)
        details = {"epoch": 199, "paired": {"a": "b"}}
        write_json(d / "details.json", details)
        if n == "T1":
            (d / "model.joblib").write_bytes(b"x")
            files = ["model.joblib"]
        else:
            torch_save(d / "final.pt", {})
            files = ["final.pt"]
        seal(d, "sig", files + ["details.json"])
    with pytest.raises(ValueError, match="epoch 200"):
        freeze_models(tmp_path, m)
    assert not (tmp_path / "model_freeze.json").exists()


def test_seal_rejects_stale_and_queue_records_failures(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import generalization_run as runner

    monkeypatch.setattr(
        runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    errors = runner.queue(tmp_path, tmp_path, [(1, "T1", 0), (2, "T1", 0)])
    assert len(errors) == 2 and len(list((tmp_path / "failures").glob("*.json"))) == 2
    (tmp_path / "artifact").write_text("original")
    seal(tmp_path, "sig", ["artifact"])
    assert completed(tmp_path, "sig")
    with pytest.raises(ValueError):
        completed(tmp_path, "other")
    (tmp_path / "artifact").write_text("changed")
    with pytest.raises(ValueError):
        completed(tmp_path, "sig")


def test_worker_recovery_and_no_evaluation_access(tmp_path, monkeypatch):
    import generalization_train as worker

    raw, y, records, train, schema = fixture()
    arrays, fitted, weights = fit_preprocessing(raw, y, records, train, schema)
    arrays = {k: v[train] for k, v in arrays.items()}
    arrays["weights"] = weights
    frozen = {"signature": "toy", "config": CONFIG}

    def loader(run, fold, part):
        assert part == "train"
        return records[train], arrays, fitted, frozen

    monkeypatch.setattr(worker, "load_partition", loader)
    original = worker.torch_save

    def interrupt(path, value):
        original(path, value)
        if path.name == "latest.pt" and value["epoch"] == 3:
            raise RuntimeError("simulated interruption")

    monkeypatch.setattr(worker, "torch_save", interrupt)
    with pytest.raises(RuntimeError, match="interruption"):
        worker.run_model(tmp_path / "resumed", 1, "N1", 11, "cpu")
    monkeypatch.setattr(worker, "torch_save", original)
    worker.run_model(tmp_path / "resumed", 1, "N1", 11, "cpu")
    worker.run_model(tmp_path / "continuous", 1, "N1", 11, "cpu")
    a = worker.directory(tmp_path / "resumed", 1, "N1", 11)
    b = worker.directory(tmp_path / "continuous", 1, "N1", 11)
    aa = torch.load(a / "final.pt", weights_only=False)
    bb = torch.load(b / "final.pt", weights_only=False)
    assert aa["epoch"] == bb["epoch"] == 200
    for key in aa["model"]:
        torch.testing.assert_close(aa["model"][key], bb["model"][key], rtol=0, atol=0)
    assert completed(a, "toy") and len(read(a / "history.json")) == 200
    assert not any(
        "validation" in row or "evaluation" in row for row in read(a / "history.json")
    )
    worker.run_model(tmp_path / "resumed", 1, "N1", 11, "cpu")  # verified skip
