"""Two-parameter L1 calibration; training labels only."""

from pathlib import Path

import numpy as np
import pandas as pd
from common import atomic, completed, require, seal, write_json
from follow_data import load
from metrics import evaluate, prediction_frame
from scipy import sparse
from scipy.optimize import linprog


def fit(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    require(
        x.ndim == y.ndim == 1 and len(x) == len(y) and len(y) > 0,
        "Invalid calibration input shape",
    )
    require(
        np.isfinite(x).all() and np.isfinite(y).all(), "Nonfinite calibration inputs"
    )
    n = len(y)
    design = sparse.csr_matrix(np.column_stack([x, np.ones(n)]))
    constraints = sparse.vstack(
        [
            sparse.hstack([design, -sparse.eye(n)]),
            sparse.hstack([-design, -sparse.eye(n)]),
        ]
    ).tocsr()
    result = linprog(
        np.r_[0.0, 0.0, np.full(n, 1 / n)],
        A_ub=constraints,
        b_ub=np.r_[y, -y],
        bounds=[(0, None), (None, None)] + [(0, None)] * n,
        method="highs-ds",
    )
    require(
        result.success and result.x is not None and np.isfinite(result.x).all(),
        f"Calibration solver failed: {result.message}",
    )
    a, b = map(float, result.x[:2])
    objective = float(np.abs(a * x + b - y).mean())
    require(
        a >= -1e-10 and np.isclose(objective, result.fun, atol=1e-7, rtol=1e-7),
        "Calibration optimum failed verification",
    )
    return {
        "a": a,
        "b_ns": b,
        "objective_mae_ns": objective,
        "solver": "highs-ds",
        "solver_status": int(result.status),
        "solver_message": str(result.message),
        "solver_iterations": int(result.nit),
        "training_registers": n,
        "inference": "max(0, a * SOG_arrival_ns + b_ns)",
    }


def prediction(coefficients, x):
    raw = coefficients["a"] * np.asarray(x) + coefficients["b_ns"]
    require(np.isfinite(raw).all(), "Nonfinite calibrated prediction")
    return raw, np.maximum(raw, 0)


def run_calibration(run):
    records, arrays, frozen = load(run)
    directory = Path(run) / "models/C0"
    if completed(directory, frozen["signature"]):
        return
    train = (records.partition == "train").to_numpy()
    coefficients = fit(arrays["sog"][train], arrays["y"][train])
    write_json(directory / "coefficients.json", coefficients)
    metrics, frames = {}, []
    for part in ("train", "validation"):
        idx = (records.partition == part).to_numpy()
        raw, pred = prediction(coefficients, arrays["sog"][idx])
        metrics[part] = {
            "scored": evaluate(records[idx], arrays["y"][idx], pred),
            "raw": evaluate(records[idx], arrays["y"][idx], raw),
            "clipped_count": int((raw < 0).sum()),
        }
        frame = prediction_frame(records[idx], arrays["y"][idx], pred, "C0")
        frame["raw_prediction_ns"] = raw
        frame["clipped_at_zero"] = raw < 0
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    atomic(
        directory / "predictions.parquet", lambda p: combined.to_parquet(p, index=False)
    )
    write_json(directory / "metrics.json", metrics)
    seal(
        directory,
        frozen["signature"],
        ["coefficients.json", "metrics.json", "predictions.parquet"],
    )
    print("C0 calibration complete", flush=True)
