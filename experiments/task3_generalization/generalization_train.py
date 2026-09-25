"""Training-only workers, fixed final epoch and exact atomic recovery."""

import hashlib
import time
from pathlib import Path

import bootstrap  # noqa: F401
import joblib
import numpy as np
import torch
from common import atomic, completed, read, require, seal, write_json
from generalization_data import load_partition
from metrics import basic
from neural import (
    PathModel,
    epoch_order,
    optimizer_for,
    predict,
    temperature,
    training_epoch,
)
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits


class ContextModel(PathModel):
    def __init__(self, inputs, hidden, context_indices=()):
        super().__init__(inputs, hidden)
        keep = torch.ones(inputs)
        keep[list(context_indices)] = 0
        self.register_buffer("input_keep", keep)

    def forward(self, x, mask, temperature=None, return_views=False):
        return super().forward(x * self.input_keep, mask, temperature, return_views)


def setup():
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False


def state_digest(model):
    h = hashlib.sha256()
    for name, value in model.mlp.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def torch_save(path, value):
    atomic(path, lambda p: torch.save(value, p))


def directory(run, fold, name, seed):
    return (
        Path(run)
        / "models"
        / f"fold{fold}"
        / (f"{name}-seed{seed}" if name.startswith("N") else name)
    )


def paired_identity(inputs, cfg, n, seed):
    # Isolated RNG prevents verification itself from perturbing training.
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        digest = state_digest(ContextModel(inputs, cfg["hidden"]))
    order = hashlib.sha256()
    for epoch in range(1, cfg["epochs"] + 1):
        order.update(epoch_order(n, seed, epoch).numpy().tobytes())
    return {"initial_mlp_sha256": digest, "batch_order_sha256": order.hexdigest()}


def restore(saved, model, optimizer, signature, name, seed, pair, device):
    require(
        saved["signature"] == signature
        and saved["name"] == name
        and saved["seed"] == seed
        and saved["paired"] == pair,
        "Stale checkpoint",
    )
    require(
        saved["epoch"] == len(saved["history"]), "Checkpoint progress/history mismatch"
    )
    model.load_state_dict(saved["model"])
    optimizer.load_state_dict(saved["optimizer"])
    torch.set_rng_state(saved["rng_cpu"].cpu())
    if device == "cuda":
        torch.cuda.set_rng_state_all([v.cpu() for v in saved["rng_cuda"]])
    return saved["history"], saved["epoch"] + 1


