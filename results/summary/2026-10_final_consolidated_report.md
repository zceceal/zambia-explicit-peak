# Final consolidated baseline: fixes, checks and master table (2026-10-24)

- **Branch:** `final-consolidated-fixes`, cut from `diesel-sensitivity-rerun-audit`.
- **Vendored OnSSET:** branch `final-consolidated-fixes`, commits `63a88d8`–`9eed67f`, recorded as
  `patches/onsset-final-consolidated-fixes.patch`.
- **Scope:** computational only. No `.tex`/`.bib` edits, nothing pushed, no paper wording.
- **Outputs:** prefix `2026-10_final_`, with manifest `results/summary/2026-10_final_manifest.csv`.
- **Unchanged:** the committed `2026-08_final`, `2026-09*` and `2026-10_mgfuel_*` files, and the
  shared `data/onsset_repo` (still at `cd64900`).

## 1. What the final baseline contains

The final baseline is the committed pipeline plus every confirmed fix. Each fix was hand-checked on
its own, on a real settlement of the corrected baseline, before being combined with the others.

| Fix | Where | Hand check |
|---|---|---|
| **Mini-grid fuel units** (`mg-fuel-units-fix`, `e92d1d9`) | `onsset_helpers.build_pv_hybrid_lookup` passes USD/L, not USD/kWh | id 46780: committed configuration charged 18,497.9 L × 0.6 = 11,099 USD/yr; correct 1.969 USD/L gives 36,423; code NPV = L × P × Σ1.08⁻ʸ exactly before and after (`2026-10_mgfuel_full_rerun_report.md`) |
| **s08 cache key** (`032a7dc`) | key = every input of the lookup table, including the mini-grid discount rate | LHS sample 141: old key reproduces the artefact value 81.0784; full key gives the clean rebuild 84.5602 exactly; central identical under all keys |
| **F-C** hybrid year 0 (`63a88d8`) | no fuel or O&M in year 0, which has no generation | id 46780 lookup entry: code = hand replica exactly (0.271526583); −0.0049 USD/kWh against charging year 0 |
| **F-B** hybrid investment (`42f9cf0`) | undiscounted, like every other technology. Chosen direction: grid, SA_PV, hydro and the paper's investment totals are all undiscounted outlays, so the hybrid is aligned to them, not the reverse | same entry: LCOE unchanged to 9 dp; investment 22,603 → 27,000 per 10 MWh (×1.1945) = undiscounted hand sum exactly |
| **F-A grid** (`2611cc0`) | grid generation cost per kWh generated: ÷ (1 − 0.15) in `get_lcoe` and `pre_electrification` | id 563: `Grid2030` +0.002294 exactly; generation term 0.015294 = 0.013/0.85; base-year grid settlement 9320: 0.013000 → 0.015294 |
| **F-A mini-grid** (`9eed67f`) | hybrid LCOE, investment and capacity × 1/(1 − 0.05) | id 46780: LCOE 0.530169, investment 619,077, capacity 115.17 kW = network + hybrid/0.95 exactly |

### Why F-A was fixed (Phase 1)

- **Egli et al. 2023, Methods.** "Adding an estimated average grid electricity **generation** cost
  to the LCOE of transmitting and distributing electricity", using "OnSSET v.1.0 from the Global
  Electrification Platform".
- **Egli et al. 2023, Table S8, Zambia.** `Grid Losses 0.15`, `GridGenerationCost (USD/kWh) 0.013`.
- **OnSSET documentation** (`docs/otherinputs.rst:87`). `GridPrice` is "The cost of which the
  national grid **generates** electricity".
- **OnSSET's code.** It has never divided by (1 − losses). The line was commented out with
  "REVIEW" from the first GEP commit (2019-05-27), relabelled "TODO" on 2020-02-27, and deleted
  unresolved on 2020-03-22.

The input is therefore per kWh generated, and charging it per delivered kWh is an acknowledged,
unresolved upstream inconsistency, not a documented convention. **Caveat:** Egli et al.'s and GEP's
published numbers use the same unfixed OnSSET, so the grid part of this fix trades strict
comparability with them for internal consistency. Detail:
`2026-10_audit_dimensional_consistency_report.md`, addendum.

## 2. Gates and checks

**Setup gate.** The isolated environment reproduced the committed `s06` outputs SHA-256-identically
before any fix (mg-fuel rerun).

