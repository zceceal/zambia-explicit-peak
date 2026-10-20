# Mini-grid diesel fuel-units fix: full rerun report (2026-10-20)

- **Branch:** `mg-fuel-units-fix`, cut from `main` (`a577a7b`).
- **Fix commit:** `e92d1d9`.
- **Scope:** computational only. No `.tex`/`.bib` file was touched, nothing was pushed, and no
  paper wording is proposed.
- **What the fix does:** `onsset_helpers.build_pv_hybrid_lookup` now passes each mini-grid diesel
  bin to the hybrid optimiser in delivered **USD/L**, i.e. `MGDieselFuelCost × LHV_DIESEL × 0.33`.
  Before the fix it passed the USD/kWh column value, which `hybrids.py:284` then multiplies by
  litres.
- **What it leaves alone:** the lookup keys, the `MGDieselFuelCost` column and its other consumers,
  and the vendored `onsset.py` and `hybrids.py`.

## 1. Hand checks (Phase 0 and Phase 1)

Settlement **id 46780**: mini-grid, rural Tier 3, GHI 2,006, 2030 population 779, 2030 demand
125,268 kWh, `MGDieselFuelCost2030` 0.581093 USD/kWh. Lookup key (tier 3, GHI 2,000, diesel bin
0.6).

The committed 2030 lookup was rebuilt from seed 42, in the same order. The optimiser's chosen
configuration reproduces the committed `NewCapacity2030` exactly, at 70.2719 kW.

| | Before fix (committed) | After fix |
|---|---|---|
| Price passed to the optimiser | 0.600 (USD/kWh bin, used as USD/L) | **1.969021 USD/L** (0.6 × 9.9445 × 0.33) |
| Configuration (per 10 MWh reference) | PV 4.048 kW, battery 8.096 kWh, diesel 1.562 kW; diesel share 45.1 % | PV 9.822 kW, battery 27.052 kWh, **no genset** |
| Fuel used by the settlement | 18,497.9 L/yr (0.3276 L/kWh of diesel output) | 0 L/yr |
| Fuel cost charged | 18,497.9 L × 0.6 = **11,098.75 USD/yr** | 0 USD/yr |
| Generation LCOE | 0.235083 USD/kWh | **0.279040 USD/kWh** |
| Code fuel NPV vs hand calculation (L × P × Σ 1.08⁻ʸ over y = 0…15) | 8,469.70 = 8,469.70 ✓ | 0 = 0 ✓ |

**Correct cost for the committed configuration.** The same 18,497.9 L/yr is priced either way:

| Price basis | USD/L | Cost (USD/yr) | Current / correct |
|---|---|---|---|
| Settlement-exact delivered price (1.90 × (1 + 2·33.7·0.817/15000)) | 1.906972 | 35,275.02 | 0.3146 |
| Bin-consistent price, as the patched code charges | 1.969021 | **36,422.79** | 0.3047 |

The patched code, holding that configuration fixed, charges exactly 36,422.79 USD/yr. The 3.3 %
gap to the settlement-exact figure comes from the lookup's existing 0.1 USD/kWh diesel bins, which
the fix does not change.

Using 10.7 kWh/L instead of the model's own LHV (9.9445) would not change the correct USD/L. The
column was built with 9.9445, so multiplying by 9.9445 × 0.33 recovers the delivered USD/L exactly.

Logs: `_claude_workspace/logs/2026-10-20_mgfuel_phase{0,1}_handcheck.log`.

## 2. How the rerun was done and gated

- **Isolation.** All 32 stages ran in a detached git worktree of `e92d1d9`, with its own empty
  `data/onsset_outputs`. Committed inputs are linked read-only. The five files a stage writes into
  `data/processed` (the 2050 spines and `calib_distgate_txormv`/`_selftest`) are never linked, so
  those writes create new local files.
- **Setup gate.** The same isolated setup at `main` (unpatched) re-ran `s06`. All five outputs (R0,
  R1 at `N_mid` 10/20/50, tech split) are **SHA-256-identical** to the committed files. The
  environment reproduces the examined baseline exactly, so every difference below is caused by the
  fix.