def run_model(run, fold, name, seed=0, device="cuda"):
    records, a, fitted, frozen = load_partition(run, fold, "train")
    signature = frozen["signature"]
    config = frozen["config"]
    cfg = config["neural"]
    require(cfg["epochs"] == 200, "Only epoch 200 is permitted")
    require(name == "T1" or name in config["neural_models"], "Unknown model")
    require(name == "T1" or seed in config["seeds"], "Unknown seed")
    dest = directory(run, fold, name, seed)
    dest.mkdir(parents=True, exist_ok=True)
    if completed(dest, signature):
        print(f"{dest}: verified completed, skipping", flush=True)
        return
    if (dest / "status.json").exists():
        require(
            read(dest / "status.json")["signature"] == signature, "Stale partial run"
        )
    write_json(
        dest / "status.json",
        {
            "state": "running",
            "signature": signature,
            "fold": fold,
            "model": name,
            "seed": seed,
            "updated_at": time.time(),
        },
    )
    history = []
    if name == "T1":
        with threadpool_limits(limits=4):
            model = HistGradientBoostingRegressor(**config["tree"])
            model.fit(a["tree"], a["y"], sample_weight=a["weights"])
            for i, p in enumerate(model.staged_predict(a["tree"]), 1):
                history.append(
                    {
                        "iteration": i,
                        "training": basic(a["y"], p),
                        "training_objective_mae_ns": float(
                            np.average(abs(p - a["y"]), weights=a["weights"])
                        ),
                    }
                )
        atomic(dest / "model.joblib", lambda p: joblib.dump(model, p))
        outputs = ["model.joblib"]
        details = {
            "weight_min": float(a["weights"].min()),
            "weight_max": float(a["weights"].max()),
            "training_weight_sum": float(a["weights"].sum()),
        }
    else:
        setup()
        require(device != "cuda" or torch.cuda.is_available(), "CUDA unavailable")
        pair = paired_identity(a["neural"].shape[-1], cfg, len(records), seed)
        torch.manual_seed(seed)
        if device == "cuda":
            torch.cuda.manual_seed_all(seed)
        model = ContextModel(
            a["neural"].shape[-1],
            cfg["hidden"],
            fitted["context_indices"] if name == "N1-NoContext" else (),
        ).to(device)
        require(
            state_digest(model) == pair["initial_mlp_sha256"], "Initialization mismatch"
        )
        optimizer = optimizer_for(model, cfg)
        x = torch.tensor(a["neural"], device=device)
        mask = torch.tensor(a["mask"], device=device)
        scale = fitted["target_scale_ns"]
        y = torch.tensor(a["y"] / scale, dtype=torch.float32, device=device)
        checkpoint = dest / "latest.pt"
        first = 1
        if checkpoint.exists():
            history, first = restore(
                torch.load(checkpoint, map_location=device, weights_only=False),
                model,
                optimizer,
                signature,
                name,
                seed,
                pair,
                device,
            )
            require(first <= 201, "Invalid resume epoch")
            print(f"Resuming {name} at epoch {first}", flush=True)
        for epoch in range(first, 201):
            tick = time.monotonic()
            loss, gradients, batches = training_epoch(
                model, optimizer, x, mask, y, seed, epoch, cfg, name
            )
            tau = temperature(cfg, name, epoch)
            hard = predict(model, x, mask) * scale
            smooth = predict(model, x, mask, tau) * scale if tau is not None else hard
            row = {
                "epoch": epoch,
                "phase": "hard" if tau is None else "smooth",
                "temperature_scaled": tau,
                "temperature_ns": None if tau is None else tau * scale,
                "learning_rate": optimizer.param_groups[0]["lr"],
                "training_objective_mae_ns": loss * scale,
                "training_hard": basic(a["y"], hard),
                "training_smooth": basic(a["y"], smooth),
                "training_hard_minus_smooth_mean_ns": float((hard - smooth).mean()),
                "training_hard_minus_smooth_max_ns": float((hard - smooth).max()),
                "gradient_norm_mean_before_clip": float(np.mean(gradients)),
                "gradient_norm_max_before_clip": float(np.max(gradients)),
                "gradient_clipped_fraction": float(
                    np.mean(np.array(gradients) > cfg["gradient_clip"])
                ),
                "batches": batches,
                "elapsed_seconds": time.monotonic() - tick,
            }
            history.append(row)
            saved = {
                "signature": signature,
                "name": name,
                "seed": seed,
                "fold": fold,
                "epoch": epoch,
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "history": history,
                "paired": pair,
                "rng_cpu": torch.get_rng_state(),
                "rng_cuda": torch.cuda.get_rng_state_all() if device == "cuda" else [],
            }
            torch_save(checkpoint, saved)
            write_json(dest / "history.json", history)
            write_json(
                dest / "status.json",
                {
                    "state": "running",
                    "signature": signature,
                    "fold": fold,
                    "model": name,
                    "seed": seed,
                    "epoch": epoch,
                    "total_epochs": 200,
                    "updated_at": time.time(),
                    "paired": pair,
                },
            )
            if epoch % 20 == 0 or epoch == 1:
                print(
                    f"fold{fold} {name} seed{seed} epoch {epoch}/200 training MAE {row['training_hard']['mae_ns']:.6f} ns",
                    flush=True,
                )
        require(
            len(history) == 200 and history[-1]["epoch"] == 200, "Final epoch missing"
        )
        torch_save(
            dest / "final.pt",
            {
                "signature": signature,
                "fold": fold,
                "name": name,
                "seed": seed,
                "epoch": 200,
                "model": model.state_dict(),
                "paired": pair,
            },
        )
        details = {
            "epoch": 200,
            "paired": pair,
            "context_indices": fitted["context_indices"]
            if name == "N1-NoContext"
            else [],
            "training_rows": len(records),
        }
        outputs = ["final.pt", "latest.pt"]
    write_json(dest / "history.json", history)
    write_json(dest / "details.json", details)
    write_json(
        dest / "status.json",
        {
            "state": "complete",
            "signature": signature,
            "fold": fold,
            "model": name,
            "seed": seed,
            "epoch": 200 if name != "T1" else None,
            "updated_at": time.time(),
        },
    )
    seal(dest, signature, outputs + ["history.json", "details.json", "status.json"])
    print(f"fold{fold} {name} seed{seed} complete", flush=True)