**Final pipeline.** All 33 stages ran (the `REPRODUCING.md` stages plus `s12 2050only_ruralT2` and
`s26`) in 369 min of compute, with no failures. In-run gates passed against the final central result
(+44.2757 %, 33,701):

- `s09`: ΔLCOE within 1 pp, switches exact;
- `s11`: passes;
- `s26`: exact `s06` allocation.

**Per-settlement diff against the mg-fuel-only baseline.** This baseline differs from the final one
only by F-A, F-B and F-C. All 39 per-settlement outputs were compared:

- **Structure:** rows, columns, order, dtypes and `id` order identical in every file.
- **Columns:** no column changed outside the fixes' channels. `Off_Grid_Code` and `NewDist` moved
  only in rows whose mini-grid LCOE, grid route or technology moved; checked row by row.
- **SA_PV:** `SA_PV2030` and `SA_PV2050` unchanged in every file, since no fix touches stand-alone
  PV.
- **F-A grid isolated exactly:** every grid settlement whose route is unchanged moved by exactly
  `p/0.85 − p` for its variant's grid price. Min = max in every file: +0.0022941 at 0.013,
  +0.0088235 at 0.05, +0.0300 at 0.17, +0.0388 at 0.22, +0.0459 at 0.26 USD/kWh.
- **Mini-grids** (F-A mini-grid + F-B + F-C): LCOE +0.0068 USD/kWh median, investment +USD 38,428
  median, capacity ×0.936. The ×0.936 equals the 46780 hand check, 115.17 / 123.04.
- **Allocation:** the grid is slightly dearer, so 77 (R0) and 44 (R1) marginal grid settlements move
  to SA_PV, and 4–5 move the other way. In Tier 2 and 2050 Tier 2, a few dozen mini-grids move to
  SA_PV.

**Audit.**

- A before/after snapshot shows no committed or real data file added, removed or modified across
  the whole of this work, other than its own new `2026-10_*` outputs.
- The vendored `explicit-peak-thesis` branch is unchanged at `cd64900`.

## 3. Master table

**Column definitions.**

- **Committed:** the `2026-08_final` outputs in the examined thesis.
- **mg-fuel-only:** the mini-grid fuel-units fix only (`mg-fuel-units-fix`). Its Morris/LHS rows
  come from the clean full-key cache rerun (`2026-10_mgfuel_dsensfix_*`) and its OAT rows from
  `2026-10_mgfuel_dsens_*`.
- **Final:** this baseline. Every fix, `s08` with the full cache key, and `s26`.

**Notes on reading the table.**

- **Committed Morris and LHS** use the year-only cache, so diesel price is frozen and shows μ\* = 0,
  and the mini-grid discount rate is frozen at 0.08.
- **Discount_rate μ\* roughly doubles** (2.09 → 3.48) because the full key lets the mini-grid
  discount-rate channel act. It still ranks 5th.
- **Full-dataset LHS re-solve rows.** `s09` picks the P5/P50/P95 samples from its own run's LHS. The
  committed and mg-fuel runs re-solve samples 27 / 194 / 152; the final run re-solves 27 / **169** /
  152, so the final P50 row is a different sample.
- **No committed diesel OAT exists.** The diesel figures as written in the paper are listed
  separately after the table. They come from the 2026-10-19 follow-up and are superseded: they were
  computed on the pre-fix costing with the contaminated diesel-bin cache
  (`2026-10_mgfuel_diesel_sensitivity_rerun.md`).

