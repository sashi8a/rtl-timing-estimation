"""All-model freeze gate, followed by one fixed out-of-fold evaluation."""

from pathlib import Path

import bootstrap  # noqa: F401
import joblib
import numpy as np
import pandas as pd
import torch
from common import atomic, completed, digest, read, require, seal, write_json
from generalization_data import load_manifest, load_partition
from generalization_train import ContextModel, directory, setup
from metrics import basic, evaluate, prediction_frame
from neural import predict


def jobs(config):
    return [(fold, "T1", 0) for fold in range(1, 5)] + [
        (fold, name, seed)
        for fold in range(1, 5)
        for seed in config["seeds"]
        for name in config["neural_models"]
    ]


def freeze_models(run, manifest):
    hashes = {}
    pairs = {}
    for fold, name, seed in jobs(manifest["config"]):
        d = directory(run, fold, name, seed)
        require(completed(d, manifest["signature"]), f"Incomplete required run: {d}")
        details = read(d / "details.json")
        if name != "T1":
            require(details["epoch"] == 200, "Evaluation requires epoch 200")
            key = (fold, seed)
            require(
                key not in pairs or pairs[key] == details["paired"],
                "Paired initialization/order differs",
            )
            pairs[key] = details["paired"]
            saved = torch.load(d / "final.pt", map_location="cpu", weights_only=False)
            require(
                saved["epoch"] == 200
                and saved["signature"] == manifest["signature"]
                and saved["fold"] == fold
                and saved["name"] == name
                and saved["seed"] == seed
                and saved["paired"] == details["paired"],
                "Final checkpoint mismatch",
            )
        for n in ("complete.json", "final.pt" if name != "T1" else "model.joblib"):
            hashes[str((d / n).relative_to(run))] = digest(d / n)
    value = {
        "signature": manifest["signature"],
        "models": hashes,
        "policy": "All 40 final models sealed before evaluation; fixed epoch 200",
    }
    path = Path(run) / "model_freeze.json"
    if path.exists():
        require(read(path) == value, "Frozen models changed")
    else:
        write_json(path, value)
    return value


def depth_bin(values):
    return pd.cut(
        values,
        bins=[-1, 0, 5, 10, 20, np.inf],
        labels=["0", "1–5", "6–10", "11–20", ">20"],
    ).astype(str)


