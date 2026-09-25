# Task 4 — evidence, limitations, and next steps

## What the project establishes

We built a reproducible pipeline from RTL to register-bit timing examples, validated 1,304 labels from 19 designs, and evaluated controlled learning interventions. The clearest engineering result is a complete, auditable dataset under explicitly limited timing conditions. The modeling result is conditional: trees and a neural context ablation helped on development-family cross-validation, while direct SOG remained strongest among configuration-level seed averages on the original AES/UART test.

The prediction is maximum rising/falling **data arrival at a mapped register bit's D pin**, in ns, under a common SDC. It is not slack, clock-to-Q alone, post-route delay, or a separate ranking objective. The assessment's fine-grained target is implemented at bit level; it is not a guarantee that every source-language register survives synthesis or can be matched in arbitrary RTL.

## 1. How good is the model, and where are its limitations?

### Preserve the distinction between the three studies

| Study | Evaluation population | Selection rule | What it can establish |
|---|---|---|---|
| Original experiment | AES key expansion and UART, 251 bits | Validation macro-design MAE selects epochs 170/180/190/200 | Performance on two held-out families under the original protocol |
| Calibration / SOG-only follow-ups | Same already-inspected 251 bits | Training-only calibration; original validation selection for neural runs | Exploratory evidence for two motivated follow-ups |
| Family cross-validation / context ablation | 17 development designs, eight families, 1,053 OOF bits; AES/UART excluded | Fixed epoch 200, no inner validation | Exploratory transfer across development families and a paired context ablation |

These studies use different evaluation populations and, for CV, a different checkpoint rule. Comparing absolute errors between their tables is not a controlled before/after improvement. CV does not undo prior inspection of the original test set. Folds share training data; register rows and seeds are not independent samples of new circuit families.

### Original experiment and follow-ups

Direct SOG achieved **0.150715 ns** macro-design MAE. T0 and T1 achieved **0.185438** and **0.177099 ns**. Mean neural MAEs were **0.176742** (N0), **0.160150** (N1), and **0.171917 ns** (N2). Some individual seeds beat SOG, but selecting those seeds after test inspection would be misleading.

Family/design balancing improved T1 over T0 on this test. Smooth-to-hard training improved all three paired N1-versus-N0 seeds. Learned representation mixing did not improve N2 over N1 in any of the three paired seeds. Neither result establishes that a learned method reliably beats SOG on unseen families.

Training-only affine calibration worsened SOG's primary error to **0.184546 ns**. SOG-only N1 averaged **0.176066 ns**, worse than four-view N1; two paired seeds worsened and one improved. These are negative/mixed observations for these implementations and splits, not proofs that calibration or single-view models can never work. Residual learning was dropped by scope; it was **not** tested and rejected experimentally.

### Cross-validation and the context ablation

| Method | Macro-design MAE (ns) | Pooled register MAE (ns) |
|---|---:|---:|
| Training median | 0.311723 | 0.495680 |
| Direct SOG | 0.175497 | 0.270107 |
| Balanced tree T1 | **0.121225** | **0.264413** |
| Hard-max MLP N0 | 0.154636 | 0.406342 |
| Smooth-to-hard MLP N1 | 0.174866 | 0.506248 |
| N1 without global context | 0.134506 | 0.397097 |

Neural entries average three separately scored seeds; they are not an ensemble. T1 reduced primary error by approximately **31%** against SOG, but pooled error by only **2%**. It beat SOG on 12 of 17 designs. This supports T1 as a useful simple candidate under this development-family protocol, not a universal winner.

Removing explicit global context reduced N1's primary error by approximately **23%**, with aggregate improvement for each paired seed. It improved 10 of the 12 fold/seed primary comparisons; it was not uniformly beneficial. Its primary seed SD was 0.012840 ns, compared with N1's 0.035826 ns. These are observed optimization spreads, not confidence intervals over new families.

Smoothing's effect did not transfer consistently: N1 had slightly better primary error than N0 in two seeds but a much worse third seed, producing a worse mean. The original positive smoothing result therefore needs the qualification “on the original split,” not “smoothing improves generalization.”

**Why the primary and pooled results disagree:** macro-design MAE gives each design equal weight; pooled MAE gives each bit equal weight. The 272-bit JPEG `div_su` design has mean MAE **0.0991 ns** for SOG, **0.2979 ns** for T1, and **0.9275 ns** for N1-NoContext. Its large neural errors have substantial influence on pooled metrics. No neural condition beat SOG on pooled OOF MAE. We should report that limitation alongside the better macro-design scores.

**Plausible explanation, not demonstrated mechanism:** global size/context quantities may encourage design-specific shortcuts that transfer poorly. The matched masking experiment supports the effect of removing those quantities in this setup; it does not identify shortcut learning as the cause or prove that remaining path/cone features contain no design identity. Likewise, the divider failure identifies where performance breaks, not whether missing path coverage, extrapolation, representation mismatch, or another mechanism caused it.

### Training-fit diagnostic

At epoch 200 in the original experiment, neural training macro-design MAE ranges from approximately **0.010–0.015 ns**, while validation macro-design MAE ranges from **0.233–0.297 ns** across models/seeds. The saved curves show a large train/validation gap. This is evidence of limited transfer despite a good training fit; it does not isolate overfitting from family/domain shift as the sole cause. It argues against assuming that simply training longer will solve the problem. These are fixed-epoch diagnostics, separate from validation-selected test scores.

### Broader modeling limits

