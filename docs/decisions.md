# Decision log

Record meaningful decisions as they are made. Unresolved choices are not commitments.

## 2026-09-24: Repository and experiment organization

**Decision:** Use a private assessment repository. Use notebooks for exploration and explanation, and Python modules/scripts for reusable, reproducible work.

**Reason:** Experiments must be understandable and repeatable without duplicating pipeline logic in notebooks.

**Alternative considered:** Notebook-only implementation, which makes shared logic and unattended reproduction harder to maintain.

**Verification:** Notebooks will run top-to-bottom and call the same implementation as scripts. Document verified commands with each implemented stage.

**Status:** Organization agreed; pipeline implementation pending.

## Template for future entries

- Date and decision
- Motivation and alternatives
- Expected consequence
- Verification method and evidence
- Status: proposed, accepted, or superseded

## 2026-09-25: Arrival-time regression and reference feature compatibility

**Decision:** Predict arrival time. BOG-derived ranks are input features only. Preserve named paper features and record all adaptations in `task1-features.md`.

**Reason:** The assessment targets register timing, and the user explicitly excluded a separate ranking objective.

**Verification:** Task 1 does not load any target labels; ranks are computed only within each design/BOG from BOG timing.

## 2026-09-25: Server, uv, and pinned EDA container

**Decision:** Execute EDA on the supplied Linux server using the ORFS image digest in `configs/eda.json`. Python 3.12.6, uv 0.11.19, `.venv`, and `uv.lock` provide the Python environment.

**Reason:** The server has 8 logical CPUs, 31 GiB RAM, working sudo Docker, and an L40S for possible later training. No GPU is required for this feature pipeline. Avoid modifying Docker group permissions.

**Verification:** The locked Python environment was created on Mac and Linux. Yosys synthesis and OpenSTA through OpenROAD ran on GCD. The image's OpenROAD version string is `unknown`, so the immutable image digest is essential provenance.

## 2026-09-25: Shared names and path-aware extraction

**Decision:** Preserve Yosys names in both JSON and Verilog (`write_verilog -norename`). Exclude `$scopeinfo` metadata from hardware counts. Query endpoint rise/fall separately and retain every sampled path as its own record.

**Reason:** The pilot exposed automatic Verilog renaming that made JSON-derived timing queries miss cells. Upstream endpoint dictionaries overwrite repeated paths. Arrival and slack must not be conflated.

**Verification:** Explicit graph/report cell matching, sampled-pin sequence checks, and separate formal equivalence status. Path-statistic tests include zero values and direct register paths.

## 2026-09-25: Dataset scope and common collection constraints

**Decision:** The user approved a mix of functional blocks and larger designs. Screened 25 candidates and selected 20 for execution, grouped into 10 families across arithmetic/control, communication, signal processing, and cryptography. Related JPEG and Ethernet blocks must not cross a family-based train/test split.

**Reason:** Modest blocks make four-representation extraction practical while exposing different logic structures. This is a block-oriented dataset, not 20 unrelated full-chip designs; that limits claims of generalization.

**Constraints:** GCD retains its ORFS SDC for the pilot. Other candidates use explicitly recorded 10 ns clocks, 0.1 ns input/output delays, 0.01 ns input slew, 1 fF output load, and no reset case analysis. These are experimental conditions, not source designers' timing specifications.

## 2026-09-25: OpenSTA signed-net declaration compatibility

**Observation:** `div_su` synthesized successfully, but OpenSTA rejected a `wire signed` declaration in the fully mapped netlist.

**Decision:** Preserve the raw export and remove only signed qualifiers on wire/input/output declarations in the STA export. At this stage arithmetic is already represented by cells and explicit bit wiring. Test the transformation and run formal equivalence on the normalized export. Do not edit source RTL or remove arithmetic operators.

## 2026-09-25: Explicit incomplete proofs

**Observation:** The default SAT flow could not model asynchronous reset cells. Adding `clk2fflogic` allowed progress, but the timer's check still left two internal comparisons unproven while proving 63.

**Decision:** Retain `unproven` status and logs. Do not interpret failure to prove as either proof of a bug or proof of equivalence. GCD passes the updated flow. Record this limitation separately from successful feature extraction.

## 2026-09-25: Collection bookkeeping

**Observation:** Separate retry collectors could overwrite one shared status file, even when processing different designs.

**Decision:** Give each collector a unique status file. Build the final inventory from actual artifacts and validate every representation, including endpoint-ID agreement across representations. Avoid overlapping jobs for the same design. Preserve failed-run logs as diagnostic evidence.

## 2026-09-25: Report parsing performance

