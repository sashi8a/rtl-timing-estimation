# Task 3: unattended training and saved diagnostics

Run ID: `task3-20260925-v1`. Server project root:
`/home/sashi/rtl-timing-estimation`. The corresponding local project contains the
source and frozen modeling lockfile. The server has its own persistent copy;
closing the laptop or SSH connection does not stop the service.

The approved experiment is T0/T1 plus N0/N1/N2 at paired seeds 11, 22, 33, and
training-median/direct-SOG references. Family membership and hyperparameters are
in `modeling/config.json`; scientific decisions are in `task3-experiment-plan.md`.

## Check progress after connecting to the GPU server

```bash
cd /home/sashi/rtl-timing-estimation
python3 modeling/status.py
systemctl --user status rtl-task3.service --no-pager
tail -n 30 runs/task3-20260925-v1/supervisor.log
tail -n 20 runs/task3-20260925-v1/logs/N0-seed11.log
```

`status.json` reports `preflight`, `training`, `final_evaluation`, `complete`, or
`failed`. Per-model status records epoch progress. A completed service may show
`active (exited)` because it retains its successful state; the decisive result is
`status.json` = `complete` plus a valid `results/complete.json` seal. If progress
is stale, inspect service state and the named model log rather than inferring
success from an old status file. Failure details are also in `failures/`.

## Saved outputs

All generated outputs live below `runs/task3-20260925-v1/` and stay out of Git:

| Path | Purpose |
| --- | --- |
| `task2_preflight.json` | Original-environment, read-only revalidation of all 19 designs |
| `prepared/manifest.json`, `split.json` | Input/code hashes, endpoint membership, feature names, train-only scalers |
| `runtime.json` | Exact package, Python, GPU, driver and lock identities |
| `models/<run>/history.json` | Full tree-iteration or neural epoch/batch diagnostics |
| `models/<run>/latest.pt` | Atomic neural checkpoint, optimizer and RNG state for resumption |
| `models/<run>/checkpoint-{170,180,190,200}.pt` | Candidate neural checkpoints retained for inspection |
| `models/<run>/selected.pt` or `model.joblib` | Validation-selected neural model or fixed tree model |
| `models/<run>/epoch_predictions/` | Validation predictions and view scores at epoch 1 and every 10 epochs |
| `models/<run>/predictions.parquet` | Final selected-model train/validation predictions |
| `selection_freeze.json` | All model selections and hashes fixed before test evaluation |
| `results/SUMMARY.md`, `summary.csv`, `metrics.json` | Final overview and full design/family/tail metrics |
| `results/test_predictions.{parquet,csv}` | Every held-out register prediction for all conditions and seeds |
| `results/learning_curves.csv` | Epoch/iteration losses, hard-max MAE/RMSE, gradients, temperature, weights |
| `results/per_design_curves.csv` | Design-level learning curves and bias |
| `results/batch_diagnostics.csv` | Neural batch loss in scaled target units and pre-clipping gradient norm |

Neural history distinguishes the online training objective from hard-max
training/validation metrics. Batch loss multiplied by the recorded target scale
is in ns. Validation-only per-view hard/smooth scores support inspection of path
count effects. Correlations that are undefined are null. No test learning curves
are collected, so test performance cannot guide checkpoint selection.

## Reliability and access

The user-level systemd service runs as `sashi`, not root, with user lingering
enabled so it survives logout and starts again after a reboot. It opens no
network listener and needs no GitHub token or copied SSH private key. The run
directory is owner-only, new files use umask 0077, core dumps are disabled, and
the service cannot gain new privileges. It is limited to 16 GiB of host RAM.

The tree queue and GPU queue run concurrently; the GPU queue executes nine runs
serially. A file lock prevents duplicate supervisors. Atomic writes prevent
partial checkpoints from replacing a good one. The service retries failed exits
after 30 seconds, with at most three starts per hour. Completed runs are hash-
verified and skipped; neural runs resume at the next epoch. Changed code,
dependencies, features, labels, or split/config cause refusal rather than silent
reuse. Persistent scientific/data errors therefore remain explicit failures.

This protects against disconnects and recoverable process interruptions, not
loss of the server disk or termination of the provider's instance. Copy results
back locally after completion; source is maintained in the private repository.

## Stop or resume the same experiment

```bash
systemctl --user stop rtl-task3.service
systemctl --user reset-failed rtl-task3.service
systemctl --user start rtl-task3.service
```

Stopping may discard the current partial epoch, but retains the last complete
checkpoint. Do not edit modeling code/config or locked packages while a run is
active. A protocol revision requires a new run directory and a recorded reason;
never change the split after viewing test results. After results are secured,
disable future automatic starts with:

```bash
systemctl --user disable --now rtl-task3.service
```

## Reproduce on the same prepared server

```bash
cd /home/sashi/rtl-timing-estimation/modeling
/home/sashi/.local/bin/uv sync --frozen --python ../.venv/bin/python
CUBLAS_WORKSPACE_CONFIG=:4096:8 .venv/bin/python -m pytest -q
cd ..
CUBLAS_WORKSPACE_CONFIG=:4096:8 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=2 \
  modeling/.venv/bin/python modeling/run.py --run runs/task3-20260925-v1
```

Use either the service or the foreground command, never both. The original Task 2
environment and complete artifact bundle are required for the read-only preflight.
Model deserialization is restricted to files generated locally by this project;
do not load untrusted external joblib/PyTorch checkpoints.