def aggregate(frame):
    metrics = {}
    summary = []
    designs = []
    families = []
    tails = []
    diagnostics = []
    for (name, seed), group in frame.groupby(["model", "seed"]):
        key = f"{name}-seed{seed}"
        overall = evaluate(
            group, group.arrival_ns.to_numpy(), group.prediction_ns.to_numpy()
        )
        fold_metrics = {
            str(f): evaluate(g, g.arrival_ns.to_numpy(), g.prediction_ns.to_numpy())
            for f, g in group.groupby("evaluation_fold")
        }
        metrics[key] = {"overall": overall, "folds": fold_metrics}
        for scope, m in [("all", overall)] + list(fold_metrics.items()):
            summary.append(
                dict(
                    model=name,
                    seed=int(seed),
                    fold=scope,
                    macro_design_mae_ns=m["macro_design_mae_ns"],
                    macro_family_of_design_mae_ns=m["macro_family_of_design_mae_ns"],
                    **m["pooled"],
                )
            )
        for design, m in overall["designs"].items():
            designs.append(dict(model=name, seed=int(seed), design_id=design, **m))
        for family, m in overall["families"].items():
            families.append(dict(model=name, seed=int(seed), family=family, **m))
        for design, m in overall["high_arrival_tail"].items():
            tails.append(dict(model=name, seed=int(seed), design_id=design, **m))
        for category in ["arrival_quartile", "sog_depth_bin", "target_launch_type"]:
            for (fold, label), g in group.groupby(["evaluation_fold", category]):
                diagnostics.append(
                    dict(
                        model=name,
                        seed=int(seed),
                        fold=int(fold),
                        category=category,
                        bin=str(label),
                        **basic(g.arrival_ns, g.prediction_ns),
                    )
                )
    summary = pd.DataFrame(summary)
    comparisons = []
    for (name, seed), g in frame.groupby(["model", "seed"]):
        controls = ["SOG"] if name not in ("SOG", "median") else []
        if name == "N1":
            controls += ["N0"]
        if name == "N1-NoContext":
            controls += ["N1"]
        for control in controls:
            cseed = int(seed) if control.startswith("N") else 0
            for scope in ["all", "1", "2", "3", "4"]:
                lhs = metrics[f"{name}-seed{seed}"]
                rhs = metrics[f"{control}-seed{cseed}"]
                a = lhs["overall"] if scope == "all" else lhs["folds"][scope]
                b = rhs["overall"] if scope == "all" else rhs["folds"][scope]
                comparisons.append(
                    {
                        "model": name,
                        "control": control,
                        "seed": int(seed),
                        "fold": scope,
                        "macro_design_mae_difference_ns": a["macro_design_mae_ns"]
                        - b["macro_design_mae_ns"],
                        "pooled_mae_difference_ns": a["pooled"]["mae_ns"]
                        - b["pooled"]["mae_ns"],
                    }
                )
    seed_summary = []
    for name, g in summary[summary.fold == "all"].groupby("model"):
        values = g.macro_design_mae_ns.to_numpy()
        seed_summary.append(
            {
                "model": name,
                "seeds": len(g),
                "mean_macro_design_mae_ns": float(values.mean()),
                "std_macro_design_mae_ns": float(values.std(ddof=1))
                if len(g) > 1
                else 0.0,
                "min_macro_design_mae_ns": float(values.min()),
                "max_macro_design_mae_ns": float(values.max()),
            }
        )
    tables = {
        "summary": summary,
        "seed_summary": pd.DataFrame(seed_summary),
        "per_design": pd.DataFrame(designs),
        "per_family": pd.DataFrame(families),
        "high_arrival_tail": pd.DataFrame(tails),
        "diagnostics": pd.DataFrame(diagnostics),
        "paired_differences": pd.DataFrame(comparisons),
    }
    if comparisons:
        tables["paired_seed_means"] = (
            tables["paired_differences"]
            .groupby(["model", "control", "fold"], as_index=False)[
                ["macro_design_mae_difference_ns", "pooled_mae_difference_ns"]
            ]
            .mean()
        )
    return metrics, tables


def validate_predictions(frame):
    require(len(frame) == 12636, "Expected 12,636 prediction rows")
    require(
        not frame.duplicated(
            ["model", "seed", "design_id", "target_endpoint_id"]
        ).any(),
        "Duplicate OOF prediction",
    )
    require(
        frame.groupby(["model", "seed"]).size().eq(1053).all()
        and frame.groupby(["model", "seed"]).ngroups == 12,
        "Model prediction coverage differs",
    )
    require(not frame.family.isin(["opencores_aes", "uart"]).any(), "Forbidden family")
    require(
        np.isfinite(frame[["arrival_ns", "prediction_ns"]]).all().all(),
        "Nonfinite prediction",
    )
    require(
        frame.groupby(["design_id", "target_endpoint_id"])
        .evaluation_fold.nunique()
        .eq(1)
        .all(),
        "Multiple evaluation folds",
    )


