"""Explicit register, design, and family aggregation in ns."""

import numpy as np
from common import require
from scipy.stats import spearmanr


def basic(y, pred):
    y, pred = np.asarray(y), np.asarray(pred)
    require(len(y) == len(pred) and len(y) > 0, "Prediction coverage differs")
    require(
        np.isfinite(y).all() and np.isfinite(pred).all(),
        "Nonfinite prediction or label",
    )
    e = pred - y
    corr = len(y) >= 2 and np.ptp(y) > 0 and np.ptp(pred) > 0
    return {
        "n": len(y),
        "mae_ns": float(np.abs(e).mean()),
        "rmse_ns": float(np.sqrt((e * e).mean())),
        "bias_ns": float(e.mean()),
        "pearson": float(np.corrcoef(y, pred)[0, 1]) if corr else None,
        "spearman": float(spearmanr(y, pred).statistic) if corr else None,
    }


def evaluate(records, y, pred):
    table = records[["design_id", "family"]].reset_index(drop=True).copy()
    table["y"], table["prediction"] = y, pred
    designs, families, tails = {}, {}, {}
    for name, group in table.groupby("design_id"):
        designs[name] = basic(group.y, group.prediction)
        threshold = float(group.y.quantile(0.9, interpolation="linear"))
        tail = group[group.y >= threshold]
        tails[name] = {"threshold_ns": threshold, **basic(tail.y, tail.prediction)}
    for name, group in table.groupby("family"):
        families[name] = {
            **basic(group.y, group.prediction),
            "macro_design_mae_ns": float(
                np.mean([designs[d]["mae_ns"] for d in group.design_id.unique()])
            ),
        }
    return {
        "pooled": basic(y, pred),
        "macro_design_mae_ns": float(np.mean([d["mae_ns"] for d in designs.values()])),
        "macro_family_of_design_mae_ns": float(
            np.mean([f["macro_design_mae_ns"] for f in families.values()])
        ),
        "designs": designs,
        "families": families,
        "high_arrival_tail": tails,
    }


def prediction_frame(records, y, pred, model, seed=None):
    result = records.copy()
    result["arrival_ns"], result["prediction_ns"] = y, pred
    result["model"], result["seed"] = model, seed
    result["error_ns"] = np.asarray(pred) - np.asarray(y)
    return result
