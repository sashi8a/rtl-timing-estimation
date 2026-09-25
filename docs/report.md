# Research report — work in progress

## Task 1: Data collection and feature extraction

The objective is register-level arrival-time regression. Four restricted-library Boolean operator graphs (SOG, AIG, AIMG, XAG) provide structural and timing features. BOG arrival times and ranks are inputs; they are not the target-circuit labels or a separate ranking objective.

The retained collection contains 19 designs across 10 families, each with four BOG representations. DCT was deferred after a long ABC synthesis run; its configuration is preserved separately. This remains within the requested approximately 20 designs.

Design sources and dependencies are pinned in `data/manifests/designs.json`. The collection mixes arithmetic/control, communication, signal-processing, and cryptographic blocks. Related Ethernet and JPEG blocks share family IDs. The effective diversity is smaller than the number of designs; later splits must keep entire families together. Complexity is measured by synthesized register bits, combinational operators, and graph depth, rather than source lines that depend on formatting and coding style.

The implementation adapts RTL-Timer's synthesis sequence and aggregation definitions to OpenSTA reports. Exact correspondence and deviations are in [the feature contract](task1-features.md); provenance and licensing are in [attribution](attribution.md). The pinned ORFS container and locked uv environment make tool and package choices explicit.

Generated endpoint, path, and design tables preserve named columns. Critical paths are queried per endpoint and per transition. Seeded random topology candidates are checked against actual timing paths, and duplicate routes are removed. Empty or untimed data remain explicit. Raw reports, source hashes, constraints, and formal-check logs are retained on the compute server.

### Measured Task 1 results after the Task 2 refresh

| Check | Result |
| --- | --- |
| Retained designs / families | 19 / 10 |
| Completed and validated BOG runs | 76 / 76 |
| Register bits across designs (one representation each) | 1,304 |
| Register endpoints across four representations | 5,216 / 5,216 timed |
| Retained path-feature rows | 84,154 |
| Register bits per design | 4–312 |
| Combinational operators per representation | 54–6,689 |
| Cross-representation endpoint identities | Agree for all 19 designs |
| Formal mapping checks | 76 passed; 0 unproven under `reset_v1` |
| Unit tests / lint | 20 passed on laptop and server / clean |
| Resumption check | All four GCD feature views and target labels reused with matching hashes |

These are extraction and consistency results, not prediction-accuracy results. Path rows and the four representations are correlated views, not independent training examples. The full inventory, validation records, and final input/output hashes are in `docs/results/`.

### Observed limitations

- OpenSTA required LEF metadata and rejected signed net declarations in mapped gate netlists. A narrow declaration normalization preserves the raw export; equivalence checks use the normalized netlist.
- The original libraries left 36 BOG mapping checks unproven. Adding the dedicated asynchronous reset/set cells resolves all 36 under the unchanged checker. The proof still covers the Yosys pre-mapping elaboration after state alignment, not original frontend translation or reset-sequence reachability.
- No placement or extracted wire parasitics are used in Task 1. These are restricted-library BOG features under stated constraints, not signoff timing.
- GCD originally kept ORFS constraints. It has now been harmonized to the common experimental SDC and all four feature views regenerated before label generation.
- Random backward walks are not uniform over all paths. The 32-path cap and deduplication are documented local choices.
- The dataset is small and contains related blocks and small state machines. Register rows are not independent samples for estimating design generalization.

No commercial-tool comparison has been performed. Differences in commercial versus open-source timing accuracy remain hypotheses, not measured conclusions.

## Task 2: Validated collection complete

The target is maximum rising/falling data arrival at each retained mapped register bit's D pin, in ns. The target circuit is synthesized independently from RTL using a broader Nangate45 gate set at the same corner and common SDC as the features. These are post-synthesis labels without placement or extracted wire parasitics, not post-route/signoff timing.

The isolated reset-cell experiment passed all 12 adoption checks: TIMER32, PWM256, and GCD in each of four representations. The `reset_v1` variant adds only `DFFR_X1` and `DFFS_X1`; original cells, combinational vocabularies, upstream files, timing constraints, and proof assumptions are unchanged. All 19 designs were regenerated consistently under this variant. This is observed repair evidence for this collection, not a universal diagnosis of asynchronous proof failures.