- Only ten source families in the full collection; the original test has two. Six related Ethernet blocks do not provide six independent projects.
- Path rows and four views are correlated inputs to one bit label; 84,154 path rows do not mean 84,154 independent targets.
- Random topology walks are capped and nonuniform. They are not exhaustive path coverage or functional sensitization proofs.
- Path MLP scores are latent values learned through endpoint supervision. They have not been validated as physical delays of individual target-circuit paths.
- The same typical cell library and timing engine generate BOG timing features and target labels. SOG's strength may partly reflect this shared construction; cross-library/tool transfer has not been measured.
- No end-to-end speedup versus target synthesis/STA was benchmarked. Features still require restricted synthesis and STA. We cannot claim a practical acceleration merely because MLP inference is fast.
- These results concern absolute arrival prediction, not downstream synthesis improvement, timing closure, signal ranking, or post-route signoff.

## 2. What would improve the work with more time/resources?

Prioritize additional independent evidence over another quick sweep on the same examples.

| Priority | Proposed next step | Motivation / expected benefit | What would count as evidence |
|---|---|---|---|
| 1 | Add independent families and reserve a genuinely fresh test set before development | Reduce dependence on the current few families | Consistent family-level error and coverage on previously unused projects |
| 2 | Investigate `div_su` with path/feature-range diagnostics and sampled-route coverage | Understand the largest transfer failure before changing the network | A measured failure mechanism and an intervention tested on new held-out families |
| 3 | Test path sampling sensitivity and, if feasible, graph/cone representations | Reduce missed-route and fixed-summary limitations | Controlled coverage/runtime tradeoff and improved generalization, not just training fit |
| 4 | Study context regularization, feature restrictions, or residual prediction under a fresh protocol | Follow up the masking result without assuming its cause | Matched controls on fresh families; residual prediction remains an untested option |
| 5 | Extend labels across corners, constraints, and physical-design stages | Separate robustness to logical structure from robustness to timing conditions | Explicitly conditioned predictions with measured out-of-condition errors |
| 6 | Benchmark wall time and memory for feature generation, target STA, training and inference | Establish whether the method provides a useful workflow benefit | End-to-end cost/accuracy comparison on representative larger designs |

A larger MLP, more seeds, longer training, or a hyperparameter sweep could be studied later, but they do not by themselves fix small-family evidence, omitted physical effects, or the divider transfer failure. More seeds quantify optimizer variability; more independent families address generalization evidence.

## 3. How could the open-source flow affect labels and conclusions?

### Observed facts and consequences

| Observed in this project | Consequence / boundary |
|---|---|
| Post-synthesis timing, ideal clock, no placement/CTS/extracted wire parasitics | Labels describe this cell-based timing problem, not physical signoff. Slew/load effects from the cell library are still present. |
| One common clock/constraint recipe and Nangate45 typical corner (25 °C, 1.1 V) | Conclusions are conditional on these conditions; no multi-corner or multi-clock robustness was tested. |
| LEF metadata was needed by OpenROAD; signed gate-netlist declarations needed narrow normalization | Integration compatibility required explicit handling. Reading LEF did not perform placement. Raw exports were preserved and normalized netlists checked. |
| 36 original BOG mapping checks were unproven; adding dedicated reset/set cells resolved them under the unchanged checker | Library vocabulary affected provability in this collection. The experiment is repair evidence, not a universal root-cause diagnosis. |
| Formal checks compare mapped netlists against Yosys pre-mapping elaboration, after state alignment | They do not validate original frontend translation or establish reset-sequence reachability. |
| Rise/fall reports, direct pin arrivals, and increment sums agree within recorded tolerances | Supports extraction/query consistency inside the same STA engine; these are not independent timing-engine measurements. |
| Primary-input paths can be critical; reset was not forced inactive | Arrival depends on input constraints. This is data-path timing, not reset recovery/removal analysis or a proof that every STA path is sensitizable. |
| Broader target mapping still filters supported cell classes; ABC receives no delay target | The target is a controlled mapping/STA flow, not an unrestricted commercial implementation or timing-closure flow. |
| All retained bits passed identity, coverage, units, hash and proof gates | No unresolved retained examples were silently filled or promoted into training. DCT's runtime-based exclusion remains a dataset limitation. |

### Hypotheses requiring new measurements

Commercial synthesis could map, optimize, size, or buffer the same RTL differently. Timing engines could differ in supported constructs, constraint interpretation, or delay calculation settings. Physical interconnect and clock effects could change critical paths and absolute arrivals. These are reasons a commercial/post-route reference might differ; **we did not measure those differences**.

We cannot conclude that OpenSTA labels are less accurate simply because the tool is open source. The defensible statement is that our labels are internally checked for a specific model and flow, and their agreement with commercial or silicon timing is unmeasured. A comparison would first align netlist, library/corner, constraints, parasitics, and report definitions; otherwise tool differences would be confounded with different inputs.

## Decision to stop experiments

No mandatory experiment remains incomplete. All 55 fitted runs across the three studies finished: 54 tree/neural runs and one affine calibration fit, including 9,600 neural epochs. Task 2 validation and all 52 existing tests passed in the recorded execution. We stop model development here, preserve negative/mixed outcomes, and focus on explaining and auditing the completed work. There is no final all-data deployment retrain or claim of a production-ready model.

Evidence: [current report](report.md), [complete results index](delivery-index.md), [feature contract](task1-features.md), [label contract](task2-label-contract.md), and [sequential decisions](decisions.md).
