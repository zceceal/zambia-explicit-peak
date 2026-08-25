# Results

Model outputs are gitignored — the full set is about 11 GB of per-settlement CSVs.

Each run writes one CSV per arm, plus a technology-split summary and a config log recording exactly
which parameter values produced it.

Naming follows `YYYY-MM-DD_<run>_<arm>.csv`. For example `2026-08_final_lcoe_R1_n20.csv` is the
canonical post-index-fix run, R1 (explicit-peak) arm, central `N_mid = 20`.

See `docs/01_pipeline.md` for which columns to read, and for the reporting caution that matters
most: use the 2030 columns. (An earlier version of this note also said to compare lifetime cost
rather than capital; that no longer holds — post-fix, capital and lifetime cost move together.)