- **Stages.** Run sequentially, as listed in `REPRODUCING.md`:
  - `s06`, `check_index_alignment`, `test_index_alignment`, `s10`, `s07`, `s11`
  - `s12a`, `s12b`, `s12` (`2050only`, `2050only_sweep`, `2050only_ruralT2`), `s12c`
  - `s08`, `s09`, `s13`, `fig_r0r1_allocation_map`, `s14`
  - `s15` (`--self-test`, smooth, monotone), `s16`–`s22`, `check_mv_sources`, `s24`, `s23`
  - `check_spine_integrity`, `s25`

  All exited 0, in **105.3 min** of compute. The in-script gates (`s08`, `s09`, `s11`) passed
  against the new central headline. `s09`'s switch gate was exact.
- **Real data untouched.** A before/after snapshot of every file in `5. data/{processed,
  onsset_outputs, raw, onsset_inputs}`, `results/` and `scripts/outputs/` showed no file added,
  removed or modified during the run.
- **Outputs.** All 103 outputs were copied as `2026-10_mgfuel_*`, with the original label replaced:
  - per-settlement and 2050 files into `data/onsset_outputs/`
  - summary tables into `results/summary/`
  - figures into `figures/`
  - notes into `notes/`

  `results/summary/2026-10_mgfuel_manifest.csv` maps each copy to its run name. No committed
  `2026-08*` or `2026-09*` file was overwritten.

## 3. Every pipeline-derived number: committed vs corrected

### 3.1 Central result (2030, rural Tier 3, `N_mid` = 20), from `s06` and `s14`

| Quantity | Committed | Corrected | Δ |
|---|---|---|---|
| **ΔLCOE % (energy-weighted)** | **+45.3775 %** | **+44.6653 %** | **−0.71 pp** |
| Energy-weighted LCOE, R0 | 0.27569 USD/kWh | 0.28008 | +0.0044 |
| Energy-weighted LCOE, R1 | 0.40078 USD/kWh | 0.40517 | +0.0044 |
| Investment to 2030, R0 | USD 15.579 bn | 16.331 | +0.753 |
| Investment to 2030, R1 | USD 21.999 bn | 22.751 | +0.753 |
| ΔInvestment, R1 − R0 | +USD 6.420 bn (+41.21 %) | +6.420 bn (**+39.31 %**) | 0 bn (−1.90 pp) |
| New capacity, R0 / R1 | 2,664.4 / 2,706.2 MW | 2,882.1 / 2,923.9 MW | +217.7 / +217.7 |
| ΔCapacity % | +1.571 % | +1.452 % | −0.12 pp |
| MG_PVHybrid capacity (both arms) | 366.2 MW | 583.9 MW | +217.7 |
| MG_PVHybrid investment, R0 / R1 | USD 1.408 / 1.406 bn | 2.161 / 2.159 bn | +0.753 |
| Grid investment / SA_PV investment, R0 | 4.3315 / 9.8390 bn | 4.3316 / 9.8390 bn | ≈ 0 |
| **SA_PV→Grid switches** | **33,665** | **33,669** | +4 |
| Settlements changing technology | 33,665 (all SA_PV→Grid) | 33,669 (all SA_PV→Grid) | +4 |
| Population switching (2030) | 430,292 (1.7650 %) | 430,328 (1.7652 %) | +36 |
| Tech split R0: grid / SA_PV / MG | 32,058 / 236,843 / 1,625 | 32,057 / 236,844 / 1,625 | −1 / +1 / 0 |
| Tech split R1: grid / SA_PV / MG | 65,723 / 203,178 / 1,625 | 65,726 / 203,175 / 1,625 | +3 / −3 / 0 |
| 2030 population on grid / SA_PV / MG, R0 | 15.299 / 6.812 / 2.268 M | 15.299 / 6.812 / 2.268 M | −24 / +24 / 0 people |
| Median grid LCOE R0 / R1 | 0.53874 / 0.49579 | 0.53875 / 0.49578 | ≈ 0 |
| Median SA_PV LCOE R0 / R1 | 1.04762 / 2.67168 | unchanged | 0 |
| Aggregate investment per household, R0 | USD 4,159 | USD 4,360 | +201 |
| Grid / SA capacity change in R1 | −17.363 % / +23.200 % | −17.363 % / +23.199 % | ≈ 0 |
| SA energy share R0, Tier 3 / Tier 2 | 17.489 % / 7.537 % | 17.490 % / 7.575 % | ≈ 0 / +0.04 |

### 3.2 `N_mid` sweep (`s06`)

