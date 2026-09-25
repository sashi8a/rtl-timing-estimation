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
