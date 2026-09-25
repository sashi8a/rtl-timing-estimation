# Data

Store small, versioned provenance manifests in `manifests/`. Generated data is ignored by Git. Future manifests should identify source revisions, licenses, top modules, parameters, clock/reset interfaces, and family relationships relevant to dataset splitting.

No dataset has been collected yet.

The Task 2 release lives in `releases/task2/registers.parquet`, with one eligible
register-bit record per row, and `releases/task2/manifest.json`. Each row references
all four feature views plus the target label/provenance. The committed inventory
is `docs/results/task2_collection.json`; follow `docs/task2-runbook.md` to reproduce
or resume generation. Superseded outputs are retained under `archive/<run-id>/`
on the compute server. Generated data and raw RTL remain excluded from Git.
