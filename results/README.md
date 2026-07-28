# Results

Model outputs are gitignored — the full set is about 11 GB of per-settlement CSVs.

Each run writes one CSV per arm, plus a technology-split summary and a config log recording exactly
which parameter values produced it.

Naming follows `YYYY-MM-DD_<run>_<arm>.csv`. For example `2026-07-01_grid3_lcoe_R1_n20.csv` is the
GRID3 spine, R1 (explicit-peak) arm, central `N_mid = 20`.

See `docs/01_pipeline.md` for which columns to read, and for the two reporting cautions that matter
most: use the 2030 columns, and compare lifetime cost rather than capital.