| `N_mid` | ΔLCOE % committed → corrected | SA_PV→Grid | Settlements changing technology |
|---|---|---|---|
| 10 | +29.99 → **+29.52** (−0.47) | 32,209 → 32,213 | 32,214 → 32,215 |
| 20 | +45.38 → **+44.67** (−0.71) | 33,665 → 33,669 | 33,665 → 33,669 |
| 50 | +66.09 → **+65.05** (−1.04) | 34,342 → 34,344 | 34,342 → 34,344 |

### 3.3 Rural Tier 2 (`s07`; 2030)

| `N_mid` | ΔLCOE % | SA_PV→Grid | ΔInvestment % |
|---|---|---|---|
| 10 | −3.69 → **−3.87** | 9 → 9 | −8.08 → −8.56 |
| 20 | +1.92 → **+1.67** | 47 → **50** | −2.64 → −3.20 |
| 50 | +7.20 → **+6.95** | 298 → **303** | +2.87 → +2.39 |

The verdict is unchanged: "FRAGILE: direction or sign reversal at Tier 2".

### 3.4 2050 horizon (`s12` `2050only`)

| Variant | ΔLCOE % | Switches |
|---|---|---|
| Tier 3 `N_mid` 20 (central) | +34.89 → **+34.15** | 32,157 → 32,157 (`s12c`) |
| Tier 3 `N_mid` 10 / 50 (band) | +23.08 / +50.93 → **+22.59 / +49.85** | 29,941 / 33,016 unchanged |
| Tier 2 `N_mid` 10 / 20 / 50 | −4.05 / −0.22 / +3.57 → **−4.08 / −0.35 / +3.37** | 3 / 11 / 108 → 3 / 11 / 110 |

2050 R0 mini-grid settlements: Tier 3 1,703 → 1,703; Tier 2 1,027 → **841**. ΔInvestment %, Tier 3
`N_mid` 10/20/50: +9.22 / +17.81 / +29.50 → +8.82 / +17.05 / +28.24.

### 3.5 Global sensitivity (`s08`, run as on `main`: PV-hybrid cache keyed on year)

- **Subsample.** Central +50.36 % → **+49.30 %**; bias-correction factor 0.9011 → 0.9060.
- **Morris μ\*, bias-corrected.** The ranking is unchanged:

  | Parameter | μ\* committed → corrected |
  |---|---|
  | Rural_tier | 57.39 → **56.60** |
  | N_mid | 15.12 → **14.95** |
  | MaxGridDist_km | 9.94 → **9.67** |
  | SA_PV_capex_mult | 5.87 → **6.00** |
  | Discount_rate | 2.09 → **1.99** |
  | Diesel_price | 0.00 → 0.00 (year-only cache; see §5) |

- **Morris μ\* for switch count.** Ranking unchanged: 8,446 / 4,653 / 1,619 / 1,071 / 295 →
  8,418 / 4,660 / 1,619 / 1,073 / 299.
- **LHS, 200 samples, all full-OnSSET.** 5th / 50th / 95th: +21.1 / +51.3 / +75.2 % →
  **+20.7 / +50.5 / +74.0 %**. Switches 3,656 / 4,419 / 5,292 → 3,658 / 4,418 / 5,282.
- **Emulator.** Still rejected: RMSE 11.61 → 11.32 pp, R² 0.523 → 0.527.

### 3.6 One-at-a-time checks (`s09`, `s11`)

| Variant | ΔLCOE % | Switches |
|---|---|---|
| Grid capex ±30 % | +45.38 → **+44.67** (still identical to central) | 33,665 → 33,669 |
| Grid generation cost 0.05 USD/kWh (`s09`) | +41.50 → **+40.90** | 34,316 → 34,309 |
| Drought price 0.17 USD/kWh | +32.64 → **+32.29** | 36,442 → 36,399 |
| Drought price 0.22 USD/kWh | +30.06 → **+29.75** | 37,400 → 37,357 |
| Drought price 0.26 USD/kWh | +28.38 → **+28.02** | 38,322 → 38,242 |

At 0.26 USD/kWh the R0 mini-grid count falls from 2,154 to **1,687**: correctly priced mini-grid
diesel no longer undercuts a costly grid.

### 3.7 Full-dataset re-solves at the LHS percentile samples (`s09`; paper lines 706–709)

The same samples are selected (27 / 194 / 152).

| | P5 | P50 | P95 |
|---|---|---|---|
| Full-dataset ΔLCOE % | +20.82 → **+20.51** | +51.16 → **+49.87** | +91.38 → **+89.32** |
| Rescaled subsample value | 21.07 → 20.74 | 51.40 → 50.69 | 75.09 → 73.95 |
| Full minus rescaled | | | 16.3 → **15.4 pp** |

