# Task 2 pilot: label contract

## Target

For each retained mapped register bit, predict the maximum **data arrival time at its D pin**, in ns, over rising and falling endpoint transitions and eligible paths under the recorded SDC. Retain the two transition arrivals, winning path/startpoint, and raw report. This is neither slack nor clock-to-Q delay. Include register-origin and constrained primary-input-origin data paths; identify their origins explicitly. Recovery/removal timing on asynchronous reset pins is outside this target.

One RTL vector register therefore produces one label per retained bit. Registers optimized away, merged ambiguously, unmapped, or without a valid timed D path are coverage outcomes, never invented zero labels. Check the mapped endpoint inventory against the BOG/RTL-alias inventory and report exclusions before constructing joined examples.

## Circuit and conditions

The initial labels are **post-synthesis, cell-delay-only timing**: general-purpose Nangate45 cell mapping at the same typical corner as the BOG libraries; ideal clock; no placement, clock-tree synthesis, or extracted wire parasitics. Keep the BOG libraries restricted to their representation vocabularies. Generate target netlists independently from the same RTL elaboration, without reading BOG arrivals or ranks.

Use a common 10 ns clock, 0.1 ns input/output delay, 0.01 ns input slew, and 1 fF output load. The launch-clock reference is zero latency. Preserve reset as an input (no case analysis); this does not constitute reset recovery/removal analysis. Use these identical conditions for feature and target branches. Harmonize GCD and regenerate all four of its BOG timing feature sets before joining labels.

No delay target is passed to ABC in the pilot. Record this explicitly: this is technology mapping followed by STA, not a timing-closure experiment.

## Query and coverage checks

Query each D endpoint and each transition separately, avoiding global top-N report truncation. In this single-clock, common-reference flow, select the greater arrival. Verify direct arrival queries where supported by the pinned OpenSTA version; retain diagnostic differences instead of silently selecting slack as a label. Assert ns/fF units, finite arrivals for timed rows, unique endpoint identities, unambiguous one-to-one alias matches, and raw-report endpoint agreement.

## Pilot acceptance

Run GCD and TIMER32. Inspect low-, middle-, and high-arrival examples for each design, including source kind, endpoint identity, rise/fall selection, and raw report arithmetic. Label coverage, functional verification status, and training eligibility are separate fields. An unresolved mapping proof is not promoted to a pass by successful STA. No collection-wide label generation or model training is part of this pilot.

## References

- OpenSTA timing commands: https://opensta.readthedocs.io/en/latest/Commands/
- Yosys induction proof semantics: https://yosyshq.readthedocs.io/projects/yosys/en/0.47/cmd/equiv_induct.html

The reattached assessment was read in full. Its introduction explicitly describes synthesis followed by STA to retrieve register arrival times; it does not require a physical-design timing stage.

## Functional inclusion policy

Keep every successfully generated label and mapping record for audit. Mark a joined row training-eligible only when its alias match is unique and one-to-one, the target D pin is timed, the target mapping check passes, and all four feature-branch mapping checks pass. Reject a join when the recorded feature SDC hash is absent or differs from the label SDC hash; regenerate the affected features rather than assuming compatibility.

The existing Yosys `equiv_induct` result is an inductive check after state alignment, not proof of reset-sequence reachability or original-RTL frontend correctness. The pilot policy retains that explicit proof boundary. Diagnostic `async2sync` passes do not change eligibility: they assume clock-synchronized asynchronous signals and negative hold time, and therefore do not settle unrestricted asynchronous behavior.

Representative TIMER32 and PWM256 SOG checks remain unproven after moving clock modeling before matching and after increasing induction depth to 16 with undefined-state modeling. Both pass under `async2sync`. This is evidence that proof results depend on the clock/reset model; it is not a counterexample or a general diagnosis of every unresolved design. TIMER32's broader-library target mapping passes the original clock-aware check, further narrowing the observed issue to the restricted mapping/proof combination.

Across Task 1, 10 of 19 designs (8 families) pass all four feature mapping checks. The other 9 remain quarantined by this default policy. Target checks are still required for each design before training. For the pilot, GCD contributes 34 eligible register bits; TIMER32's 65 labeled bits remain available for inspection but are excluded from training.

References for the diagnostic assumptions:
- https://yosyshq.readthedocs.io/projects/yosys/en/v0.68/cmd/index_formal.html
- https://yosyshq.readthedocs.io/projects/yosys/en/0.44/cmd/async2sync.html
