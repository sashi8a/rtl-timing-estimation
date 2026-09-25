# Exploratory family cross-validation and context ablation

This study implements the approved four-fold development-family experiment. It does not replace the original split or alter earlier experiments. AES and UART are excluded before feature construction. The experiment is exploratory because earlier test results have already been inspected; it does not create a new untouched test set.

## Frozen protocol

| Fold | Evaluation families | Evaluation registers | Training registers |
|---|---|---:|---:|
| 1 | JPEG, PWM256 | 358 | 695 |
| 2 | CIC5, SPI | 337 | 716 |
| 3 | Chameleon peripherals, CRC32 | 196 | 857 |
| 4 | Ethernet, GCD | 162 | 891 |

Every one of 1,053 eligible development register bits from 17 designs belongs to exactly one evaluation fold. Each fold trains on the other six families. Counts and family provenance determine membership, not predictions.

Each fold fits T1 with its original fixed histogram gradient-boosting settings and recomputed equal-family/equal-design weights. Neural models N0, N1, and N1-NoContext each train from scratch with paired seeds 11, 22, and 33. This is four trees plus 36 neural runs, totaling 7,200 neural epochs. The training-label median and direct SOG are references.

All neural models use the original 64/32 MLP, softplus path score, uniform endpoint MAE, AdamW (learning rate 0.001, weight decay 0.0001), batch size 32, and gradient clipping at 1. N0 uses hard max throughout; N1 variants use normalized smooth max with temperature decreasing geometrically from 0.1 to 0.005 over epochs 1–150, followed by hard max for epochs 151–200. Temperatures use each fold's training-median target scale. Inference uses hard max within each view and equal averaging across all four views.

**Only epoch 200 is evaluated.** There is no validation partition, inner search, early stopping, checkpoint selection, or evaluation-fold learning curve. All 40 final model artifacts must be sealed before the evaluation stage opens held-out feature arrays and labels.

## Preprocessing and ablation

Raw immutable feature tables are reconstructed with the original allowlists, path ordering, samples, and narrow empty-driver-statistics encoding. The original normalized arrays are not used for preparation. Padding is fixed at the existing 33-path cap, so evaluation bag sizes cannot change training tensor shapes. Training-only constant removal and endpoint-balanced neural scalers are refitted independently for each fold. Fold 2 shares the original training families, providing an exact reconstruction regression check against the old prepared training arrays.

Neural numeric columns have explicit `path.`, `cone.`, and `design.` namespaces. Representation indicators remain separate. Tree summaries retain these namespaces too. N1-NoContext zeros retained normalized `design.*` columns inside the model on every forward pass; dimensions and initial MLP weights match N1 exactly. These columns represent register count, combinational-operator count, maximum combinational depth, net count, and six global operator counts. Path/cone quantities and launch/representation indicators remain available. Removing these explicit quantities does not remove all possible information about design identity.

Training workers load only the training partition. Evaluation arrays are hash-verified for immutability but are not opened by the fitting worker. The manifest binds the entire frozen study, so changing an evaluation input invalidates resumption even though it cannot change fitted preprocessing or model parameter updates. Initialization and the complete 200-epoch batch-order digest are recorded and checked across paired models.

## Execution

Use the unchanged locked `modeling/.venv`. New code lives exclusively in `experiments/task3_generalization/`; original modules and lockfiles remain unchanged.

```bash
modeling/.venv/bin/python experiments/task3_generalization/generalization_run.py \
  --base-run runs/task3-20260925-v1 \
  --run runs/task3-generalization-20260925-v1

modeling/.venv/bin/python experiments/task3_generalization/status.py \
  --run runs/task3-generalization-20260925-v1
```

The supervisor owns an exclusive file lock. A serial CPU queue fits four trees concurrently with a serial GPU queue ordered by fold 1–4, seed 11/22/33, then N0/N1/N1-NoContext. A failed job records an explicit failure and does not discard or prevent independent jobs from completing. Aggregate evaluation is blocked until all required runs succeed.