### 3.8 Robustness and convention sensitivities

| Stage | Quantity | Committed → corrected |
|---|---|---|
| `s10` | ΔLCOE % at f = 0.4 / 0.6 / 1.0 | +19.10 / +27.86 / +45.38 → **+18.80 / +27.42 / +44.67** |
| `s19` | band-frozen ΔLCOE % | +21.84 → **+21.50** |
| `s19` | SA-frozen ΔLCOE %, R1 / R0 allocation | +1.58 / −0.53 → +1.56 / −0.52 |
| `s19` | settlements crossing the 1 kW step | 148,562 → 148,561 |
| `s19` | median kW/hh R0 / R1 | 0.80 / 1.21, unchanged |
| `s15` | smooth capex curve | +23.70 % / 23,046 → **+23.34 % / 23,051** |
| `s15` | monotone capex curve | +18.72 % / 15,724 → **+18.43 % / 15,725** |
| `s16` | full reinvestment | +45.93 % / 33,627 → **+45.24 % / 33,631**; still +0.57 pp over central |
| `s17` | fitted anchors | +44.81 % / 33,645 → **+44.11 % / 33,649**; shared with central 33,639 → 33,643; fitted curve unchanged (it has no cost input) |
| `s18` | household size 4.5 | +43.58 % / 32,845 → **+42.89 % / 32,839** |
| `s18` | household size 5.5 | +46.95 % / 33,858 → **+46.21 % / 33,858** |
| `s21` | transformer-or-MV gate | +46.24 % / 33,367 → **+45.62 % / 33,371** |
| `s22` | ZESCO-only MV layer | +45.72 % / 29,311 → **+44.85 % / 29,316** |
| `s23` | single-household settlements excluded | +43.61 % / 27,990 → **+42.91 % / 27,992** |
| `s24` | switcher profile | 33,665 → 33,669 switchers, all rural; median 2.02 hh and 1.765 % of population, unchanged to 3 sf |

## 4. What is affected and what is not

**Unaffected (identical), and why.** None of these inputs or calculations involves mini-grid
diesel costing:

- peak-to-mean ratios and their provincial comparison (`s20`, byte-identical);
- ρ statistics, N_hh, urban shares, settlements at the floor, mini-grid-eligible counts and shares
  (`s14`);