| Release check | Result |
| --- | ---: |
| Designs / families | 19 / 10 |
| Unique target register bits | 1,304 |
| Timed and training-eligible register bits | 1,304 / 1,304 |
| Unique feature-to-label matches across four views | 5,216 / 5,216 |
| BOG mapping checks | 76 / 76 passed |
| Broader-library target mapping checks | 19 / 19 passed |
| Untimed / unmatched / ambiguous bits | 0 / 0 / 0 |
| Failed or timed-out collection stages | 0 |
| Retained designs excluded from this release | 0 |

Every label's rising and falling arrival was checked against direct OpenSTA pin queries and reported path-increment sums. The validator also checks complete register inventories, unique RTL aliases, one-to-one matches, cross-view identities, ns/fF units, identical feature/label constraint hashes, artifact hashes, and eligibility. GCD and TIMER32 target-label tables are byte-identical to the original pilot. The six [inspected examples](task2-pilot-observations.md) therefore remain applicable.

| Family | Designs | Eligible register bits |
| --- | ---: | ---: |
| `chameleon_peripherals` | 3 | 164 |
| `cic5` | 1 | 312 |
| `crc32` | 1 | 32 |
| `opencores_aes` | 1 | 172 |
| `opencores_ethernet` | 6 | 128 |
| `opencores_jpeg` | 3 | 349 |
| `orfs_gcd` | 1 | 34 |
| `pwm256` | 1 | 9 |
| `spi` | 1 | 25 |
| `uart` | 1 | 79 |

The release contains one row per register bit, with four feature-view references, labels, family IDs, and provenance. Four representations and many paths do not create additional independent targets. CIC5 and the JPEG family together account for 661 of 1,304 bits; later evaluation should report per-design/family results as well as pooled errors.

The [inventory](results/task2_collection.json) reports every design and explicit exclusion categories. The [execution record](results/task2_execution.json) records the budget and completed runs. Work began at 03:21:45 UTC; the repair gate passed before 03:26:45. The first pass validated all labels by 03:46:29. Final review found a missing environment component in the per-artifact cache key, so the collection was regenerated with lockfiles and actual Python/package versions recorded. Final release validation completed at 04:12:12 UTC. All 266 numerical feature, label, and join tables are byte-identical to the first pass. The user removed the overall stopping deadline while the last design was finishing; no collection stage failed or timed out.

Superseded upstream outputs are retained under the server's `data/archive/20260925T032645Z-1617b16d/`. The first-pass reset-library data, inventories, and exact code are preserved under `data/archive/20260925T035331Z-d071168e/`; original experiment archives and Git history remain available. No previously unproven artifact was relabeled as passed: new mappings were generated and checked. The conditional `async2sync` diagnostic never substitutes for the required proof.

## Task 3: Training and analysis — initial and follow-up runs complete

The modeling discussion selected a tree weighting comparison and two neural
comparisons: smooth-max versus hard-max path training, then learned versus equal
representation mixing under smooth-to-hard training. All neural conditions use
all four BOG views and hard-max path pooling at inference. The resulting five
learned configurations accompany training-median and direct-SOG references. Explicit
residual prediction was dropped to limit scope: a sufficiently expressive direct
model can represent the correction, although residual training could still offer
optimization or inductive-bias benefits. This is a design choice, not a measured
negative result. The [experiment scratchpad](task3-experiment-plan.md) records the
rationale, controls, remaining choices, and shared prerequisites for running the
two tracks concurrently. No modeling results are claimed yet.

Following authorization to prepare and launch unattended training, the 6/2/2
family split is frozen: 716 training, 337 validation, and 251 test register bits.
The scratchpad specifies feature inputs, matched protocols, and macro-design MAE
in ns as the primary metric. It documents the
finite-temperature downward bias of normalized log-sum-exp, the distinction
between family-balanced training and design-macro evaluation, and the limited
generalization evidence available from two test families. A separate modeling
uv environment preserves Task 2 environment fingerprints. Fifteen modeling tests
pass, alongside the original 20 tests and read-only revalidation of all 19
designs. A persistent non-root service executes the fixed experiments and saves
epoch/iteration histories, intermediate diagnostics, checkpoints and predictions.
Model selections are frozen using validation data before the common test stage.
The [runbook](task3-runbook.md) documents status and recovery; the
[launch record](results/task3_launch.json) records configuration and source hashes.
The original run completed all 11 learned runs and the common test stage without
a service restart. Test macro-design MAE was 0.150715 ns for direct SOG,
0.185438 ns for T0, 0.177099 ns for T1, and 0.160150 ns for N1 averaged across
its three seeds. The learned models did not establish an aggregate advantage
over SOG on this two-family test. Smoothing improved all three paired N1 versus
N0 comparisons; this is distinct from outperforming the SOG reference.

