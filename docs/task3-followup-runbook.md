# Exploratory SOG follow-ups

The original experiment remains immutable. These follow-ups reuse its 716/337/251
family-separated training/validation/test bits, features, scalers, target scale,
locked environment, and evaluation metrics. The original test results were seen
before these experiments were proposed: report all follow-up results as exploratory.

## Experiments

- **C0:** fit `a * SOG + b` on training registers only with uniform L1 loss,
  `a >= 0`, unrestricted intercept, and SciPy HiGHS dual-simplex linear programming.
  No tuning or per-family coefficients. Score predictions clipped at zero; retain
  raw predictions, clipping counts, coefficients and solver status.
- **N1-SOG:** three seeds (11, 22, 33), each compared to its original N1 run.
  Feed only the frozen SOG slice to the original 33-input, 64/32-hidden-width MLP;
  preserve constant representation indicators and verify initial MLP hashes match.
  The original epoch-order function and training loop preserve paired batch order.
  Use the same 150 smooth plus 50 hard epochs, optimizer, learning rate, clipping,
  and candidates 170/180/190/200 for validation-only checkpoint selection.

Code is isolated in `experiments/task3_followup/`. The neural runner is an adapted
copy of the frozen training harness, importing the original pooling, optimization,
batch-order and metric helpers. No original module or lockfile is modified.
Each new manifest hashes both the new source/config and linked original artifacts,
records its committed source revision and runtime, and rejects stale resumption.

## Server operation

The independent user service `rtl-task3-followup.service` runs as `sashi` with
`Linger=yes`, startup after reboot, owner-only outputs, a 16 GiB host-memory limit,
and three starts per hour at most. It opens no port and needs no laptop connection.
Calibration and the serial three-run GPU queue execute concurrently. Failures
preserve the other queue's progress and write a failure record. Every neural epoch
is atomically checkpointed, including optimizer and RNG state.

After connecting to the existing GPU server:

```bash
cd /home/sashi/rtl-timing-estimation
python3 experiments/task3_followup/status.py
systemctl --user status rtl-task3-followup.service --no-pager
tail -n 20 runs/task3-followup-20260925-v1/supervisor.log
```

To stop or resume without changing the experiment:

```bash
systemctl --user stop rtl-task3-followup.service
systemctl --user reset-failed rtl-task3-followup.service
systemctl --user start rtl-task3-followup.service
```

Never start a second foreground supervisor while the service is active. Do not
edit source/config/locked dependencies during execution. On restart, completed
outputs are verified and skipped; partial neural runs resume at the next epoch.
Provider instance/disk loss remains outside process-recovery protection.

## Outputs

Everything is saved under `runs/task3-followup-20260925-v1/`:

- `manifest.json`: original artifact references, source hashes, revision, runtime,
  seeds, and paired initializations.
- `models/C0/`: coefficients, solver diagnostics, train/validation metrics and
  raw/clipped predictions.
- `models/N1-SOG-seed*/`: original-style epoch/batch histories, gradient norms,
  temperature, hard/smooth validation diagnostics, intermediate predictions,
  candidate checkpoints, selected model, and restart checkpoint.
- `selection_freeze.json`: calibration and all neural selections fixed before
  evaluating the test partition.
- `results/`: summary, full per-design/family/tail metrics, raw/clipped C0 test
  predictions, all model/reference predictions, paired SOG-only minus N1 errors,
  and plot-ready learning-curve, per-design-curve and batch-diagnostic CSVs.

`status.json` = `complete` and a verified `results/complete.json` seal indicate
success. `active (exited)` is the expected systemd state after success. A failed
run reports the actual error instead of declaring partial results complete.

## Reproduction

Use the existing `modeling/.venv`; no installation or lockfile change is needed.
The ignored deployment file `source_revision.json` records the exact commit and
must accompany the source snapshot; its hash is part of the new manifest.

```bash
cd /home/sashi/rtl-timing-estimation
CUBLAS_WORKSPACE_CONFIG=:4096:8 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  modeling/.venv/bin/python -m pytest -q experiments/task3_followup/tests
CUBLAS_WORKSPACE_CONFIG=:4096:8 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=2 \
  modeling/.venv/bin/python experiments/task3_followup/follow_run.py \
  --base-run runs/task3-20260925-v1 --run runs/task3-followup-20260925-v1
```

The service runs the same supervisor. Completed results can be synchronized back
when the laptop reconnects. Copy only final filenames, excluding hidden temporary
files, and verify all completion seals after transfer.