- the 2050 spines and erosion summary (`s12a`, `s12b`, byte-identical);
- the calibration (`s21`'s recalibrated file is byte-identical);
- MV distance sources (byte-identical);
- the median SA_PV LCOE, and SA_PV settlement LCOEs generally;
- mini-grid settlement and population counts at the Tier 3 central case;
- the index-alignment acceptance checks.

**Affected.** Every ΔLCOE %, investment and capacity figure from a solve, because mini-grid costs
are in both arms' energy-weighted totals and investment. The pattern:

- **ΔLCOE %** falls by about 0.3–1.1 pp everywhere (about −1.6 % relative). Mini-grid generation
  cost rises in both arms, which enlarges the R0 denominator.
- **Investment and capacity** rise by about USD 0.75 bn and about 218 MW in every Tier 3 2030 arm:
  mini-grids are rebuilt with more PV and battery, and less or no genset. ΔInvestment in USD is
  unchanged, but ΔInvestment % falls.
- **Switch counts and technology splits** move by single digits at Tier 3, through grid-network
  re-routing next to mini-grid-priced settlements (§5).
- **Tier 2, 2050 Tier 2 and high grid-price variants** lose mini-grids to SA_PV or grid, where the
  mini-grid margin was thin.

## 5. Per-settlement structure checks and tracing

Every per-settlement output was compared row by row with its committed counterpart: 37 files,
aligned on `id`, all columns, exact float comparison. **Every file has identical structure:** same
270,526 rows, same columns in the same order, same dtypes, same row order. In every file, at least
98.7 % of rows are byte-identical.

| File (committed run name) | Structure | Rows byte-identical (of 270,526) | Rows changed | of which own MG LCOE unchanged | Technology changes (analysis year) |
|---|---|---|---|---|---|
| `2026-08-21_hhsize_R0_rural4p5.csv` | same | 267,681 | 2,845 | 23 | 6 (2030) |
| `2026-08-21_hhsize_R0_rural5p5.csv` | same | 268,389 | 2,137 | 13 | 0 (2030) |
| `2026-08-21_hhsize_R1_n20_rural4p5.csv` | same | 267,667 | 2,859 | 37 | 2 (2030) |
| `2026-08-21_hhsize_R1_n20_rural5p5.csv` | same | 268,402 | 2,124 | 0 | 0 (2030) |
| `2026-08_final_lcoe_R0.csv` | same | 268,079 | 2,447 | 7 | 3 (2030) |
| `2026-08_final_lcoe_R0_ruralT2.csv` | same | 267,991 | 2,535 | 72 | 126 (2030) |
| `2026-08_final_lcoe_R1_n10.csv` | same | 268,038 | 2,488 | 48 | 18 (2030) |
| `2026-08_final_lcoe_R1_n20.csv` | same | 268,037 | 2,489 | 49 | 11 (2030) |
| `2026-08_final_lcoe_R1_n50.csv` | same | 268,032 | 2,494 | 54 | 11 (2030) |
| `2026-08_final_lcoe_R1_ruralT2_n10.csv` | same | 268,021 | 2,505 | 4 | 115 (2030) |
| `2026-08_final_lcoe_R1_ruralT2_n20.csv` | same | 268,009 | 2,517 | 26 | 197 (2030) |
| `2026-08_final_lcoe_R1_ruralT2_n50.csv` | same | 267,987 | 2,539 | 65 | 206 (2030) |
| `2026-08_final_oat_capminus30pct_R0.csv` | same | 268,079 | 2,447 | 7 | 3 (2030) |
| `2026-08_final_oat_capminus30pct_R1_n20.csv` | same | 268,037 | 2,489 | 49 | 11 (2030) |
| `2026-08_final_oat_capplus30pct_R0.csv` | same | 268,079 | 2,447 | 7 | 3 (2030) |
| `2026-08_final_oat_capplus30pct_R1_n20.csv` | same | 268,037 | 2,489 | 49 | 11 (2030) |
| `2026-08_final_oat_gen-017_R0.csv` | same | 267,683 | 2,843 | 403 | 120 (2030) |
| `2026-08_final_oat_gen-017_R1_n20.csv` | same | 267,762 | 2,764 | 324 | 32 (2030) |
| `2026-08_final_oat_gen-022_R0.csv` | same | 267,343 | 3,183 | 743 | 206 (2030) |
| `2026-08_final_oat_gen-022_R1_n20.csv` | same | 267,389 | 3,137 | 697 | 63 (2030) |
| `2026-08_final_oat_gen-026_R0.csv` | same | 267,180 | 3,346 | 906 | 685 (2030) |
| `2026-08_final_oat_gen-026_R1_n20.csv` | same | 267,081 | 3,445 | 1,005 | 550 (2030) |
| `2026-08_final_oat_genminusdrought_R0.csv` | same | 268,026 | 2,500 | 60 | 14 (2030) |
| `2026-08_final_oat_genminusdrought_R1_n20.csv` | same | 267,993 | 2,533 | 93 | 13 (2030) |
| `2026-08_fittedanchor_lcoe_R1.csv` | same | 268,037 | 2,489 | 49 | 11 (2030) |
| `2026-09-02_mvzesco_R0.csv` | same | 267,237 | 3,289 | 840 | 3 (2030) |
| `2026-09-02_mvzesco_R1_n20.csv` | same | 267,197 | 3,329 | 880 | 8 (2030) |
| `2026-09-02_txormv_R0.csv` | same | 268,164 | 2,362 | 7 | 3 (2030) |
| `2026-09-02_txormv_R1_n20.csv` | same | 268,122 | 2,404 | 49 | 11 (2030) |
| `2050only_grid3_lcoe_R0.csv` | same | 268,164 | 2,362 | 0 | 0 (2050) |
| `2050only_grid3_lcoe_R0_ruralT2.csv` | same | 268,127 | 2,399 | 37 | 210 (2050) |
| `2050only_grid3_lcoe_R1_n10.csv` | same | 268,164 | 2,362 | 0 | 0 (2050) |
| `2050only_grid3_lcoe_R1_n20.csv` | same | 268,157 | 2,369 | 7 | 0 (2050) |
| `2050only_grid3_lcoe_R1_n50.csv` | same | 268,164 | 2,362 | 0 | 0 (2050) |
| `2050only_grid3_lcoe_R1_ruralT2_n10.csv` | same | 268,164 | 2,362 | 0 | 42 (2050) |
| `2050only_grid3_lcoe_R1_ruralT2_n20.csv` | same | 268,164 | 2,362 | 0 | 33 (2050) |
| `2050only_grid3_lcoe_R1_ruralT2_n50.csv` | same | 268,155 | 2,371 | 9 | 108 (2050) |

**How the changed rows trace to the fix.**

1. **Direct channel.** Every row whose own MG_PVHybrid LCOE changed (about 2,100–2,850 per file).
   These are the mini-grid-eligible settlements with a non-99 MG cost. Their
   `Minimum_LCOE_Off_grid`, `MaxDist`, investment and capacity follow from that.
2. **Grid-network re-routing.** These are the rows in "own MG LCOE unchanged". Every one changed
   only in grid-side columns (`MinGridDist`, `Grid`, `MinimumOverallLCOE`, investment), and every
   one lies near a settlement whose MG LCOE or `MaxDist` changed:

   | File | Max distance (km) | Median distance (km) | Random-settlement median (km) |
   |---|---|---|---|
   | central R0 | 4.3 | 3.3 | 6.4 |
   | central R1 | 4.0 | 2.2 | 6.4 |
   | drought 0.26 R0 (906 rows) | 9.4 | 1.5 | 12.2 |
   | 2050 Tier 2 R0 | 3.6 | 1.3 | 12.3 |

   A higher off-grid cost lets the grid extend further from mini-grid-priced settlements, which
   re-routes the network and changes neighbours' distance to it. The large counts in the drought
   files come from 467 mini-grid→Grid moves at 0.26 USD/kWh.
3. **One pre-existing, unrelated difference.** In `2026-09-02_mvzesco_R{0,1_n20}` (`s22`), 833
   additional rows differ in `CurrentMVLineDist`, `PlannedMVLineDist` and `minTDdist`. These are
   input distances, which the fix cannot touch. An **unpatched** rerun of `s22` (code at `main`)
   reproduces exactly the same differences against the committed files. Their size is about
   10⁻¹² km (max 1.95 × 10⁻¹²), i.e. floating-point noise from the MV-distance computation. The
   unpatched rerun also reproduces the committed `s22` summary exactly (+45.718913 %, 29,311), and
   unpatched and patched reruns are identical in those columns. So it predates this work and does
   not affect any result. Excluding it, the ZESCO files behave like the others (7 R0 rows traced to
   re-routing).

The table above omits files that are byte-identical or have no committed counterpart:

- **Byte-identical:** the provincial ρ tables, `pe_2050_erosion_summary`, `mv_distance_sources`, the
  three 2050 spines, and the `s21` calibration file.
- **No committed per-settlement counterpart:** the `2026-08-16_*` capex and reinvestment solves,
  which are compared at summary level in §3.8.


## 6. Follow-on: the diesel-price sensitivity must be rerun on this baseline

The diesel-price work on branch `diesel-sensitivity-followup` was computed on the **old, unit-mismatched
mini-grid costing**:

- Task A: corrected Morris μ\* 0.915, LHS +21.0 / +51.3 / +75.6 %.
- Task B: `s26` OAT, +46.4 / +47.0 / +47.3 %.

It is already written into the paper, and **it needs rerunning again on top of this corrected
baseline once this fix lands**. It was not attempted here.

On this branch, `s08` still carries `main`'s year-only PV-hybrid cache. Its diesel μ\* of 0.00 in
§3.5 is therefore the old caching artefact, not a corrected diesel effect. The probe in
`2026-10_diesel_followup_mg_fuel_units.md` (on the other branch) suggests the corrected-units
diesel effect will be smaller, about 0.3× (μ\* about 0.27).

## 7. Notes

- **The earlier first-order estimate held for ΔLCOE:** it predicted about +44.7 % and the solve
  gives +44.665 %. It was **wrong on two points**:
  - investment and capacity rise materially (+USD 0.75 bn, +218 MW), which it did not estimate;
  - the allocation is not exactly unchanged (+4 switches centrally).
- **Not done, by instruction:** `main.tex`, any push, and paper wording.
- **Oddities seen, not addressed:**
  - `calculate_hybrid_lcoe` charges fuel in year 0 although generation is credited only from year 1
    (`hybrids.py`, year loop).
  - Lookup diesel bins are 0.1 USD/kWh wide, about 3 % price resolution.
- **No committed per-settlement files for `s15`/`s16`.** The committed `2026-08-16_*` capex and
  reinvestment solves are not present in `data/onsset_outputs`, so those stages are compared at
  summary level only, via `2026-09-02_variant_summaries.csv`.
