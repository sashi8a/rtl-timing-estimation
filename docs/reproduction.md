# Reproduction and artifact access

## 1. Review the completed assessment without compute

Clone this private repository and start with [the report](report.md), [Task 4](task4-reflections.md), [implementation overview](implementation.md) and [results index](delivery-index.md). Figures, compact metrics, the all-study ledger, dataset inventories, source manifests, configurations, tests and lockfiles are committed. No GPU is needed to read the results.

Large generated files are deliberately outside Git. Two separate archives support deeper review:

- `rtl-timing-review.zip`: current reviewer-facing source/docs, compact feature/label/release tables, and all three modeling run directories including checkpoints, predictions, histories and provenance. `DELIVERY-MANIFEST.json` hashes its payload; the `.sha256` sidecar checks the zip.
- `task2-complete-artifacts.tar.gz`: original RTL/library assets and complete raw EDA reports, scripts, proofs and data. Its recorded SHA-256 and size are in [the bundle descriptor](results/task2_artifact_bundle.json).

These archives are maintained by the repository owner separately from Git. Access to the private Git repository alone does not automatically provide server access or the archives. Obtain the corresponding archives from the owner before running artifact-dependent commands. Personal study notes are not part of either reviewer deliverable.

## 2. Verify existing artifacts and regenerate figures

Extract the review zip into a separate checkout directory; its paths are relative to the project root. Check the supplied archive checksum before extraction. Do not overlay unrelated local experimental outputs.

```bash
# Standard-library verification; no CUDA is needed.
python3 experiments/task3_generalization/verify_package.py \
  --run runs/task3-generalization-20260925-v1

# Isolated reporting environment; does not alter experimental locks.
uv sync --project reporting --frozen
uv run --project reporting python reporting/build_figures.py
```

The CV verifier checks manifests, source snapshot, prepared arrays, all model seals and final coverage. The figure builder verifies all three studies' sealed result files before reading their tables. The archived `package-sha256.json` and the review archive's `DELIVERY-MANIFEST.json` also permit full per-file transport verification. Rebuilding a zip does not regenerate labels or train models.

## 3. Regenerate the dataset on a compatible Linux host

The tested EDA host is Ubuntu x86-64, with Docker, eight logical CPUs and 31 GiB RAM. No GPU is required for Tasks 1–2. Use [Task 1 setup](task1-runbook.md) for the pinned image and Python version, then [Task 2 reproduction](task2-runbook.md) for source fetching, the reset-cell variant, collection and release validation.

```bash
uv sync --locked
# Fetch all pinned RTL/library inputs using the loop in task2-runbook.md.
# Pull the image digest from configs/eda.json before running containers.
uv run python scripts/test_reset_variant.py
uv run python scripts/run_label_collection.py --workers 4 --deadline-minutes 40
uv run python scripts/export_dataset.py
uv run python scripts/validate_collection.py
uv run pytest -q
uv run ruff check src scripts tests
```

`configs/eda.json` records the tested Docker prefix (`sudo -n docker`), container image and environment script. Adapt privileges deliberately on another host. A deadline can leave explicit partial coverage; inspect the collection inventory before using a release. Resumption requires matching inputs and output hashes, not merely existing filenames.

**Exact replay versus a new regeneration:** modeling configurations pin the published release SHA. Fresh EDA execution can change provenance or serialized artifacts even if numerical tables agree. A newly generated release is not silently interchangeable with the frozen one. Use the supplied frozen artifacts for exact study verification. To study a new release, revalidate it, record its new identity, revise configurations explicitly in an isolated copy, and use new run directories. Do not overwrite original artifacts or relabel changed inputs as identical.

## 4. Modeling environment, tests and execution

The recorded modeling host used an NVIDIA L40S with PyTorch 2.8.0/CUDA 12.8. The locked environment is separate from the Task 2 environment:

```bash
uv sync --project modeling --frozen --python 3.12.6
CUBLAS_WORKSPACE_CONFIG=:4096:8 modeling/.venv/bin/python -m pytest -q modeling/tests
CUBLAS_WORKSPACE_CONFIG=:4096:8 modeling/.venv/bin/python -m pytest -q experiments/task3_followup/tests
CUBLAS_WORKSPACE_CONFIG=:4096:8 modeling/.venv/bin/python -m pytest -q experiments/task3_generalization/tests
```

Run isolated suites separately to avoid module-name collisions. CPU checks can run without the original GPU, while CUDA checks and the recorded training/evaluation runners require a compatible GPU. Do not interpret a skipped GPU test as a GPU pass.

With the verified artifacts and matching deployment environment:

```bash
CUBLAS_WORKSPACE_CONFIG=:4096:8 modeling/.venv/bin/python modeling/run.py \
  --run runs/task3-20260925-v1
CUBLAS_WORKSPACE_CONFIG=:4096:8 modeling/.venv/bin/python experiments/task3_followup/follow_run.py \
  --base-run runs/task3-20260925-v1 --run runs/task3-followup-20260925-v1
CUBLAS_WORKSPACE_CONFIG=:4096:8 modeling/.venv/bin/python experiments/task3_generalization/generalization_run.py \
  --base-run runs/task3-20260925-v1 --run runs/task3-generalization-20260925-v1
```

Completed runs are verified and skipped. Follow-up deployment `source_revision.json` files are supplied in the review archive and are bound by the manifests. A bare clone omits these ignored deployment files and generated inputs; do not invent their provenance to make checks pass.

Strict resumption verifies code, input/output hashes, configuration and runtime; saved absolute base-run paths and host/runtime fingerprints mean copying files to an arbitrary machine is not a transparent resume. A different host/path/environment may correctly fail these checks. Use the recorded compatible deployment for exact resumption, or make a separately documented new experiment with fresh provenance. Bitwise training identity across different GPU/software stacks is not claimed.

Systemd templates and detailed recovery instructions are in the [original](task3-runbook.md), [SOG follow-up](task3-followup-runbook.md) and [CV](task3-generalization-runbook.md) runbooks. Their `/home/sashi/...` paths describe the recorded deployment rather than a universal install location. No source or checkpoint edits are needed to inspect the already completed results.

## 5. Assessment coverage

| Assessment task | Deliverable |
|---|---|
| Task 1: collection and paper-related features | Pinned 19-design manifest, four representations, feature contract, extraction code and measured inventory |
| Task 2: open-source timing labels | Explicit label/constraint contract, mapping/timing validation, 1,304 eligible bit records, raw evidence archive |
| Task 3: models and held-out evaluation | Three separately labeled studies, controlled comparisons, complete per-seed results, checkpoints and diagnostics |
| Task 4: reflection | Quality/limits, prioritized future work, observed versus hypothesized open-source-flow differences |

No additional training is required to complete these deliverables. The documented portability limits and unmeasured runtime/commercial/physical comparisons remain limitations rather than implied completed validation.
