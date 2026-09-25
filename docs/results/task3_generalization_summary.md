# Exploratory family cross-validation

All 40 learned runs completed; 7,200 neural epochs. All 1,053 development registers have out-of-family predictions. AES/UART excluded.

| Model | Mean macro-design MAE (ns) | Seed SD (ns) |
|---|---:|---:|
| N0 | 0.154636 | 0.008714 |
| N1 | 0.174866 | 0.035826 |
| N1-NoContext | 0.134506 | 0.012840 |
| SOG | 0.175497 | 0.000000 |
| T1 | 0.121225 | 0.000000 |
| median | 0.311723 | 0.000000 |

Primary scores average errors over all 17 designs, separately per neural seed, then summarize seeds. They are not unweighted fold means. Families are the generalization units; folds share training data. This exploratory study does not restore an untouched test set. Seed spread describes optimization variability, not uncertainty across independent datasets.

Quartile cutoffs use each fold training labels, with ties assigned to the higher bin; empty bins are omitted from descriptive tables. Depth bins use maximum sampled SOG path depth. Target launch type and true-arrival categories are evaluation metadata only.

No evaluation learning curves, early stopping, or checkpoint selection were used. Fixed epoch 200 was evaluated only after all final models were sealed.

## Primary and pooled errors

Neural entries below average the three seed-specific metrics; no seeds are selected or ensembled.

| Model | Macro-design MAE (ns) | Pooled MAE (ns) |
|---|---:|---:|
| median | 0.311723 | 0.495680 |
| SOG | 0.175497 | 0.270107 |
| T1 | 0.121225 | 0.264413 |
| N0 | 0.154636 | 0.406342 |
| N1 | 0.174866 | 0.506248 |
| N1-NoContext | 0.134506 | 0.397097 |

## Execution and reproducibility

- Source revision: `2c9df0b93a7f45c2a38f457a4ac05a2f01a62c84`.
- Run signature: `9cc407f8d8984d423756619ea80a2efb46a52c3f29f3d8b5e4da3d9d52eeb687`.
- All 52 tests passed; CPU/GPU recovery, a full interrupted 200-epoch run, and real-data GPU preflight passed.
- All 40 runs completed with zero failures and zero service restarts.
- All 331 packaged files were synced locally and hash-verified; all 494 checked prior files remain unchanged.
- Full checkpoints, 7,200 epoch records, batch losses, gradients, pooling diagnostics and predictions are saved in `runs/task3-generalization-20260925-v1/`.

See the [runbook](../task3-generalization-runbook.md), [full metrics](task3_generalization_metrics.json), [fold/seed metrics](task3_generalization_fold_seed_metrics.csv), [paired differences](task3_generalization_paired_differences.csv), and [execution audit](task3_generalization_execution.json). Task 4 interpretation remains separate.
