# Results

Model outputs are gitignored — About 11 GB for every variant; the four central solves and the 2050 endpoint that the paper reports are about 3 GB, and are the set the paper's Data availability statement refers to.

Each run writes one CSV per arm, plus a technology-split summary and a config log recording exactly
which parameter values produced it.

Naming follows `YYYY-MM-DD_<run>_<arm>.csv`. For example `2026-08_final_lcoe_R1_n20.csv` is the
canonical post-index-fix run, R1 (explicit-peak) arm, central `N_mid = 20`.

`results/summary/` holds the committed CSVs behind the reported numbers. Those written directly by a
script are `s12a`, `s14`, `s18`, `s19`, `s20`, `s21`, `s22`, `s23`, `s24` and `check_mv_sources.py`;
the other thirteen are copied from `data/onsset_outputs/` by `s25_collect_summaries.py` after the run
that produced them.

See `docs/01_pipeline.md` for which columns to read: report the 2030 columns.
