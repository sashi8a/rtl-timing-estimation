"""Regenerate presentation figures and a ledger from sealed study results; no fitting."""

import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/rtl-timing-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/rtl-timing-font-cache")
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/figures"
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = ROOT / "docs/results"
STUDIES = {
    "original": "task3-20260925-v1",
    "followup": "task3-followup-20260925-v1",
    "cv": "task3-generalization-20260925-v1",
}
COLORS = {
    "median": "#999999",
    "SOG": "#333333",
    "T0": "#56B4E9",
    "T1": "#0072B2",
    "N0": "#009E73",
    "N1": "#E69F00",
    "N2": "#CC79A7",
    "C0": "#882255",
    "N1-SOG": "#44AA99",
    "N1-NoContext": "#D55E00",
}
rows = []
inputs = {}
for study, run in STUDIES.items():
    directory = ROOT / "runs" / run / "results"
    seal = json.loads((directory / "complete.json").read_text())
    for name, expected in seal["outputs"].items():
        p = directory / name
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Stale result {p}")
    for name in ["summary.csv"]:
        p = directory / name
        inputs[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    s = pd.read_csv(directory / "summary.csv")
    if study == "cv":
        s = s[s.fold == "all"]
    for r in s.to_dict("records"):
        name = r["model"] if study == "cv" else r["run"].split("-seed")[0]
        seed = (
            int(r["seed"])
            if study == "cv"
            else int(r["run"].split("-seed")[1])
            if "-seed" in r["run"]
            else 0
        )
        rows.append(
            {
                "study": study,
                "run_id": run,
                "model": name,
                "seed": seed,
                "evaluation": "development-family OOF" if study == "cv" else "AES/UART",
                "exploratory": study != "original",
                "macro_design_mae_ns": r["macro_design_mae_ns"],
                "pooled_mae_ns": r["mae_ns"] if study == "cv" else r["pooled_mae_ns"],
                "pooled_rmse_ns": r["rmse_ns"]
                if study == "cv"
                else r["pooled_rmse_ns"],
            }
        )
ledger = pd.DataFrame(rows)
ledger.to_csv(RESULTS / "experiment-ledger.csv", index=False)
plt.rcParams.update(
    {
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.fonttype": "none",
        "figure.facecolor": "white",
    }
)


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=160, bbox_inches="tight")
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def bars(ax, study, order, metric):
    sub = ledger[ledger.study == study]
    means = sub.groupby("model")[metric].mean().reindex(order)
    ax.barh(order, means, color=[COLORS[n] for n in order], alpha=0.85)
    for i, n in enumerate(order):
        values = sub[sub.model == n][metric].to_numpy()
        if len(values) > 1:
            ax.scatter(
                values,
                i + np.linspace(-0.16, 0.16, len(values)),
                s=23,
                color="black",
                zorder=3,
            )
        ax.text(
            max(means[n], float(values.max())) + 0.007,
            i,
            f"{means[n]:.3f}",
            va="center",
            fontsize=9,
        )
    ax.invert_yaxis()
    ax.set_xlim(0, 0.75 if metric == "pooled_mae_ns" else 0.37)
    ax.set_xlabel("MAE (ns), lower is better")
    ax.grid(axis="x", alpha=0.2)
    ax.set_axisbelow(True)


fig, axs = plt.subplots(1, 3, figsize=(15, 5.5), layout="constrained")
for ax, study, order, title in zip(
    axs,
    ["original", "followup", "cv"],
    [
        ["median", "SOG", "T0", "T1", "N0", "N1", "N2"],
        ["median", "SOG", "C0", "N1", "N1-SOG"],
        ["median", "SOG", "T1", "N0", "N1", "N1-NoContext"],
    ],
    [
        "Original: AES / UART\n251 test bits, validation selection",
        "Exploratory follow-ups: AES / UART\nSame inspected 251 test bits",
        "Exploratory CV: eight development families\n1,053 OOF bits, fixed epoch 200",
    ],
    strict=True,
):
    bars(ax, study, order, "macro_design_mae_ns")
    ax.set_title(title, fontsize=11)
