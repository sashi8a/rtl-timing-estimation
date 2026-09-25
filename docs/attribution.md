# Attribution

The synthesis pass sequence in `src/rtl_timing/eda.py` adapts
`vlg2bog/scr_ys/run_ys_template.ys` from RTL-Timer revision
`206ff4078368c251d2fafaffcc648282c68316f1`.
Path feature aggregation follows `report_example/timing_path.py` at that revision,
with an OpenSTA parser and explicitly documented feature semantics.
See `RTL-Timer-LICENSE.txt` for the retained BSD-3-Clause notice.

Reference scripts and Liberty files are downloaded by `rtl-timing fetch`; original
notices are retained. Nangate library licensing is separate from the code license.
ORFS's `LICENSE_BUILD_RUN_SCRIPTS` applies to its scripts, not automatically to
every bundled RTL design. Design-specific provenance must be checked before redistribution.