| Section | Quantity | Committed `2026-08_final` | mg-fuel-only corrected | Final fully-corrected | Final − committed |
|---|---|---|---|---|---|
| Central result (2030, Tier 3, N_mid 20) | ΔLCOE % | +45.378 | +44.665 | +44.276 | -1.102 |
| Central result (2030, Tier 3, N_mid 20) | Energy-weighted LCOE R0 (USD/kWh) | 0.2757 | 0.2801 | 0.2826 | 0.0069 |
| Central result (2030, Tier 3, N_mid 20) | Energy-weighted LCOE R1 (USD/kWh) | 0.4008 | 0.4052 | 0.4077 | 0.0069 |
| Central result (2030, Tier 3, N_mid 20) | Investment to 2030 R0 (USD bn) | 15.579 | 16.331 | 16.637 | 1.058 |
| Central result (2030, Tier 3, N_mid 20) | Investment to 2030 R1 (USD bn) | 21.999 | 22.751 | 23.057 | 1.058 |
| Central result (2030, Tier 3, N_mid 20) | ΔInvestment % | +41.21 | +39.31 | +38.59 | -2.62 |
| Central result (2030, Tier 3, N_mid 20) | New capacity R0 (MW) | 2,664.4 | 2,882.1 | 2,882.1 | 217.7 |
| Central result (2030, Tier 3, N_mid 20) | New capacity R1 (MW) | 2,706.2 | 2,923.9 | 2,923.8 | 217.6 |
| Central result (2030, Tier 3, N_mid 20) | ΔCapacity % | +1.571 | +1.452 | +1.447 | -0.124 |
| Central result (2030, Tier 3, N_mid 20) | SA_PV→Grid switches | 33,665 | 33,669 | 33,701 | 36 |
| Central result (2030, Tier 3, N_mid 20) | Settlements changing technology | 33,665 | 33,669 | 33,701 | 36 |
| Central result (2030, Tier 3, N_mid 20) | Population switching (2030) | 430,292 | 430,328 | 431,680 | 1,388 |
| Central result (2030, Tier 3, N_mid 20) | Population switching (% of 2030) | 1.765 | 1.765 | 1.771 | 0.006 |
| Central result (2030, Tier 3, N_mid 20) | Tech split R0: grid | 32,058 | 32,057 | 31,985 | -73 |
| Central result (2030, Tier 3, N_mid 20) | Tech split R0: SA_PV | 236,843 | 236,844 | 236,916 | 73 |
| Central result (2030, Tier 3, N_mid 20) | Tech split R0: MG_PVHybrid | 1,625 | 1,625 | 1,625 | 0 |
| Central result (2030, Tier 3, N_mid 20) | Tech split R1: grid | 65,723 | 65,726 | 65,686 | -37 |
| Central result (2030, Tier 3, N_mid 20) | Tech split R1: SA_PV | 203,178 | 203,175 | 203,215 | 37 |
| Central result (2030, Tier 3, N_mid 20) | Tech split R1: MG_PVHybrid | 1,625 | 1,625 | 1,625 | 0 |
| Central result (2030, Tier 3, N_mid 20) | 2030 population on grid R0 | 15,299,039 | 15,299,015 | 15,297,357 | -1,682 |
| Central result (2030, Tier 3, N_mid 20) | MG_PVHybrid capacity (MW) | 366.2 | 583.9 | 583.7 | 217.5 |
| Central result (2030, Tier 3, N_mid 20) | MG_PVHybrid investment R0 (USD bn) | 1.408 | 2.161 | 2.466 | 1.058 |
| Central result (2030, Tier 3, N_mid 20) | Grid investment R0 (USD bn) | 4.332 | 4.332 | 4.329 | -0.003 |
| Central result (2030, Tier 3, N_mid 20) | SA_PV investment R0 (USD bn) | 9.839 | 9.839 | 9.841 | 0.002 |
| Central result (2030, Tier 3, N_mid 20) | Median grid LCOE R0 | 0.5387 | 0.5387 | 0.5398 | 0.0011 |
| Central result (2030, Tier 3, N_mid 20) | Median SA_PV LCOE R0 | 1.0476 | 1.0476 | 1.0476 | 0.0000 |
| N_mid sweep (s06) | ΔLCOE % at N_mid 10 | +29.988 | +29.516 | +29.265 | -0.723 |
| N_mid sweep (s06) | SA_PV→Grid at N_mid 10 | 32,209 | 32,213 | 32,253 | 44 |
| N_mid sweep (s06) | ΔInvestment % at N_mid 10 | +26.30 | +25.09 | +24.63 | -1.67 |
| N_mid sweep (s06) | ΔLCOE % at N_mid 50 | +66.091 | +65.054 | +64.483 | -1.608 |
| N_mid sweep (s06) | SA_PV→Grid at N_mid 50 | 34,342 | 34,344 | 34,374 | 32 |
| N_mid sweep (s06) | ΔInvestment % at N_mid 50 | +61.33 | +58.50 | +57.43 | -3.90 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 ΔLCOE % (N_mid 10) | -3.689 | -3.874 | -3.903 | -0.214 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 ΔLCOE % (N_mid 20) | +1.917 | +1.666 | +1.571 | -0.346 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 ΔLCOE % (N_mid 50) | +7.203 | +6.953 | +6.808 | -0.395 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 SA_PV→Grid (N_mid 10) | 9 | 9 | 10 | 1 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 SA_PV→Grid (N_mid 20) | 47 | 50 | 50 | 3 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 SA_PV→Grid (N_mid 50) | 298 | 303 | 294 | -4 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 ΔInvestment % (N_mid 10) | -8.08 | -8.56 | -8.75 | -0.67 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 ΔInvestment % (N_mid 20) | -2.64 | -3.20 | -3.46 | -0.81 |
| Rural Tier 2 (s07) and 2050 (s12) | Tier 2 2030 ΔInvestment % (N_mid 50) | +2.87 | +2.39 | +2.12 | -0.75 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 ΔLCOE % (N_mid 10) | +23.084 | +22.593 | +22.124 | -0.960 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 ΔLCOE % (N_mid 20) | +34.889 | +34.147 | +33.432 | -1.457 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 ΔLCOE % (N_mid 50) | +50.933 | +49.849 | +48.802 | -2.131 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 SA_PV→Grid (N_mid 10) | 29,941 | 29,941 | 29,957 | 16 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 SA_PV→Grid (N_mid 20) | 32,156 | 32,156 | 32,211 | 55 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 SA_PV→Grid (N_mid 50) | 33,016 | 33,016 | 33,069 | 53 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 ΔInvestment % (N_mid 10) | +9.22 | +8.82 | +8.18 | -1.04 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 ΔInvestment % (N_mid 20) | +17.81 | +17.05 | +15.81 | -2.00 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 3 ΔInvestment % (N_mid 50) | +29.50 | +28.24 | +26.18 | -3.32 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 2 ΔLCOE % (N_mid 20) | -0.224 | -0.346 | -0.374 | -0.150 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 2 ΔLCOE % (N_mid 10) | -4.051 | -4.081 | -3.997 | +0.054 |
| Rural Tier 2 (s07) and 2050 (s12) | 2050 Tier 2 ΔLCOE % (N_mid 50) | +3.573 | +3.372 | +3.235 | -0.337 |
| Robustness and convention variants | Fitted anchors (s17) ΔLCOE % | +44.811 | +44.107 | +43.723 | -1.088 |
| Robustness and convention variants | Fitted anchors (s17) SA_PV→Grid | 33,645 | 33,649 | 33,688 | 43 |
| Robustness and convention variants | Smooth capex curve (s15) ΔLCOE % | +23.701 | +23.336 | +23.136 | -0.565 |
| Robustness and convention variants | Smooth capex curve (s15) SA_PV→Grid | 23,046 | 23,051 | 23,081 | 35 |
| Robustness and convention variants | Monotone capex curve (s15) ΔLCOE % | +18.716 | +18.427 | +18.270 | -0.446 |
| Robustness and convention variants | Monotone capex curve (s15) SA_PV→Grid | 15,724 | 15,725 | 15,736 | 12 |
| Robustness and convention variants | Full reinvestment (s16) ΔLCOE % | +45.925 | +45.235 | +44.860 | -1.066 |
| Robustness and convention variants | Full reinvestment (s16) SA_PV→Grid | 33,627 | 33,631 | 33,686 | 59 |
| Robustness and convention variants | Single-household excluded (s23) ΔLCOE % | +43.607 | +42.908 | +42.525 | -1.082 |
| Robustness and convention variants | Single-household excluded (s23) SA_PV→Grid | 27,990 | 27,992 | 28,033 | 43 |
| Robustness and convention variants | Household size 4.5 (s18) ΔLCOE % | +43.576 | +42.888 | +42.527 | -1.049 |
| Robustness and convention variants | Household size 4.5 (s18) SA_PV→Grid | 32,845 | 32,839 | 32,895 | 50 |
| Robustness and convention variants | Household size 5.5 (s18) ΔLCOE % | +46.951 | +46.215 | +45.796 | -1.155 |
| Robustness and convention variants | Household size 5.5 (s18) SA_PV→Grid | 33,858 | 33,858 | 33,905 | 47 |
| Robustness and convention variants | Transformer-or-MV gate (s21) ΔLCOE % | +46.236 | +45.625 | +45.235 | -1.001 |
| Robustness and convention variants | Transformer-or-MV gate (s21) SA_PV→Grid | 33,367 | 33,371 | 33,408 | 41 |
| Robustness and convention variants | ZESCO-only MV layer (s22) ΔLCOE % | +45.719 | +44.851 | +44.449 | -1.270 |
| Robustness and convention variants | ZESCO-only MV layer (s22) SA_PV→Grid | 29,311 | 29,316 | 29,359 | 48 |
| Robustness and convention variants | Sizing convention f = 0.4 ΔLCOE % (s10) | +19.099 | +18.799 | +18.637 | -0.462 |
| Robustness and convention variants | Sizing convention f = 0.6 ΔLCOE % (s10) | +27.859 | +27.421 | +27.183 | -0.675 |
| Robustness and convention variants | Band-frozen ΔLCOE % (s19) | +21.843 | +21.500 | +21.315 | -0.529 |
| Robustness and convention variants | Settlements crossing the 1 kW step (s19) | 148,562 | 148,561 | 148,596 | 34 |
| Robustness and convention variants | Aggregate investment per household R0 (USD) | 4,159 | 4,360 | 4,442 | 282 |
| One-at-a-time grid checks (s09, s11) | Grid capex −30 % ΔLCOE % | +45.378 | +44.665 | +44.276 | -1.102 |
| One-at-a-time grid checks (s09, s11) | Grid capex +30 % ΔLCOE % | +45.378 | +44.665 | +44.276 | -1.102 |
| One-at-a-time grid checks (s09, s11) | Grid generation 0.05 USD/kWh ΔLCOE % | +41.498 | +40.904 | +39.995 | -1.503 |
| One-at-a-time grid checks (s09, s11) | Drought price 0.17 ΔLCOE % | +32.644 | +32.286 | +30.639 | -2.005 |
| One-at-a-time grid checks (s09, s11) | Drought price 0.17 SA_PV→Grid | 36,442 | 36,399 | 36,974 | 532 |
| One-at-a-time grid checks (s09, s11) | Drought price 0.22 ΔLCOE % | +30.059 | +29.745 | +28.014 | -2.045 |
| One-at-a-time grid checks (s09, s11) | Drought price 0.22 SA_PV→Grid | 37,400 | 37,357 | 38,169 | 769 |
| One-at-a-time grid checks (s09, s11) | Drought price 0.26 ΔLCOE % | +28.379 | +28.018 | +26.327 | -2.052 |
| One-at-a-time grid checks (s09, s11) | Drought price 0.26 SA_PV→Grid | 38,322 | 38,242 | 39,182 | 860 |
| One-at-a-time grid checks (s09, s11) | Full-dataset LHS re-solve P5 ΔLCOE % (paper l.706–709) | +20.82 | +20.51 | +20.33 | -0.50 |
| One-at-a-time grid checks (s09, s11) | Full-dataset LHS re-solve P50 ΔLCOE % (paper l.706–709) | +51.16 | +49.87 | +49.69 | -1.47 |
| One-at-a-time grid checks (s09, s11) | Full-dataset LHS re-solve P95 ΔLCOE % (paper l.706–709) | +91.38 | +89.32 | +88.54 | -2.85 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* ΔLCOE (bias-corr.) Rural_tier | 57.395 | 56.372 | 55.864 | -1.530 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris σ ΔLCOE Rural_tier | 44.530 | 43.708 | 43.225 | -1.305 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* ΔLCOE (bias-corr.) N_mid | 15.116 | 14.702 | 14.563 | -0.553 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris σ ΔLCOE N_mid | 10.898 | 10.453 | 10.375 | -0.523 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* ΔLCOE (bias-corr.) MaxGridDist_km | 9.938 | 9.461 | 9.436 | -0.502 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris σ ΔLCOE MaxGridDist_km | 8.607 | 8.236 | 8.218 | -0.389 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* ΔLCOE (bias-corr.) SA_PV_capex_mult | 5.872 | 5.974 | 6.034 | 0.163 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris σ ΔLCOE SA_PV_capex_mult | 3.824 | 3.796 | 3.820 | -0.005 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* ΔLCOE (bias-corr.) Discount_rate | 2.087 | 3.625 | 3.475 | 1.388 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris σ ΔLCOE Discount_rate | 1.270 | 2.333 | 2.173 | 0.903 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* ΔLCOE (bias-corr.) Diesel_price_USDl | 0.000 | 0.126 | 0.135 | 0.135 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris σ ΔLCOE Diesel_price_USDl | 0.000 | 0.165 | 0.121 | 0.121 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* switches Rural_tier | 8446.3 | 8398.9 | 8419.3 | -27.0 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* switches MaxGridDist_km | 4652.8 | 4644.0 | 4648.1 | -4.7 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* switches SA_PV_capex_mult | 1619.4 | 1616.4 | 1623.4 | 3.9 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* switches Discount_rate | 1071.0 | 1056.0 | 1057.9 | -13.1 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* switches N_mid | 294.9 | 307.5 | 312.8 | 17.8 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Morris μ* switches Diesel_price_USDl | 0.0 | 2.6 | 3.2 | 3.2 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | LHS ΔLCOE % (bias-corr.) P5 | +21.06 | +20.73 | +20.57 | -0.49 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | LHS ΔLCOE % (bias-corr.) P50 | +51.32 | +49.86 | +49.49 | -1.83 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | LHS ΔLCOE % (bias-corr.) P95 | +75.16 | +73.66 | +73.03 | -2.13 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | LHS switches P5 | 3,656 | 3,657 | 3,673 | 17 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | LHS switches P50 | 4,419 | 4,415 | 4,428 | 8 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | LHS switches P95 | 5,292 | 5,270 | 5,284 | -8 |
| Global sensitivity (s08): committed = year-only cache; mg-fuel and final = full cache key | Bias-correction factor | 0.9011 | 0.9060 | 0.9136 | 0.0125 |
| Diesel-price OAT, full dataset (s26) | Diesel 1.90 (central) USD/L ΔLCOE % | — | +44.665 | +44.276 | — |
| Diesel-price OAT, full dataset (s26) | Diesel 1.90 (central) USD/L SA_PV→Grid | — | 33,669 | 33,701 | — |
| Diesel-price OAT, full dataset (s26) | Diesel 0.95 USD/L ΔLCOE % | — | +44.970 | +44.579 | — |
| Diesel-price OAT, full dataset (s26) | Diesel 0.95 USD/L SA_PV→Grid | — | 33,669 | 33,701 | — |
| Diesel-price OAT, full dataset (s26) | Diesel 0.38 USD/L ΔLCOE % | — | +46.240 | +45.933 | — |
| Diesel-price OAT, full dataset (s26) | Diesel 0.38 USD/L SA_PV→Grid | — | 33,674 | 33,706 | — |
| Diesel-price OAT, full dataset (s26) | Diesel 0.10 USD/L ΔLCOE % | — | +47.340 | +46.973 | — |
| Diesel-price OAT, full dataset (s26) | Diesel 0.10 USD/L SA_PV→Grid | — | 33,676 | 33,705 | — |

