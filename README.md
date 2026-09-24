# RTL Timing Estimation

Research assessment: predict fine-grained register timing from RTL using open-source tools, and evaluate improvements over an adapted RTL-Timer baseline.

## Status

Repository scaffold only. Data generation, feature extraction, models, and evaluation are not implemented yet. Toolchain, dependencies, timing target, and experimental protocol will be chosen after reviewing the paper and reference implementation.

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

No executable pipeline exists yet. Setup instructions, pinned dependencies, and exact commands will be added alongside each implemented stage and verified before being documented as working.

## References

- [RTL-Timer paper](https://arxiv.org/abs/2403.18453)
- [RTL-Timer reference implementation](https://github.com/hkust-zhiyao/RTL-Timer)
- [OpenROAD Flow Scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)

Upstream code has not been imported. Any reused code will retain its attribution and applicable license notices.
