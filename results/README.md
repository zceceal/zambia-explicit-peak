# Results

Model outputs are gitignored — the full set is about 11 GB of per-settlement CSVs.

Each run writes one CSV per arm, plus a technology-split summary and a config log recording exactly
which parameter values produced it.

Naming follows `YYYY-MM-DD_<run>_<arm>.csv`. For example `2026-08_final_lcoe_R1_n20.csv` is the
canonical post-index-fix run, R1 (explicit-peak) arm, central `N_mid = 20`.

`results/summary/` holds the committed CSVs behind the reported numbers. Those written directly by a
script are `s14`, `s18`, `s19`, `s20`, `s21`, `s22`, `s23` and `check_mv_sources.py`; the rest are
copied from `data/onsset_outputs/` after the run that produced them.

See `docs/01_pipeline.md` for which columns to read: report the 2030 columns.
