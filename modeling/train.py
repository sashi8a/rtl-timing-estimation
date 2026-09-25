"""One resumable model run. Checkpoints contain only this project's own state."""

import argparse
import hashlib
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from common import atomic, completed, read, require, seal, write_json
from metrics import evaluate, prediction_frame
from neural import PathModel, optimizer_for, predict, temperature, training_epoch
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from data import load


def setup():
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False


def torch_save(path, value):
    atomic(path, lambda p: torch.save(value, p))


def state_digest(model):
    h = hashlib.sha256()
    for name, value in model.mlp.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def run_model(run, name, seed=0, device="cuda"):
    records, a, frozen = load(run)
    signature = frozen["signature"]
    directory = (
        Path(run) / "models" / (f"{name}-seed{seed}" if name.startswith("N") else name)
    )
    directory.mkdir(parents=True, exist_ok=True)
    if completed(directory, signature):
        print(f"{directory.name}: verified completed output, skipping", flush=True)
        return
    started = time.time()
    if (directory / "status.json").exists():
        require(
            read(directory / "status.json")["signature"] == signature,
            "Stale partial run",
        )
    write_json(
        directory / "status.json",
        {
            "state": "running",
            "model": name,
            "seed": seed,
            "signature": signature,
            "updated_at": time.time(),
        },
    )
    train, val = [(records.partition == p).to_numpy() for p in ("train", "validation")]
    config = frozen["config"]
    if name.startswith("T"):
        model = HistGradientBoostingRegressor(**config["tree"])
        with threadpool_limits(limits=4):
            model.fit(
                a["tree"][train],
                a["y"][train],
                sample_weight=a["weights"][train]
                if name == "T1"
                else np.ones(train.sum()),
            )
            history = []
            for step, (pt, pv) in enumerate(
                zip(
                    model.staged_predict(a["tree"][train]),
                    model.staged_predict(a["tree"][val]),
                    strict=True,
                ),
                1,
            ):
                history.append(
                    {
                        "iteration": step,
                        "training_objective_mae_ns": float(
                            np.average(
                                np.abs(pt - a["y"][train]),
                                weights=a["weights"][train] if name == "T1" else None,
                            )
                        ),
                        "training": evaluate(records[train], a["y"][train], pt),
                        "validation": evaluate(records[val], a["y"][val], pv),
                    }
                )
            predictions = {
                part: model.predict(a["tree"][indices])
                for part, indices in [("train", train), ("validation", val)]
            }
        atomic(directory / "model.joblib", lambda p: joblib.dump(model, p))
        write_json(directory / "history.json", history)
        outputs = ["model.joblib", "history.json"]
        details = {
            "training_weight_min": float(
                (a["weights"][train] if name == "T1" else np.ones(train.sum())).min()
            ),
            "training_weight_max": float(
                (a["weights"][train] if name == "T1" else np.ones(train.sum())).max()
            ),
        }
    else:
        setup()
        require(
            device != "cuda" or torch.cuda.is_available(),
            "CUDA unavailable; refusing silent CPU fallback",
        )
        torch.manual_seed(seed)
        if device == "cuda":
            torch.cuda.manual_seed_all(seed)
        cfg = config["neural"]
        model = PathModel(a["neural"].shape[-1], cfg["hidden"], name == "N2").to(device)
        initial_digest = state_digest(model)
        optimizer = optimizer_for(model, cfg)
        xt = torch.tensor(a["neural"][train], device=device)
        mt = torch.tensor(a["mask"][train], device=device)
        xv = torch.tensor(a["neural"][val], device=device)
        mv = torch.tensor(a["mask"][val], device=device)
        scale = frozen["target_scale_ns"]
        yt = torch.tensor(a["y"][train] / scale, dtype=torch.float32, device=device)
        history, best, first_epoch = [], None, 1
        checkpoint = directory / "latest.pt"
        if checkpoint.exists():
            saved = torch.load(checkpoint, map_location=device, weights_only=False)
            require(
                saved["signature"] == signature
                and saved["name"] == name
                and saved["seed"] == seed,
                "Stale checkpoint",
            )
            require(
                saved["initial_mlp_sha256"] == initial_digest, "Initialization changed"
            )
            model.load_state_dict(saved["model"])
            optimizer.load_state_dict(saved["optimizer"])
            history, best, first_epoch = (
                saved["history"],
                saved["best"],
                saved["epoch"] + 1,
            )
            torch.set_rng_state(saved["rng_cpu"].cpu())
            if device == "cuda":
                torch.cuda.set_rng_state_all([v.cpu() for v in saved["rng_cuda"]])
            print(f"{directory.name}: resumed at epoch {first_epoch}", flush=True)
        for epoch in range(first_epoch, cfg["epochs"] + 1):
            tick = time.time()
            loss, gradients, batches = training_epoch(
                model, optimizer, xt, mt, yt, seed, epoch, cfg, name
            )
            pt, pv = predict(model, xt, mt) * scale, predict(model, xv, mv) * scale
            train_metrics = evaluate(records[train], a["y"][train], pt)
            val_metrics = evaluate(records[val], a["y"][val], pv)
            tau = temperature(cfg, name, epoch)
            row = {
                "epoch": epoch,
                "phase": "hard" if tau is None else "smooth",
                "temperature_scaled": tau,
                "temperature_ns": None if tau is None else tau * scale,
                "learning_rate": optimizer.param_groups[0]["lr"],
                "training_objective_mae_ns": loss * scale,
                "training_hard": train_metrics,
                "validation_hard": val_metrics,
                "gradient_norm_mean_before_clip": float(np.mean(gradients)),
                "gradient_norm_max_before_clip": float(np.max(gradients)),
                "gradient_clipped_fraction": float(
                    np.mean(np.asarray(gradients) > cfg["gradient_clip"])
                ),
                "representation_weights": model.logits.softmax(dim=0)
                .detach()
                .cpu()
                .tolist(),
                "batches": batches,
                "elapsed_seconds": time.time() - tick,
            }
            if tau is not None:
                smooth_val = predict(model, xv, mv, tau) * scale
                row["validation_smooth"] = evaluate(
                    records[val], a["y"][val], smooth_val
                )
                row["validation_hard_minus_smooth_mean_ns"] = float(
                    (pv - smooth_val).mean()
                )
                row["validation_hard_minus_smooth_max_ns"] = float(
                    (pv - smooth_val).max()
                )
            history.append(row)
            # Save validation predictions every 10 epochs plus every selection candidate.
            # Include view scores/path counts to inspect pooling and size-related error.
            if epoch % 10 == 0 or epoch == 1 or epoch in cfg["candidate_epochs"]:
                frame = prediction_frame(records[val], a["y"][val], pv, name, seed)
                with torch.no_grad():
                    _, vh = model(xv, mv, return_views=True)
                    _, vs = model(xv, mv, tau, return_views=True)
                for vi, rep in enumerate(config["representations"]):
                    frame[f"{rep}_path_count"] = a["mask"][val, vi].sum(axis=-1)
                    frame[f"{rep}_hard_score_ns"] = vh[:, vi].cpu().numpy() * scale
                    frame[f"{rep}_smooth_score_ns"] = vs[:, vi].cpu().numpy() * scale
                atomic(
                    directory / "epoch_predictions" / f"validation-{epoch:03}.parquet",
                    lambda p, frame=frame: frame.to_parquet(p, index=False),
                )
            if epoch in cfg["candidate_epochs"] and (
                best is None or val_metrics["macro_design_mae_ns"] < best["score"]
            ):
                best = {
                    "epoch": epoch,
                    "score": val_metrics["macro_design_mae_ns"],
                    "model": {
                        k: v.detach().cpu().clone()
                        for k, v in model.state_dict().items()
                    },
                }
            saved = {
                "signature": signature,
                "name": name,
                "seed": seed,
                "epoch": epoch,
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "history": history,
                "best": best,
                "initial_mlp_sha256": initial_digest,
                "rng_cpu": torch.get_rng_state(),
                "rng_cuda": torch.cuda.get_rng_state_all() if device == "cuda" else [],
            }
            torch_save(checkpoint, saved)
            if epoch in cfg["candidate_epochs"]:
                torch_save(directory / f"checkpoint-{epoch:03}.pt", saved)
            write_json(directory / "history.json", history)
            write_json(
                directory / "status.json",
                {
                    "state": "running",
                    "model": name,
                    "seed": seed,
                    "signature": signature,
                    "epoch": epoch,
                    "total_epochs": cfg["epochs"],
                    "updated_at": time.time(),
                    "validation_macro_design_mae_ns": val_metrics[
                        "macro_design_mae_ns"
                    ],
                },
            )
            if epoch % 10 == 0 or epoch == 1:
                print(
                    f"{directory.name}: epoch {epoch}/{cfg['epochs']}, val MAE={val_metrics['macro_design_mae_ns']:.6f} ns, epoch={row['elapsed_seconds']:.2f}s",
                    flush=True,
                )
        require(best is not None, "No valid checkpoint candidate")
        model.load_state_dict(best["model"])
        torch_save(
            directory / "selected.pt",
            {
                "signature": signature,
                "name": name,
                "seed": seed,
                "epoch": best["epoch"],
                "model": best["model"],
                "initial_mlp_sha256": initial_digest,
            },
        )
        predictions = {
            "train": predict(model, xt, mt) * scale,
            "validation": predict(model, xv, mv) * scale,
        }
        details = {
            "selected_epoch": best["epoch"],
            "validation_selection_mae_ns": best["score"],
            "initial_mlp_sha256": initial_digest,
            "representation_weights": model.logits.softmax(dim=0)
            .detach()
            .cpu()
            .tolist(),
        }
        outputs = ["selected.pt", "latest.pt", "history.json"]
        outputs += [
            str(p.relative_to(directory))
            for p in sorted((directory / "epoch_predictions").glob("*.parquet"))
        ]
        outputs += [p.name for p in sorted(directory.glob("checkpoint-*.pt"))]
    metrics, frames = {}, []
    for part, indices in [("train", train), ("validation", val)]:
        pred = predictions[part]
        metrics[part] = evaluate(records[indices], a["y"][indices], pred)
        frames.append(
            prediction_frame(
                records[indices],
                a["y"][indices],
                pred,
                name,
                seed if name.startswith("N") else None,
            )
        )
    frame = pd.concat(frames, ignore_index=True)
    atomic(
        directory / "predictions.parquet", lambda p: frame.to_parquet(p, index=False)
    )
    write_json(directory / "metrics.json", metrics)
    write_json(
        directory / "details.json",
        {
            **details,
            "signature": signature,
            "model": name,
            "seed": seed,
            "last_process_seconds": time.time() - started,
        },
    )
    write_json(
        directory / "status.json",
        {
            "state": "complete",
            "signature": signature,
            "updated_at": time.time(),
            **details,
        },
    )
    seal(
        directory,
        signature,
        outputs
        + ["metrics.json", "details.json", "predictions.parquet", "status.json"],
    )
    print(f"{directory.name}: complete", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument(
        "--model", choices=["T0", "T1", "N0", "N1", "N2"], required=True
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", default="cuda", choices=["cpu", "cuda"])
    args = parser.parse_args()
    run_model(args.run, args.model, args.seed, args.device)
