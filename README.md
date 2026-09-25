# RTL Timing Estimation

Research assessment: predict fine-grained register timing from RTL using open-source tools, and evaluate model choices on held-out design families.

## Status

Task 1 feature extraction is implemented for **19 designs across 10 families**, with all four BOG representations (76 runs). DCT was deferred because of synthesis runtime; the exclusion is documented. See [the measured inventory](docs/results/task1_inventory.csv), [validation results](docs/results/task1_validation.json), and [working report](docs/report.md).

The two-design Task 2 pilot now has 99 register-bit labels and complete matches to all four BOG views. GCD is training-eligible under the documented proof gate; TIMER32 remains excluded because its BOG mapping proofs are unresolved. No models have been trained. Our prediction objective is arrival-time regression; BOG-derived ranks are input features only. Some mapping-equivalence checks remain unproven and must not be presented as passed.

## Objectives

- Collect approximately 20 diverse RTL designs with documented provenance.
- Generate model features and register timing labels using open-source tools.
- Establish a baseline and test a motivated improvement.
- Evaluate generalization on held-out designs and document limitations.
- Provide reproducible generation, training, and evaluation commands.

## Project structure

| Path | Purpose |
| --- | --- |
| `configs/` | Design manifests and experiment settings |
| `src/rtl_timing/` | Reusable pipeline and model code |
| `scripts/` | Data generation, training, and evaluation entry points |
| `notebooks/` | Small experiments and explanatory walkthroughs |
| `tests/` | Mapping, extraction, and evaluation checks |
| `docs/` | Problem formulation, decision log, and report |
| `third_party/` | Pinned upstream references with attribution |
| `data/` | Source manifests and generated datasets |
| `runs/` | Experiment configurations, metrics, logs, and plots |

## Workflow and reproducibility

Notebooks should run top-to-bottom and import reusable logic from `src/rtl_timing/`. Scripts will run the same code for reproducible experiments.

Each experiment should record its configuration, random seed, code revision, tool versions, dataset identity, and split identifiers. Meaningful decisions belong in [the decision log](docs/decisions.md); findings and limitations belong in [the report](docs/report.md).

Generated datasets, model artifacts, and run outputs are excluded from Git by default. Commit small provenance manifests under `data/manifests/` and reproduction instructions. Artifact distribution will be decided after measuring output sizes.

## Reproduction

See [Task 1 runbook](docs/task1-runbook.md) for the pinned container, uv environment, generation commands, and verification. See [feature correspondence and deviations](docs/task1-features.md) for exact definitions. Start with [the GCD walkthrough](notebooks/01_gcd_walkthrough.ipynb).

## References

- [RTL-Timer paper](https://arxiv.org/abs/2403.18453)
- [RTL-Timer reference implementation](https://github.com/hkust-zhiyao/RTL-Timer)
- [OpenROAD Flow Scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)

The synthesis sequence and feature aggregation adapt upstream code; see [attribution](docs/attribution.md). Reference assets are fetched at pinned revisions with original notices retained.

See [the label contract](docs/task2-label-contract.md), [Task 2 runbook](docs/task2-runbook.md), and [six inspected pilot examples](docs/results/task2_pilot_review.md).