Every epoch atomically saves model, optimizer, CPU/CUDA RNG, complete training history, and progress. Restart resumes the last saved epoch; verified complete runs are skipped. Changed code, configuration, environment, inputs, or corrupted artifacts reject resumption. Automatic retries preserve settings and are bounded by systemd. No evaluation-driven retries or best-seed selection are permitted.

The user service is `rtl-task3-generalization.service`, running as `sashi` on the L40S host. It uses `UMask=0077`, `NoNewPrivileges=true`, a 16 GiB host-memory limit, at most three starts per hour, and a 30-second restart delay. User lingering and enabled startup allow operation after SSH logout and restart after a host reboot. Neither the laptop nor this chat is part of the execution chain. Server availability, storage, and hardware remain external dependencies.

```bash
systemctl --user status rtl-task3-generalization.service
systemctl --user show rtl-task3-generalization.service -p ActiveState -p NRestarts
loginctl show-user sashi -p Linger
```

Before reporting that laptop shutdown is safe, close the launch connection and independently reconnect; verify enablement, lingering, advancing epochs, and a readable checkpoint with the current manifest signature.

## Outputs and interpretation boundaries

`manifest.json` records configuration, exact membership, raw-input hashes, original and new source hashes, source revision, runtime, and prepared-array hashes. `source_snapshot/` retains the experiment sources. Each fold stores separate train/evaluation arrays and its fitted preprocessing. Each model has progress, epoch/batch diagnostics, latest and final checkpoints (or the tree artifact), and a completion seal. `model_freeze.json` binds all 40 final models before evaluation.

The final package includes 12,636 unique model/seed/register predictions in Parquet and CSV, full JSON metrics, per-design/family/tail errors, every fold/seed comparison, seed summaries, training curves, batch losses, and a concise summary. All times and errors are in ns, except explicitly marked scaled quantities. Reference/tree seed 0 means a deterministic non-neural run.

Primary macro-design MAE averages across all 17 out-of-fold designs separately for each neural seed, then summarizes seeds. It is **not** the unweighted average of four fold scores. Secondary diagnostics include pooled MAE/RMSE, bias, correlations where defined, and macro-family-of-design MAE. High-arrival tails retain the existing per-design 90th-percentile definition, including ties.

Descriptive arrival quartiles use training-label cutoffs from each fold; cutoff ties enter the higher bin, and empty bins are omitted. SOG depth bins use the maximum sampled path depth per endpoint: 0, 1–5, 6–10, 11–20, >20. Target critical-path launch types and true-arrival categories are evaluation metadata, never predictors.

Families are the relevant generalization units; folds share training data. Seed variation measures optimizer variability, not confidence intervals across independent datasets. Task 4 interpretation remains a separate discussion.

## Verification and synchronization

Run existing suites separately to avoid module-name collisions between isolated experiment packages:

```bash
CUBLAS_WORKSPACE_CONFIG=:4096:8 modeling/.venv/bin/python -m pytest -q experiments/task3_generalization/tests
modeling/.venv/bin/python -m pytest -q modeling/tests experiments/task3_followup/tests
.venv/bin/python -m pytest -q tests
```

After completion, sync from the server (the command can be rerun when the laptop reconnects):

```bash
rsync -az --exclude='.*' \
  -e 'ssh -i ~/.ssh/google_compute_engine' \
  sashi@89.169.111.107:/home/sashi/rtl-timing-estimation/runs/task3-generalization-20260925-v1/ \
  runs/task3-generalization-20260925-v1/
python3 experiments/task3_generalization/verify_package.py \
  --run runs/task3-generalization-20260925-v1
```

The offline verifier checks the manifest, prepared files, source snapshot, model-freeze hashes, all 40 model seals, final result seal, and exact coverage. Do not present a partial backup or an unsealed results directory as the completed study. Publication includes source, protocol, decisions, and verified summaries; generated checkpoints and data remain in the run package.