Preparation identified four valid zero-gate input-to-register paths whose
gate-output fanout/capacitance sample sets are empty. These receive an explicit
empty-set indicator and zero placeholders in the modeling inputs, identically
across conditions; other missing values remain errors. Task 2 tables, labels and
eligibility remain unchanged. After train-constant removal there are 228 tree
inputs and 33 inputs per path for the shared representation-conditioned MLP.

### Exploratory follow-ups

After inspecting those results, the user approved training-only affine SOG
calibration and SOG-only N1 with the same three seeds, architecture, preprocessing,
batch ordering and smooth-to-hard schedule. The original split was retained.
These are exploratory repeated evaluations of an already-inspected test set,
not fresh untouched-test evidence. Original model and Task 2 artifacts remain
unchanged. The [follow-up runbook](task3-followup-runbook.md) documents the protocol.

All four follow-up runs and evaluation completed successfully with zero service
restarts. C0 calibration scored 0.184546 ns macro-design MAE versus direct SOG's
0.150715 ns. SOG-only N1 averaged 0.176066 ns versus four-view N1's 0.160150 ns:
two paired seeds worsened and one improved. Neither proposal improved the primary
aggregate metric. These observations do not prove calibration or single-view
learning ineffective in general. Full [metrics](results/task3_followup_metrics.json)
and [execution verification](results/task3_followup_execution.json) are published;
all checkpoints, predictions and 600 neural curve epochs are saved on the server
and in a hash-verified local backup.

### Exploratory family cross-validation and context ablation

The approved four-fold study completed all 40 learned runs and 7,200 neural
epochs across 17 development designs (eight families, 1,053 register bits).
AES and UART were excluded from every new fold. Each fold refitted preprocessing
using training families only. N0, N1, and N1-NoContext used paired seeds and
fixed epoch-200 evaluation; all final models were frozen before evaluation.
The ablation zeros retained normalized global design quantities while preserving
path/cone features and identical input dimensions and initialization.

| Model | Macro-design MAE (ns) | Pooled MAE (ns) |
|---|---:|---:|
| median | 0.311723 | 0.495680 |
| SOG | 0.175497 | 0.270107 |
| T1 | 0.121225 | 0.264413 |
| N0 | 0.154636 | 0.406342 |
| N1 | 0.174866 | 0.506248 |
| N1-NoContext | 0.134506 | 0.397097 |

Neural entries average three separately scored seeds. Primary MAE averages over
all 17 out-of-fold designs, not equally over folds. These primary and pooled
metrics weight the dataset differently; both are reported. Families are the
relevant generalization units, folds share training data, and this exploratory
study does not restore an untouched test set.

Execution had zero failures or restarts. The complete 331-file package was synced
locally and hash-verified, including all checkpoints, training curves, batch
losses, and 12,636 unique model/seed/register predictions. The
[summary](results/task3_generalization_summary.md),
[full metrics](results/task3_generalization_metrics.json),
[execution audit](results/task3_generalization_execution.json), and
[runbook](task3-generalization-runbook.md) document the outcome. Task 4 interpretation
is reserved for the subsequent reflection discussion.

## Task 4: Reflections — ongoing

The sequential [decision log](decisions.md) records choices, rejected alternatives, observed failures, and verification. Future work includes stronger equivalence coverage, broader independent design families, sensitivity to constraints and sampling, physical timing labels, and commercial-tool comparisons if access becomes available. These are proposals, not completed experiments.

## Reproduction

Follow the [Task 2 runbook](task2-runbook.md), using the [Task 1 environment setup](task1-runbook.md). The refreshed [GCD walkthrough](../notebooks/01_gcd_walkthrough.ipynb) explains the feature views. Machine-readable results are in `docs/results/`; generated data are excluded from Git.
