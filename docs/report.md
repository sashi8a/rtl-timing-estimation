# Research report — work in progress

## Task 1: Data collection and feature extraction

The objective is register-level arrival-time regression. Four restricted-library Boolean operator graphs (SOG, AIG, AIMG, XAG) provide structural and timing features. BOG arrival times and ranks are inputs; they are not the target-circuit labels or a separate ranking objective.

The retained collection contains 19 designs across 10 families, each with four BOG representations. DCT was deferred after a long ABC synthesis run; its configuration is preserved separately. This remains within the requested approximately 20 designs.

Design sources and dependencies are pinned in `data/manifests/designs.json`. The collection mixes arithmetic/control, communication, signal-processing, and cryptographic blocks. Related Ethernet and JPEG blocks share family IDs. The effective diversity is smaller than the number of designs; later splits must keep entire families together. Complexity is measured by synthesized register bits, combinational operators, and graph depth, rather than source lines that depend on formatting and coding style.

The implementation adapts RTL-Timer's synthesis sequence and aggregation definitions to OpenSTA reports. Exact correspondence and deviations are in [the feature contract](task1-features.md); provenance and licensing are in [attribution](attribution.md). The pinned ORFS container and locked uv environment make tool and package choices explicit.

Generated endpoint, path, and design tables preserve named columns. Critical paths are queried per endpoint and per transition. Seeded random topology candidates are checked against actual timing paths, and duplicate routes are removed. Empty or untimed data remain explicit. Raw reports, source hashes, constraints, and formal-check logs are retained on the compute server.

### Measured Task 1 results

| Check | Result |
| --- | --- |
| Retained designs / families | 19 / 10 |
| Completed and validated BOG runs | 76 / 76 |
| Register bits across designs (one representation each) | 1,304 |
| Register endpoints across four representations | 5,216 / 5,216 timed |
| Retained path-feature rows | 84,184 |
| Register bits per design | 4–312 |
| Combinational operators per representation | 54–6,689 |
| Cross-representation endpoint identities | Agree for all 19 designs |
| Formal mapping checks | 40 passed; 36 unproven |
| Unit tests / lint | 12 passed / clean |
| Repeated GCD feature extraction | All 12 Parquet tables byte-identical |

These are extraction and consistency results, not prediction-accuracy results. Path rows and the four representations are correlated views, not independent training examples. The full inventory, validation records, and final input/output hashes are in `docs/results/`.

### Observed limitations

- OpenSTA required LEF metadata and rejected signed net declarations in mapped gate netlists. A narrow declaration normalization preserves the raw export; equivalence checks use the normalized netlist.
- Some equivalence checks remain unproven, particularly for asynchronous-reset designs. Successful extraction does not resolve those proof obligations. The proof itself covers the Yosys pre-mapping elaboration, not the original frontend translation.
- No placement or extracted wire parasitics are used in Task 1. These are restricted-library BOG features under stated constraints, not signoff timing.
- GCD originally kept ORFS constraints. It has now been harmonized to the common experimental SDC and all four feature views regenerated before label generation.
- Random backward walks are not uniform over all paths. The 32-path cap and deduplication are documented local choices.
- The dataset is small and contains related blocks and small state machines. Register rows are not independent samples for estimating design generalization.

No commercial-tool comparison has been performed. Differences in commercial versus open-source timing accuracy remain hypotheses, not measured conclusions.

## Task 2: Label generation — two-design pilot complete

The target is maximum rising/falling data arrival at each retained mapped register bit's D pin, in ns. The target circuit is synthesized independently from RTL using a broader Nangate45 gate set at the same corner and SDC as the features. These are post-synthesis labels with no placement or extracted wire parasitics; they are not post-route/signoff accuracy claims.

| Design | Labeled bits | Matches across four views | Target proof | Training-eligible bits |
| --- | ---: | ---: | --- | ---: |
| GCD | 34 / 34 | 136 / 136 | Passed | 34 |
| TIMER32 | 65 / 65 | 260 / 260 | Passed | 0 |

All 99 labels agree with direct pin-arrival queries and reported path-increment sums. Six low/middle/high examples were inspected; [manual observations](task2-pilot-observations.md) explain the source paths and alias identities. Endpoint matching uses unique, one-to-one RTL alias intersections, never timing similarity. Feature/label SDC fingerprints must match. Exact outputs and examples are in `docs/results/task2_pilot.json` and `task2_pilot_review.md`.

TIMER32 and PWM256 SOG diagnostics remain unproven under deeper clock-aware induction, but pass under a synchronous-reset abstraction. This narrows the observed issue without proving unrestricted asynchronous equivalence. TIMER32's broader-library target mapping passes the original check; its restricted BOG checks still block training eligibility. See the diagnostic results and [inclusion policy](task2-label-contract.md).

The conservative feature-proof gate currently admits 10 of 19 designs across 8 families for further consideration; target proofs and coverage are still required. Resolve the 9 quarantined designs or explicitly approve a narrower experimental scope before training. Collection-wide label generation remains pending. A passing Yosys induction check assumes state alignment and is not a reset-reachability or original-RTL frontend proof.

## Task 3: Training and analysis — pending

Agree on family-based train/validation/test membership before tuning. Start with a simple arrival-time baseline, then test a motivated modeling change. A full reproduction of RTL-Timer is optional. Choose metrics after inspecting target-label coverage and distribution; report per-design behavior alongside aggregate errors.

## Task 4: Reflections — ongoing

The sequential [decision log](decisions.md) records choices, rejected alternatives, observed failures, and verification. Future work includes stronger equivalence coverage, broader independent design families, sensitivity to constraints and sampling, physical timing labels, and commercial-tool comparisons if access becomes available. These are proposals, not completed experiments.

## Reproduction

Follow [the runbook](task1-runbook.md). Inspect [the GCD walkthrough](../notebooks/01_gcd_walkthrough.ipynb) before moving to target-label generation. Machine-readable results are in `docs/results/`; generated data are excluded from Git.