**Diesel figures as currently written in the paper** (2026-10-19 follow-up; pre-fix costing, diesel-bin cache; superseded, see §3):

| Quantity | Value |
|---|---|
| Paper diesel Morris μ* (2026-10-19) | 0.915 (σ 0.649) |
| Paper LHS band (2026-10-19) | +21.0 / +51.3 / +75.6 |
| Paper OAT 0.95 / 0.38 / 0.10 (2026-10-19) | +46.35 / +47.00 / +47.34 |

## 4. Reading the result

**Headline.** The central ΔLCOE moves +45.38 % → +44.67 % (mini-grid fuel fix) → **+44.28 %**
(final), −1.10 pp in all. The sign and the qualitative findings are unchanged:

- SA_PV→Grid switching dominates;
- the Morris ranking is unchanged;
- Tier 2 is still the fragile boundary case.

**Investment** rises by USD 1.06 bn in each arm (the mini-grids' larger PV-battery systems; F-B;
F-A mini-grid). ΔInvestment in USD is unchanged at about +6.42 bn, so ΔInvestment % falls.

**Biggest relative moves:**

- the drought-price variants (−2.0 pp), because F-A scales with the grid price;
- the 2050 band (−1.0 to −2.1 pp).

**Diesel price, on a clean basis.**

| Quantity | Final baseline |
|---|---|
| Morris μ\* | 0.135 (last) |
| LHS standardised effect | small |
| Full-dataset OAT, 0.95 / 0.38 / 0.10 USD/L | +0.30 / +1.66 / +2.70 pp vs central |

## 5. Not done, by instruction

- No `.tex`/`.bib` edits.
- No paper wording.
- Nothing pushed.
- Nothing on `main`.
- The SA_Diesel shadow cost stays parked (`2026-10_PARKED_sadiesel_shadow_cost.md` on
  `diesel-sensitivity-followup`).
