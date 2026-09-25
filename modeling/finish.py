"""Freeze validation choices first, then evaluate all held-out predictions."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
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
from curves import export_curves
from metrics import evaluate, prediction_frame
from neural import PathModel, predict
from threadpoolctl import threadpool_limits
from train import setup

from data import load


def finish(run):
    run = Path(run)
    records, a, frozen = load(run, full_check=True)
    signature = frozen["signature"]
    destination = run / "results"
    if completed(destination, signature):
        return
    models = [("T0", 0), ("T1", 0)] + [
        (n, s) for s in frozen["config"]["seeds"] for n in ("N0", "N1", "N2")
    ]
    files, selection = {}, {}
    for name, seed in models:
        key = f"{name}-seed{seed}" if name.startswith("N") else name
        directory = run / "models" / key
        require(completed(directory, signature), f"Model unfinished: {key}")
        details = read(directory / "details.json")
        selection[key] = details
        for file in (
            "complete.json",
            "details.json",
            "selected.pt" if name.startswith("N") else "model.joblib",
        ):
            relative = str((directory / file).relative_to(run))
            files[relative] = digest(run / relative)
    for seed in frozen["config"]["seeds"]:
        require(
            len(
                {
                    selection[f"{n}-seed{seed}"]["initial_mlp_sha256"]
                    for n in ("N0", "N1", "N2")
                }
            )
            == 1,
            "Paired initialization differs",
        )
    freeze = {
        "signature": signature,
        "selection": selection,
        "files": files,
        "rule": frozen["config"]["test_policy"],
    }
    if (run / "selection_freeze.json").exists():
        require(
            read(run / "selection_freeze.json") == freeze,
            "Selections changed after test freeze",
        )
    else:
        write_json(run / "selection_freeze.json", freeze)
    checked_hashes(run, files)
    # Only after every checkpoint is finalized do we evaluate the test partition.
    setup()
    require(torch.cuda.is_available(), "CUDA unavailable during final evaluation")
    test = (records.partition == "test").to_numpy()
    train = (records.partition == "train").to_numpy()
    median = float(np.median(a["y"][train]))
    results, frames = {}, []
    for name, seed in [("median", 0), ("SOG", 0)] + models:
        key = f"{name}-seed{seed}" if name.startswith("N") else name
        if name == "median":
            pred = np.full(test.sum(), median)
        elif name == "SOG":
            pred = a["sog"][test]
        elif name.startswith("T"):
            model = joblib.load(run / "models" / key / "model.joblib")
            with threadpool_limits(limits=4):
                pred = model.predict(a["tree"][test])
        else:
            state = torch.load(
                run / "models" / key / "selected.pt",
                map_location="cuda",
                weights_only=False,
            )
            require(state["signature"] == signature, "Stale selected checkpoint")
            model = PathModel(
                a["neural"].shape[-1],
                frozen["config"]["neural"]["hidden"],
                name == "N2",
            ).cuda()
            model.load_state_dict(state["model"])
            pred = (
                predict(
                    model,
                    torch.tensor(a["neural"][test], device="cuda"),
                    torch.tensor(a["mask"][test], device="cuda"),
                )
                * frozen["target_scale_ns"]
            )
        results[key] = evaluate(records[test], a["y"][test], pred)
        frames.append(
            prediction_frame(
                records[test],
                a["y"][test],
                pred,
                name,
                seed if name.startswith("N") else None,
            )
        )
    # References on validation/train are useful context, without tuning them.
    references = {}
    for part in ("train", "validation"):
        index = (records.partition == part).to_numpy()
        references[part] = {
            name: evaluate(records[index], a["y"][index], p)
            for name, p in [
                ("median", np.full(index.sum(), median)),
                ("SOG", a["sog"][index]),
            ]
        }
    comparisons = {
        "T1_minus_T0": results["T1"]["macro_design_mae_ns"]
        - results["T0"]["macro_design_mae_ns"]
    }
    for treatment, control in [("N1", "N0"), ("N2", "N1")]:
        paired = [
            results[f"{treatment}-seed{s}"]["macro_design_mae_ns"]
            - results[f"{control}-seed{s}"]["macro_design_mae_ns"]
            for s in frozen["config"]["seeds"]
        ]
        comparisons[f"{treatment}_minus_{control}"] = {
            "seeds": frozen["config"]["seeds"],
            "paired_differences_ns": paired,
            "mean_ns": float(np.mean(paired)),
            "sample_std_ns": float(np.std(paired, ddof=1)) if len(paired) > 1 else None,
        }
    destination.mkdir(parents=True, exist_ok=True)
    write_json(
        destination / "metrics.json",
        {
            "signature": signature,
            "test": results,
            "references": references,
            "comparisons": comparisons,
        },
    )
    combined = pd.concat(frames, ignore_index=True)
    atomic(
        destination / "test_predictions.parquet",
        lambda p: combined.to_parquet(p, index=False),
    )
    atomic(
        destination / "test_predictions.csv", lambda p: combined.to_csv(p, index=False)
    )
    overview = pd.DataFrame(
        [
            {
                "run": key,
                "macro_design_mae_ns": value["macro_design_mae_ns"],
                "pooled_mae_ns": value["pooled"]["mae_ns"],
                "pooled_rmse_ns": value["pooled"]["rmse_ns"],
            }
            for key, value in results.items()
        ]
    )
    atomic(destination / "summary.csv", lambda p: overview.to_csv(p, index=False))
    lines = [
        "# Task 3 completed experiment results",
        "",
        "Frozen 6/2/2 family split; 716/337/251 register bits. Test families: AES key expansion and UART.",
        "",
        "Arrival-time regression only. Macro-design MAE is primary; lower is better. Two test families limit generalization claims.",
        "",
        "| Run | Test macro design MAE (ns) | Pooled RMSE (ns) |",
        "| --- | ---: | ---: |",
    ]
    for row in overview.itertuples():
        lines.append(
            f"| {row.run} | {row.macro_design_mae_ns:.6f} | {row.pooled_rmse_ns:.6f} |"
        )
    lines += [
        "",
        "All neural inference uses hard-max path pooling. All seeds are reported; no best-seed selection.",
        "N1−N0 tests smooth training; N2−N1 tests learned mixing conditional on smooth training. Representation weights are not causal importance scores.",
        "Residual prediction was excluded by scope, not by a negative experiment.",
        "",
        "Full metrics, per-design/family/tail diagnostics, test predictions, and paired differences are alongside this file.",
        "Per-model history.json contains learning curves and neural batch losses, gradient norms, temperatures, weights, and pooling gaps.",
        "Neural epoch_predictions/ contains validation predictions and view scores every ten epochs; selected and candidate checkpoints are retained.",
    ]
    atomic(destination / "SUMMARY.md", lambda p: p.write_text("\n".join(lines) + "\n"))
    export_curves(run)
    seal(
        destination,
        signature,
        [
            "metrics.json",
            "test_predictions.parquet",
            "test_predictions.csv",
            "summary.csv",
            "SUMMARY.md",
            "learning_curves.csv",
            "per_design_curves.csv",
            "batch_diagnostics.csv",
        ],
    )
    print("All held-out evaluations saved", flush=True)
