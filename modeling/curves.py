"""Plot-ready CSV exports retain iteration/epoch, batch and design diagnostics."""

from pathlib import Path

import pandas as pd
from common import atomic, read


def export_curves(run):
    run = Path(run)
    curves, designs, batches = [], [], []
    for path in sorted((run / "models").glob("*/history.json")):
        for record in read(path):
            step = record.get("epoch", record.get("iteration"))
            common = {
                "run": path.parent.name,
                "step": step,
                "step_kind": "epoch" if "epoch" in record else "tree_iteration",
            }
            row = dict(common)
            for key, value in record.items():
                if not isinstance(value, (dict, list)):
                    row[key] = value
            for part, key in [
                ("train", "training_hard" if "training_hard" in record else "training"),
                (
                    "validation",
                    "validation_hard" if "validation_hard" in record else "validation",
                ),
            ]:
                metrics = record[key]
                row[f"{part}_macro_design_mae_ns"] = metrics["macro_design_mae_ns"]
                row[f"{part}_pooled_mae_ns"] = metrics["pooled"]["mae_ns"]
                row[f"{part}_pooled_rmse_ns"] = metrics["pooled"]["rmse_ns"]
                for design, value in metrics["designs"].items():
                    designs.append(
                        {**common, "partition": part, "design_id": design, **value}
                    )
            if "representation_weights" in record:
                for rep, value in zip(
                    ["sog", "aig", "aimg", "xag"],
                    record["representation_weights"],
                    strict=True,
                ):
                    row[f"{rep}_mixing_weight"] = value
            curves.append(row)
            for batch in record.get("batches", []):
                batches.append({**common, **batch})
    for filename, rows in [
        ("learning_curves.csv", curves),
        ("per_design_curves.csv", designs),
        ("batch_diagnostics.csv", batches),
    ]:
        table = pd.DataFrame(rows)
        atomic(
            run / "results" / filename,
            lambda p, table=table: table.to_csv(p, index=False),
        )