**Observation:** Profiling the parser showed almost all runtime in whitespace-heavy regular-expression matching.

**Decision:** Bound the expression to OpenSTA's numeric columns. All 34 GCD rising critical-path records were identical before and after the change, and parsing those records took about 0.023 seconds locally after the change. Reextract and validate the final collection with the optimized parser.

## 2026-09-25: Final collection size and DCT exclusion

**Observation:** The DCT MAC's ABC synthesis remained CPU-bound after more than seven minutes in the retry. This is a runtime observation, not evidence of invalid RTL.

**Decision:** Defer DCT and retain 19 designs across 10 families, consistent with the assessment's approximately-20-design request. Do not pad the collection with another related state machine solely to reach 20. Preserve its source configuration in `deferred_designs.json` and failed/interrupted artifacts on the server. Complete the remaining CIC representations with the faster, output-checked parser.

**Consequence:** Arithmetic diversity is reduced. Revisit DCT with a larger synthesis budget or a documented alternative ABC script in future work.

## 2026-09-25: Task 1 collection verification

**Observed:** All 76 retained representation runs passed artifact checks; all 5,216 endpoint rows were timed, and canonical endpoint identities agreed across representations for every design. The 19 designs contain 1,304 register bits when counted once each, and yield 84,184 retained path rows. Formal mapping checks passed for 40 runs and remained unproven for 36. All 12 GCD Parquet tables were byte-identical after repeated extraction. Eight unit tests and lint checks passed.

**Boundary:** This completes collection and feature extraction, with recorded proof limitations. No target-circuit labels or trained models exist. Review the walkthrough before planning Task 2.

## 2026-09-25: Target-label definition confirmed against assessment

**Decision:** Use maximum rising/falling data arrival at each retained mapped register bit's D pin, in ns, from an independently synthesized broader-library circuit. Include constrained primary-input and register-origin paths and retain source type. Do not substitute slack or BOG timing as the label.

**Evidence:** The reattached assessment explicitly describes synthesis followed by STA to obtain individual-register arrival times. It does not require placement or routing. The first target therefore uses cell-delay-only post-synthesis timing, with that limitation stated explicitly.

## 2026-09-25: GCD constraint harmonization

**Decision:** Replace the original GCD experiment's clock/latency/I/O conditions with the common collection SDC and regenerate all four views. Preserve the initial artifacts under `data/archive/task1_initial/gcd` on the server and the original configuration in commit `6623f62`.

**Reason:** A clock latency offset and different input conditions would confound comparisons. Feature and label joins now require identical SDC hashes. Both pilot designs were freshly regenerated with these fingerprints; older designs must be refreshed before label joins if their summaries lack them.

## 2026-09-25: Investigating unproven asynchronous mappings

**Observed:** TIMER32 and PWM256 SOG checks still leave their lowest counter bits unproven when clock modeling is moved before matching and when induction is increased to 16 steps with undefined-state modeling. Both pass after `async2sync`. TIMER32's broader-library target mapping passes the original clock-aware check.

**Interpretation:** This is evidence of sensitivity to mapping and clock/reset modeling. It is not a concrete behavioral counterexample and does not justify declaring every unresolved asynchronous design equivalent. `async2sync` assumes synchronized asynchronous signals and negative hold time. The existing induction checker also assumes state alignment; it does not prove reset reachability or original frontend correctness.

**Policy:** Preserve labels for audit, but mark rows training-eligible only after unique one-to-one alias matching, valid timing, matching feature/label constraints, a passing target mapping check, and passing checks for all four BOG mappings. Conditional diagnostics do not override the main statuses. This leaves 10/19 designs across 8 families past the feature-proof gate; target validation remains necessary. Resolve the 9 quarantined designs or explicitly reconsider scope before training.

## 2026-09-25: Two-design label pilot

**Observed:** GCD yields 34/34 labels and TIMER32 65/65, with all 396 feature-view matches unique and complete. All 99 selected arrivals agree with direct OpenSTA pin-arrival queries, and path increments sum to the reported arrivals. Six low/middle/high examples are retained for inspection. Both target mapping checks pass; TIMER32 remains ineligible for training because its BOG checks are unresolved.

**Implementation details that mattered:** The pinned `report_arrival` command does not support `>` redirection like `report_checks`; bracketed log sections are captured instead. Target mapping retains ordinary combinational gates and DFFs and explicitly excludes physical-only, latch, scan, tristate, clock-gating, and multi-output adder cells. Broader gate types are target-circuit metadata, not new BOG features. Twelve unit tests pass.

**Boundary:** This completes the agreed pilot, not collection-wide labeling, commercial-tool validation, or model training.
