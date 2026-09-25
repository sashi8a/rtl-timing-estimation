"""Freeze all selections before exploratory test-set reuse."""

from pathlib import Path

import numpy as np
import pandas as pd
import torch
from calibration import prediction
from common import (
    atomic,
    checked_hashes,
    completed,
    digest,
    read,
    require,
    seal,
    write_json,
)
from follow_curves import export_curves
from follow_data import load
from follow_model import SOGModel
from metrics import evaluate, prediction_frame
from neural import predict
from train import setup


def freeze_selections(run, signature, seeds):
    run = Path(run)
    files = {}
    for name in ["C0"] + [f"N1-SOG-seed{s}" for s in seeds]:
        directory = run / "models" / name
        require(completed(directory, signature), f"Unfinished experiment: {name}")
        artifact = "coefficients.json" if name == "C0" else "selected.pt"
        for filename in ["complete.json", artifact]:
            key = str((directory / filename).relative_to(run))
            files[key] = digest(run / key)
    freeze = {
        "signature": signature,
        "files": files,
        "evaluation": "Exploratory follow-up; previously inspected test set; no further model selection",
    }
    path = run / "selection_freeze.json"
    if path.exists():
        require(read(path) == freeze, "Selections changed after freeze")
    else:
        write_json(path, freeze)
    checked_hashes(run, files)


def finish(run):
    run = Path(run)
    records, arrays, frozen = load(run, full_check=True)
    manifest = read(run / "manifest.json")
    signature, seeds = frozen["signature"], manifest["followup_config"]["seeds"]
    destination = run / "results"
    if completed(destination, signature):
        return
    freeze_selections(run, signature, seeds)
    setup()
    require(torch.cuda.is_available(), "GPU unavailable; refusing silent fallback")
    test = (records.partition == "test").to_numpy()
    base = Path(manifest["base_run"])
    original = read(base / "results/metrics.json")["test"]
    baseline_names = ["median", "SOG"] + [f"N1-seed{s}" for s in seeds]
    metrics = {name: original[name] for name in baseline_names}
    old_predictions = pd.read_parquet(base / "results/test_predictions.parquet")
    frames = [
        old_predictions[old_predictions.model.isin(["median", "SOG", "N1"])].copy()
    ]
    coefficients = read(run / "models/C0/coefficients.json")
    raw, pred = prediction(coefficients, arrays["sog"][test])
    metrics["C0"] = evaluate(records[test], arrays["y"][test], pred)
    calibration_raw = evaluate(records[test], arrays["y"][test], raw)
    frame = prediction_frame(records[test], arrays["y"][test], pred, "C0")
    frame["raw_prediction_ns"], frame["clipped_at_zero"] = raw, raw < 0
    frames.append(frame)
    for seed in seeds:
        name = f"N1-SOG-seed{seed}"
        saved = torch.load(
            run / "models" / name / "selected.pt",
            map_location="cuda",
            weights_only=False,
        )
        require(
            saved["signature"] == signature
            and saved["initial_mlp_sha256"]
            == manifest["paired_initializations"][str(seed)],
            "Selected model identity mismatch",
        )
        model = SOGModel(
            arrays["neural"].shape[-1], frozen["config"]["neural"]["hidden"]
        ).cuda()
        model.load_state_dict(saved["model"])
        pred = (
            predict(
                model,
                torch.tensor(arrays["neural"][test], device="cuda"),
                torch.tensor(arrays["mask"][test], device="cuda"),
            )
            * frozen["target_scale_ns"]
        )
        metrics[name] = evaluate(records[test], arrays["y"][test], pred)
        frames.append(
            prediction_frame(records[test], arrays["y"][test], pred, "N1-SOG", seed)
        )
    paired = [
        metrics[f"N1-SOG-seed{s}"]["macro_design_mae_ns"]
        - metrics[f"N1-seed{s}"]["macro_design_mae_ns"]
        for s in seeds
    ]
    per_design = {
        d: {
            str(s): metrics[f"N1-SOG-seed{s}"]["designs"][d]["mae_ns"]
            - metrics[f"N1-seed{s}"]["designs"][d]["mae_ns"]
            for s in seeds
        }
        for d in records[test].design_id.unique()
    }
    comparisons = {
        "C0_minus_SOG_ns": metrics["C0"]["macro_design_mae_ns"]
        - metrics["SOG"]["macro_design_mae_ns"],
        "N1_SOG_minus_N1": {
            "seeds": seeds,
            "paired_differences_ns": paired,
            "mean_ns": float(np.mean(paired)),
            "sample_std_ns": float(np.std(paired, ddof=1)),
            "per_design": per_design,
        },
    }
    destination.mkdir(parents=True, exist_ok=True)
    write_json(
        destination / "metrics.json",
        {
            "signature": signature,
            "evaluation": manifest["followup_config"]["evaluation"],
            "test": metrics,
            "comparisons": comparisons,
            "calibration_raw_test": calibration_raw,
            "calibration_test_clipped_count": int((raw < 0).sum()),
        },
    )
    combined = pd.concat(frames, ignore_index=True)
    require(
        combined.groupby(["model", "seed"], dropna=False)
        .size()
        .eq(int(test.sum()))
        .all(),
        "Incomplete prediction coverage",
    )
    atomic(
        destination / "test_predictions.parquet",
        lambda p: combined.to_parquet(p, index=False),
    )
    atomic(
        destination / "test_predictions.csv", lambda p: combined.to_csv(p, index=False)
    )
    summary = pd.DataFrame(
        [
            {
                "run": n,
                "macro_design_mae_ns": v["macro_design_mae_ns"],
                "pooled_mae_ns": v["pooled"]["mae_ns"],
                "pooled_rmse_ns": v["pooled"]["rmse_ns"],
            }
            for n, v in metrics.items()
        ]
    )
    atomic(destination / "summary.csv", lambda p: summary.to_csv(p, index=False))
    export_curves(run)
    lines = [
        "# Exploratory SOG follow-up results",
        "",
        "The original test results were inspected before proposing these experiments. These are exploratory follow-ups, not a new untouched test.",
        "",
        f"Calibration: a={coefficients['a']:.8f}, b={coefficients['b_ns']:.8f} ns; {int((raw < 0).sum())} test predictions clipped at zero.",
        "",
        "| Run | Macro-design MAE (ns) | Pooled RMSE (ns) |",
        "| --- | ---: | ---: |",
    ]
    lines += [
        f"| {r.run} | {r.macro_design_mae_ns:.6f} | {r.pooled_rmse_ns:.6f} |"
        for r in summary.itertuples()
    ]
    lines += [
        "",
        f"C0 minus SOG MAE: {comparisons['C0_minus_SOG_ns']:.6f} ns.",
        f"Mean paired SOG-only minus four-view N1 MAE: {np.mean(paired):.6f} ns; negative favors SOG-only.",
        "",
        "All three seeds and all held-out register predictions are saved. No post-test tuning or best-seed selection.",
        "Original split, feature scaling, target scale, MLP initialization and batch ordering are retained. Two test families limit generalization conclusions.",
        "Curve CSVs, batch diagnostics, per-design errors, per-view pooling diagnostics, and checkpoint histories are saved alongside the model artifacts.",
    ]
    atomic(destination / "SUMMARY.md", lambda p: p.write_text("\n".join(lines) + "\n"))
    seal(
        destination,
        signature,
        [
            "metrics.json",
            "summary.csv",
            "SUMMARY.md",
            "test_predictions.parquet",
            "test_predictions.csv",
            "learning_curves.csv",
            "per_design_curves.csv",
            "batch_diagnostics.csv",
        ],
    )
