# Reproducing the two-design label pilot

Use the same uv environment and pinned EDA container as Task 1. Run EDA on the Linux server. The target is defined in [the label contract](task2-label-contract.md).

## Constraints and features

GCD now uses the common generated SDC. Its original ORFS constraint file and original generated artifacts are retained for comparison. Fetch pinned inputs and regenerate the pilot feature branches with constraint fingerprints:

```bash
uv run rtl-timing fetch gcd
uv run rtl-timing fetch timer32
```

For each design and each of `sog`, `aig`, `aimg`, `xag`, run:

```bash
uv run rtl-timing generate gcd --representation sog
uv run rtl-timing verify-equivalence gcd --representation sog
```

Use TIMER32's design ID `timer32` for its four runs. Do not reuse old summaries lacking SDC hashes when joining labels. Original GCD reports are archived on the server under `data/archive/task1_initial/gcd/`; commit `6623f62` preserves the original configuration and results.

## Diagnostic proofs

```bash
uv run python scripts/diagnose_equivalence.py --run
```

This runs three separately named variants for TIMER32 and PWM256 SOG. It does not overwrite the main proof status or promote a conditional reset-model pass to general equivalence. Without `--run`, it summarizes retained logs. See `docs/results/equivalence_diagnostics.json`.

## Labels and inspection

```bash
uv run rtl-timing generate-labels gcd
uv run rtl-timing generate-labels timer32
uv run python scripts/summarize_label_pilot.py
uv run python scripts/validate_collection.py
uv run python scripts/summarize_collection.py
uv run python scripts/snapshot_provenance.py
```

The label command builds a broader-library netlist independently from RTL, queries both endpoint transitions and direct pin arrivals, checks raw-report arithmetic, runs the mapping proof, and writes label and join tables. It retains only ordinary combinational gates and DFFs in the target library: physical-only, latch, scan, tristate, clock-gating, and multi-output adder cells are excluded; the exact selected/excluded cell lists are recorded.

Per-design outputs live in `data/labels/<design>/`: `labels.parquet`, `feature_label_join.parquet`, `netlist.json`, `bog.v` (the target netlist; filename retained for the shared proof helper), `target.lib`, scripts, raw reports, proof status, and `summary.json`. The `training_eligible` column is a gate, not a model prediction. Re-check it before training.

The review script verifies all 99 pilot labels and 396 feature-to-label matches and writes six representative raw-path examples to `docs/results/task2_pilot_review.md`. The 396 matched rows are four views of 99 register bits, not 396 independent targets. General collection runs must report unmatched/ambiguous endpoints rather than assume the pilot's complete coverage.

No model is trained by these commands. Run `uv run pytest -q` and `uv run ruff check src scripts tests` for code checks. The broader rollout requires an explicit decision about the 9 currently quarantined designs; the pilot does not establish commercial-tool accuracy.

The complete pilot data and raw reports are also available locally under `data/labels/`, and packaged on the server in `/home/sashi/task2-pilot-artifacts.tar.gz`. The historical filename `docs/results/task1_artifact_hashes.json` now covers both feature and pilot-label artifacts.