def finish(run):
    run = Path(run)
    manifest = load_manifest(run, full_check=True)
    signature = manifest["signature"]
    if completed(run / "results", signature):
        return
    freeze_models(run, manifest)
    setup()
    frames = []
    curves = []
    batches = []
    for fold in range(1, 5):
        records, a, fitted, _ = load_partition(run, fold, "evaluation", manifest)
        require(
            set(records.family) == set(manifest["config"]["folds"][fold - 1]),
            "Evaluation family mismatch",
        )
        require(
            set(records.family).isdisjoint(fitted["training_families"]),
            "Family leakage",
        )
        records["arrival_quartile"] = (
            np.searchsorted(fitted["quartiles_ns"], a["y"], side="right") + 1
        )
        records["sog_depth_bin"] = depth_bin(records.sog_max_sampled_path_depth)
        predictions = [
            ("SOG", 0, a["sog"]),
            ("median", 0, np.full(len(records), fitted["target_scale_ns"])),
        ]
        for f, name, seed in jobs(manifest["config"]):
            if f != fold:
                continue
            d = directory(run, fold, name, seed)
            if name == "T1":
                p = joblib.load(d / "model.joblib").predict(a["tree"])
            else:
                model = ContextModel(
                    a["neural"].shape[-1],
                    manifest["config"]["neural"]["hidden"],
                    fitted["context_indices"] if name == "N1-NoContext" else (),
                ).to("cuda")
                saved = torch.load(
                    d / "final.pt", map_location="cuda", weights_only=False
                )
                model.load_state_dict(saved["model"])
                p = (
                    predict(
                        model,
                        torch.tensor(a["neural"], device="cuda"),
                        torch.tensor(a["mask"], device="cuda"),
                    )
                    * fitted["target_scale_ns"]
                )
            predictions.append((name, seed, p))
            for row in read(d / "history.json"):
                flat = {k: v for k, v in row.items() if not isinstance(v, (dict, list))}
                flat.update(fold=fold, model=name, seed=seed)
                for kind in ["training", "training_hard", "training_smooth"]:
                    flat.update(
                        {f"{kind}_{k}": v for k, v in row.get(kind, {}).items()}
                    )
                curves.append(flat)
                for batch in row.get("batches", []):
                    batches.append(
                        dict(
                            fold=fold,
                            model=name,
                            seed=seed,
                            epoch=row["epoch"],
                            loss_ns=batch["loss_scaled"] * fitted["target_scale_ns"],
                            **batch,
                        )
                    )
        for name, seed, p in predictions:
            frames.append(prediction_frame(records, a["y"], p, name, seed))
    frame = pd.concat(frames, ignore_index=True)
    validate_predictions(frame)
    require(
        sum("epoch" in row for row in curves) == 7200, "Neural history coverage differs"
    )
    metrics, tables = aggregate(frame)
    tables.update(
        training_curves=pd.DataFrame(curves),
        batch_losses=pd.DataFrame(batches),
        predictions=frame,
    )
    dest = run / "results"
    atomic(dest / "predictions.parquet", lambda p: frame.to_parquet(p, index=False))
    for name, table in tables.items():
        atomic(
            dest / f"{name}.csv", lambda p, table=table: table.to_csv(p, index=False)
        )
    write_json(dest / "metrics.json", metrics)
    write_json(
        dest / "coverage.json",
        {
            "learned_runs": 40,
            "neural_epochs": 7200,
            "designs": 17,
            "families": 8,
            "register_bits": 1053,
            "prediction_rows": len(frame),
            "signature": signature,
        },
    )
    lines = [
        "# Exploratory family cross-validation",
        "",
        "All 40 learned runs completed; 7,200 neural epochs. All 1,053 development registers have out-of-family predictions. AES/UART excluded.",
        "",
        "| Model | Mean macro-design MAE (ns) | Seed SD (ns) |",
        "|---|---:|---:|",
    ]
    for r in tables["seed_summary"].itertuples():
        lines.append(
            f"| {r.model} | {r.mean_macro_design_mae_ns:.6f} | {r.std_macro_design_mae_ns:.6f} |"
        )
    lines += [
        "",
        "Primary scores average errors over all 17 designs, separately per neural seed, then summarize seeds. They are not unweighted fold means. Families are the generalization units; folds share training data. This exploratory study does not restore an untouched test set. Seed spread describes optimization variability, not uncertainty across independent datasets.",
        "",
        "Quartile cutoffs use each fold training labels, with ties assigned to the higher bin; empty bins are omitted from descriptive tables. Depth bins use maximum sampled SOG path depth. Target launch type and true-arrival categories are evaluation metadata only.",
        "",
        "No evaluation learning curves, early stopping, or checkpoint selection were used. Fixed epoch 200 was evaluated only after all final models were sealed.",
    ]
    atomic(dest / "SUMMARY.md", lambda p: p.write_text("\n".join(lines) + "\n"))
    seal(
        dest,
        signature,
        [
            p.name
            for p in sorted(dest.iterdir())
            if p.is_file() and p.name != "complete.json" and not p.name.startswith(".")
        ],
    )
