# Task 1 feature contract and deviations

Prediction target: **target-circuit register arrival time** (Task 2 labels).
BOG-derived rank is an input feature only. No ranking model or loss is selected.

## Reference

RTL-Timer, Sections 3.2–3.3, Table 2: https://arxiv.org/abs/2403.18453
Code revision: `206ff4078368c251d2fafaffcc648282c68316f1`.

| Feature | Implementation | Difference or clarification |
| --- | --- | --- |
| Register/combinational/total counts | Mapped JSON cells, excluding `$scopeinfo` metadata | Avoids commercial power reports |
| Driving register count | Backward cone traversal, distinct source register cells | Primary inputs counted separately; constant branches stop traversal |
| Endpoint rank and percentile | Descending BOG arrival, average ties, normalized to [0,1], four groups | Explicit local convention; never derived from labels |
| Path arrival | OpenSTA report on restricted-library BOG | OpenSTA replaces PrimeTime; time unit ns |
| Path depth and operator counts | Unique combinational cells along reported data path | Replaces brittle report-length-minus-three heuristic |
| Fanout and capacitance | Output-pin loads, including launch Q/QN | Zero values retained; capacitance fF |
| Slew | Launch output, combinational outputs, endpoint D | Excludes clock pins and duplicate combinational inputs; time ns |
| Aggregates | Sum, mean, population variance, population standard deviation | Released code returns variance; paper mentions standard deviation; retain both |
| Random paths | Seeded backward walks, cap 32 additional paths per endpoint, count proportional to driving registers | Sampling algorithm and cap are explicit local choices, not claimed paper defaults |

## Path verification

Each sampled candidate retains its source pin and ordered combinational input pins.
OpenSTA queries constrain this sequence; returned paths must contain the sequence in order.
The query is performed separately for rising and falling endpoint transitions; retain the larger arrival.
A path that cannot be timed is rejected and counted. The output distinguishes topology candidates from verified timing paths.
Backward random walks are not uniform over all complete paths. They may undersample long or branching routes.

For critical paths, a single-clock flow with uniform launch reference is assumed. Rising/falling queries avoid selecting only the worst-slack polarity. Multiple capture/launch clocks and exception-rich constraints are outside initial support.

## Output tables

`endpoint_features.parquet`: design/representation, endpoint cell, canonical alias and all aliases, cone register/input counts, timing status, BOG arrival, BOG rank features.

`path_features.parquet`: design/representation, endpoint identity, path ID/kind, transition, ordered pins, arrival, depth, operator counts, load/slew statistics.

`design_features.parquet`: structural design counts and operator-type counts. `summary.json`: design size and extraction coverage. `endpoints.json`: graph identities and topology candidates. Raw synthesis/timing logs and path reports are retained.

A null alias or absent timed path is explicit. No timing labels are read by this pipeline. Target labels will be joined separately in Task 2.

## Collection constraints

GCD originally used its pinned ORFS SDC. Before the Task 2 pilot it was harmonized to the common conditions used by other designs: 10 ns clock, zero clock latency, 0.1 ns input/output delay, 0.01 ns input slew, and 1 fF output load. All four GCD feature sets were regenerated; original outputs are archived. Timing includes primary-input paths; reset is not silently forced inactive.

Restricted upstream Nangate45 libraries specify typical process, 25 C, 1.1 V, 1 ns and 1 fF units. No placement or extracted wire parasitics are used. OpenROAD requires Nangate45 LEF metadata to initialize its database; this does not imply placement or physical wire-delay estimation.

## Verification boundary

Formal checks compare mapped BOG behavior with Yosys's pre-mapping elaboration. This does not prove equivalence between original RTL and the frontend's elaboration. Any incomplete proof is reported as `unproven`, never as success.

The implementation must verify actual report units and endpoint coverage before declaring a dataset complete. Dataset-wide checks are recorded separately from the GCD walkthrough in `docs/results/task1_validation.json`.

Design net count uses distinct nonconstant Yosys bit-net identities, not declared RTL bus count. Sampled routes duplicating an already retained route are removed and counted. Startpoint type distinguishes primary-input and register-origin paths.
