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

## Task 3: Training and analysis — pending

The modeling discussion selected two controlled experiments: balanced training
weights for a compact tree model, and smooth-max versus hard-max path aggregation
for a small MLP, alongside a naive training-median arrival predictor. Explicit
residual prediction was dropped to limit scope: a sufficiently expressive direct
model can represent the correction, although residual training could still offer
optimization or inductive-bias benefits. This is a design choice, not a measured
negative result. The [experiment scratchpad](task3-experiment-plan.md) records the
rationale, controls, remaining choices, and shared prerequisites for running the
two tracks concurrently. No modeling results are claimed yet.

Agree on family-based train/validation/test membership before tuning. Start with a simple arrival-time baseline, then test a motivated modeling change. A full reproduction of RTL-Timer is optional. Choose metrics after inspecting target-label coverage and distribution; report per-design behavior alongside aggregate errors.

## Task 4: Reflections — ongoing

The sequential [decision log](decisions.md) records choices, rejected alternatives, observed failures, and verification. Future work includes stronger equivalence coverage, broader independent design families, sensitivity to constraints and sampling, physical timing labels, and commercial-tool comparisons if access becomes available. These are proposals, not completed experiments.

## Reproduction

Follow the [Task 2 runbook](task2-runbook.md), using the [Task 1 environment setup](task1-runbook.md). The refreshed [GCD walkthrough](../notebooks/01_gcd_walkthrough.ipynb) explains the feature views. Machine-readable results are in `docs/results/`; generated data are excluded from Git.
