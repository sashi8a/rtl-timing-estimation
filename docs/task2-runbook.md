# Reproducing the Task 2 collection

Use the locked uv environment and pinned Linux EDA container described in [Task 1 setup](task1-runbook.md). The [label contract](task2-label-contract.md) defines the target and proof boundary. No GPU or model training is used here.

## Inputs and library variant

```bash
uv sync --locked
uv run python - <<'PY'
import json
import subprocess
for design in json.load(open('data/manifests/designs.json'))['designs']:
    subprocess.run(['uv', 'run', 'rtl-timing', 'fetch', design['id']], check=True)
PY
```

Fetch sources only before generation, not during an active run. `configs/task1.json` explicitly selects `"bog_library_variant": "reset_v1"`. The alternative `upstream` selects the original libraries. The derived files live under `data/libraries/reset_v1/`; the pinned upstream files remain unchanged. Each derived library adds only `DFFR_X1` and `DFFS_X1`, retaining all original cells and the representation's combinational vocabulary.

To check actual cell preservation and reproduce the isolated adoption experiment:

```bash
uv run python scripts/test_reset_variant.py
uv run python scripts/test_reset_variant.py --run --deadline-minutes 20
```

The second command creates a new `data/experiments/reset_v1-<timestamp>/` directory and tests TIMER32, PWM256, and GCD in all four representations, with at most four EDA containers. It does not switch the production configuration automatically. Adoption requires all 12 original clock-aware checks to pass. No `async2sync` substitution or weaker reset assumptions are used. The recorded adoption experiment is in `docs/results/reset_repair_experiment.json`; cell checks are in `reset_library_validation.json`.

## Generate or resume

```bash
uv run python scripts/run_label_collection.py --workers 4 --deadline-minutes 40
# Or select designs explicitly:
uv run python scripts/run_label_collection.py --designs gcd timer32 --workers 2 --deadline-minutes 10
```

The command regenerates missing/stale feature views, runs their mapping checks, builds independent broader-library target netlists, queries rise/fall D-pin arrivals, checks direct pin queries and path-increment sums, checks target mapping, and constructs fresh joins. It preserves existing label columns and the `training_eligible` gate. Labels from unproven designs remain available for inspection but cannot become training examples.

Resumption is enabled by default. Reuse requires matching RTL/SDC files, manifest and configurations, selected library, relevant pipeline source files, `uv.lock`, `pyproject.toml`, `.python-version`, the actual Python/package versions, and all sealed output hashes. Label signatures additionally include all four feature-table and proof/provenance identities. Missing provenance forces regeneration; it is never filled in retrospectively. `--no-resume` forces regeneration. Do not run overlapping collectors for the same design.

A replaced directory is moved to `data/archive/<run-id>/` before generation. Each invocation has a unique status file in `data/collection_runs/labels-<run-id>.json`. Failures and timeouts are distinct statuses and produce a nonzero exit; successful designs remain intact. Each EDA stage has a ten-minute ceiling further bounded by the command's remaining wall time. Timed-out containers are stopped. The overall budget also includes validation and packaging, so leave time after the generation deadline.

## Validate and export

```bash
uv run python scripts/export_dataset.py
uv run python scripts/validate_collection.py
uv run python scripts/summarize_collection.py
uv run python scripts/summarize_label_pilot.py
uv run python scripts/snapshot_provenance.py
uv run pytest -q
uv run ruff check src scripts tests
```

Run the exporter where all raw reports exist. It independently rechecks hashes, identities, one-to-one alias matching, constraints, units, both transition reports, direct queries, increment sums, and proof/eligibility status. A design with failed validation is reported explicitly and contributes no released rows. Inspect `docs/results/task2_collection.json`; exporter completion alone does not imply complete collection coverage.

- `data/releases/task2/registers.parquet`: one row per eligible register bit, with arrival labels, design/family IDs, four feature-view references and endpoint identities, constraint hash, and provenance references/hashes.
- `data/releases/task2/manifest.json`: dataset hash, coverage by design and family, exclusions, and collection-run references.
- `docs/results/task2_collection.json` and `task2_inventory.csv`: compact committed inventory and exclusion evidence.
- `data/labels/<design>/`: all label/join tables, target libraries/netlists, scripts, reports, proofs, and sealed provenance, including successfully labeled excluded designs.
- `data/processed/<design>/<representation>/`: corresponding feature tables, raw reports, netlists, proofs, and sealed provenance.

Use the four BOG feature tables as model inputs. Release-row rise/fall arrivals and target `startpoint_type` are target/audit metadata, not predictive features. Design/family IDs define grouping and splits. The four feature views are correlated inputs for one register-bit target, not four independent training examples. The next stage must split by family. The historical filename `docs/results/task1_artifact_hashes.json` now inventories both tasks; execution-specific provenance lives beside each artifact.

## Historical results

The original Task 1 and two-design pilot are retained in Git history and server archives (`task1-artifacts.tar.gz`, `task2-pilot-artifacts.tar.gz`, and `data/archive/`). Their unproven statuses describe those earlier library mappings. Current release eligibility is determined from the newly generated `reset_v1` artifacts. Conditional `async2sync` diagnostics remain historical evidence only.

## Current artifact bundle

`/home/sashi/task2-complete-artifacts.tar.gz` on the compute server contains the current sources, all raw feature/label reports, tables, libraries, experiment evidence, release, and result inventories. Its SHA-256 sidecar is `/home/sashi/task2-complete-artifacts.sha256`. Use it with this repository revision; generated data remain excluded from Git. The full verified bundle has also been extracted into the local project workspace. Superseded data remain under the server's `data/archive/20260925T032645Z-1617b16d/`, including the previous inventories. The superseded first-pass reset-library release and its exact code are archived under `data/archive/20260925T035331Z-d071168e/`.
