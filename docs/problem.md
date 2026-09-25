# Problem formulation

## Assessment objective

Estimate timing for individual RTL registers. Build a dataset of approximately 20 diverse designs, generate labels with open-source tools, evaluate models on held-out designs, and investigate modeling choices with a simple baseline where useful. Reproducing the full RTL-Timer model is not a prerequisite.

## Initial vocabulary

- **RTL:** a description of registers and the logic that computes their next values.
- **Synthesis:** translation and optimization of RTL into a gate-level circuit.
- **Liberty library:** cell definitions and timing characteristics used by synthesis and timing analysis.
- **Static timing analysis (STA):** calculation of signal timing through a circuit under specified constraints.
- **Arrival time:** when a signal reaches an endpoint relative to the timing reference.
- **Required time:** the latest acceptable arrival under the applicable timing constraints.
- **Slack:** required time minus arrival time; negative slack indicates a violation.
- **Boolean operator graph (BOG):** a bit-level representation of logical operations and register endpoints.

## Conceptual data flow

RTL feeds two branches: a BOG branch produces model features, while a synthesized-circuit branch produces timing labels. Register endpoints must be matched between branches to form supervised examples.

## Decisions still open

Task 1 feature definitions, BOG libraries, collection constraints, and design sources are recorded in the feature contract and manifests. Arrival-time regression is the agreed objective. The Task 2 pilot now fixes the target as maximum D-pin data arrival after broader-library synthesis, under matching constraints and without extracted wire parasitics. Still open: resolving quarantined BOG proofs and the full labeling rollout; Task 3 baseline/model choice, family split membership, and metrics.

## Verification principles

Features must be available at prediction time without accessing target labels. Dataset provenance, mapping coverage, and exclusions must be recorded. Comparisons must use consistent labels and evaluation conditions. Separate observed results from hypotheses and untested ideas.