fig.suptitle(
    "Three studies: keep evaluation populations and selection rules separate\nBars = mean macro-design MAE; black dots = each neural seed (not confidence intervals)",
    fontsize=13,
)
save(fig, "study-results")
fig, axs = plt.subplots(1, 2, figsize=(11, 5), layout="constrained")
for ax, metric, title in zip(
    axs,
    ["macro_design_mae_ns", "pooled_mae_ns"],
    ["Equal weight per design (primary)", "Equal weight per register"],
    strict=True,
):
    bars(ax, "cv", ["median", "SOG", "T1", "N0", "N1", "N1-NoContext"], metric)
    ax.set_xlim(0, 0.75)
    ax.set_title(title)
fig.suptitle(
    "Cross-validation: conclusions depend on the unit being weighted\n17 designs / 1,053 register bits; neural bars average three seeds",
    fontsize=13,
)
save(fig, "cv-metric-tradeoff")
p = RESULTS / "task3_generalization_per_design.csv"
inputs[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
d = (
    pd.read_csv(p)
    .groupby(["design_id", "model"])
    .mae_ns.mean()
    .unstack()[["SOG", "T1", "N0", "N1", "N1-NoContext"]]
)
fig, ax = plt.subplots(figsize=(9, 9), layout="constrained")
im = ax.imshow(d, cmap="Blues", vmin=0, vmax=1.25, aspect="auto")
ax.set_xticks(range(len(d.columns)), d.columns)
ax.set_yticks(range(len(d)), d.index)
for i in range(len(d)):
    for j in range(len(d.columns)):
        v = d.iloc[i, j]
        ax.text(
            j,
            i,
            f"{v:.3f}",
            ha="center",
            va="center",
            color="white" if v > 0.65 else "black",
            fontsize=9,
        )
ax.set_title(
    "CV per-design MAE exposes the divider transfer failure\nNeural entries average three seeds; values in ns"
)
fig.colorbar(im, ax=ax, label="MAE (ns)")
save(fig, "cv-per-design")
p = ROOT / "runs" / STUDIES["original"] / "results/learning_curves.csv"
inputs[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
c = pd.read_csv(p)
fig, axs = plt.subplots(1, 3, figsize=(14, 4.6), layout="constrained", sharey=True)
for ax, name in zip(axs, ["N0", "N1", "N2"], strict=True):
    for metric, color, label in [
        ("train_macro_design_mae_ns", "#0072B2", "Train"),
        ("validation_macro_design_mae_ns", "#D55E00", "Validation"),
    ]:
        sub = c[c.run.str.startswith(name + "-seed")]
        for _, g in sub.groupby("run"):
            ax.plot(g.epoch, g[metric], color=color, alpha=0.22, lw=0.8)
        mean = sub.groupby("epoch")[metric].mean()
        ax.plot(mean.index, mean.values, color=color, lw=2, label=label)
    ax.axvline(150, color="gray", linestyle=":", lw=1)
    ax.set_title(name)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Hard-max macro-design MAE (ns)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.2)
    ax.legend()
fig.suptitle(
    "Original experiment: training fit and held-out validation behavior\nThin lines = each seed; thick lines = seed mean; no test learning curves",
    fontsize=12,
)
save(fig, "original-learning-curves")
(OUT / "provenance.json").write_text(
    json.dumps(
        {
            "input_sha256": inputs,
            "matplotlib": matplotlib.__version__,
            "pandas": pd.__version__,
            "source": "reporting/build_figures.py",
            "note": "Descriptive figures from sealed outputs; no fitting or model selection",
        },
        indent=2,
    )
    + "\n"
)
print("Wrote ledger and four PNG/SVG figures")
