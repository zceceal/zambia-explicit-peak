# The pipeline

Every script lives in `scripts/`, named `sNN_<what it does>.py`, and runs in numeric order. Each stage
writes files the next stage reads. Every contested parameter lives in `config/config.yaml`, not in
code.

The `s` prefix is deliberate: some later stages import functions from earlier ones, and a filename
beginning with a digit (`06_run_arms.py`) cannot be imported by Python.

## Run order

| Stage | Script | What it does | Key output |
|---|---|---|---|
| 01 | `s01_build_spine_clusters.py` | Builds settlement polygons from GRID3: geometry, WorldPop population, urban/rural class, admin-1 | cluster spine |
| 02 | `s02_build_spine_dispersed.py` | Recovers the ~18% of population living outside any GRID3 polygon by aggregating residual pixels to ~2.8 km cells, so the spine reconciles to the national total | **combined spine, 270,526 settlements** |
| 03 | `s03_build_spine_attributes.py` | Computes every OnSSET spatial column: solar and wind resource, travel time, road and grid distances (MV distance = minimum over ZESCO, Meta predictive and OSM layers; transformers; the NEP distance is stored but not used) | spine with attributes |
| 04 | `s04_calibrate_base_year.py` | Calibrates who is already electrified in the base year against the national survey. Variant A (2 km transformer gate plus night lights, NEAS-2023) is the one used; a transformer-or-MV gate is the sensitivity in `s21` | calibrated spine |
| 05 | `s05_compute_peak_ratios.py` | **The intervention.** Adds `N_hh` and `PE_ratio` per settlement using `peak_preprocessor/`. Writes one spine per swept `N_mid` ∈ {10, 20, 50} | PE-augmented spines |
| 06 | `s06_run_arms.py` | The main event: solves R0 and R1 through OnSSET (planned distance = current distance) and compares them | R0/R1 outputs |
| 07 | `s07_run_demand_sensitivity.py` | Repeats the comparison at rural Tier 2 (219 kWh/HH/yr). One changed value; everything else identical | Tier-2 outputs |
| 08 | `s08_run_global_sensitivity.py` | Morris elementary-effects screen (6 parameters, 8 trajectories, 56 paired evaluations) plus Latin-hypercube uncertainty propagation | sensitivity results |
| 09 | `s09_run_oat_checks.py` | One-at-a-time checks on the grid side, and full-spine validation of the sensitivity subsample bias correction | OAT results |
| 10 | `s10_run_sizing_decomposition.py` | Post-processes existing outputs to recompute the headline with only a fraction `f` of stand-alone capital scaled by peak. Produces the +19.1% / +27.9% / +45.4% band | f-band |
| 11 | `s11_run_drought_oat.py` | Re-runs the grid-cost OAT at 2024 drought import prices (0.17–0.26 USD/kWh) | drought OAT |
| 12a | `s12a_build_2050_peak_ratios.py` | Rebuilds `PE_ratio` on the 2050 population and measures how far the peak signal erodes. Reads `data/processed/zambia_grid3_spine_pe_n20.csv` | `zambia_settlements_PE_2050_uniform.csv` (repo root); `results/summary/2026-08_final_pe_2050_erosion_summary.csv` |
| 12b | `s12b_build_2050_spine.py` | Builds the 2050 spine: the engine's own projection to 38,083,385 people at urban share 0.672, then `N_hh` and `PE_ratio` on it. Reads `data/processed/zambia_grid3_spine_pe_n{10,20,50}.csv` | `data/processed/zambia_grid3_spine_pe_2050_n{10,20,50}.csv` |
| 12 | `s12_run_2050_horizon.py` | Re-solves both arms at the projected 2050 population, reusing `s06`'s `run_arm()`. Reads the 2050 spines from `s12b` | `scripts/outputs/2050only_grid3_lcoe_{R0,R1_n10,R1_n20,R1_n50}.csv` |
| 12c | `s12c_summarise_2050.py` | Summarises one 2050 arm pair. Reads the two per-settlement CSVs named on its command line | stdout only |
| 13 | `s13_generate_figures.py` | Regenerates every figure in the paper. Reads the `s06`, `s07`, `s08` and `s09` outputs from `data/onsset_outputs/` | `figures/*.png`, `figures/*.pdf` |
| 14 | `s14_paper_numbers.py` | Every figure the paper quotes, from one arm pair. Reads `data/onsset_outputs/<run>_R0.csv` and `_R1_n{10,20,50}.csv` | `results/summary/<run>_paper_numbers.csv` |
| 15 | `s15_run_capex_curve_sensitivity.py` | Re-solves the central case against a continuous stand-alone capital-cost curve (`smooth`) and with the >1 kW premium removed (`monotone`). Reads `data/processed/zambia_grid3_spine_pe_n20.csv` | `data/onsset_outputs/2026-08_final_capex{smooth,monotone}_*.csv` |
| 16 | `s16_run_corrected_conventions.py` | Re-solves R1 with OnSSET's full reinvestment schedule switched on. Reads the same spine | `data/onsset_outputs/2026-08_final_reinvest_*.csv` |
| 17 | `s17_run_fitted_anchors.py` | Re-solves R1 on a curve fitted to the Tum mini-grid and the IRP load-factor point, removing the `N_mid` assumption. Reads the same spine | `data/onsset_outputs/2026-08_final_fitted_*.csv` |
| 18 | `s18_run_hhsize_sensitivity.py` | Re-solves both arms at rural household size 4.5 and 5.5. Reads the same spine | `data/onsset_outputs/2026-08-21_hhsize_*.csv`; `results/summary/2026-08-21_hhsize_sensitivity.csv` |
| 19 | `s19_band_and_channel_decomposition.py` | Step-crossing and channel-freeze decomposition, no re-solve. Reads `data/onsset_outputs/2026-08_final_lcoe_{R0,R1_n20}.csv` | `results/summary/2026-08_final_band_and_channel_decomposition.csv` |
| 20 | `s20_provincial_rho.py` | Provincial peak-to-mean ratios against REMP Table 9, no re-solve. Reads `data/onsset_outputs/2026-08_final_lcoe_R1_n20.csv` | `results/summary/2026-08_final_provincial_rho.csv`, `..._provincial_rho_summary.csv` |
| 21 | `s21_run_calibration_gate_sensitivity.py` | Re-calibrates on the transformer-or-MV base-year gate and solves both arms. Reads `data/processed/zambia_grid3_spine_stage2.csv` | `data/onsset_outputs/2026-09-02_txormv_*.csv`; `results/summary/2026-09-02_calibration_gate_sensitivity.csv` |
| 22 | `s22_run_mv_layer_sensitivity.py` | Re-solves both arms with the ZESCO record as the only MV layer. Reads the spine and the raw MV layers | `data/onsset_outputs/2026-09-02_mvzesco_*.csv`; `results/summary/2026-09-02_mv_layer_sensitivity.csv` |
| 23 | `s23_summarise_variants.py` | One table of every variant, no re-solve. Reads `data/onsset_outputs/` and `scripts/outputs/` | `results/summary/2026-09-02_variant_summaries.csv` |
| 24 | `s24_switcher_profile.py` | Profile of the switching settlements, no re-solve. Reads `data/onsset_outputs/2026-08_final_lcoe_{R0,R1_n20}.csv` | `results/summary/2026-09-03_switcher_profile.csv` |
| 25 | `s25_collect_summaries.py` | Copies the thirteen summary CSVs `s06`, `s08`, `s09`, `s10` and `s11` write into `data/onsset_outputs/` (git-ignored) into `results/summary/` (committed). Last step of every full run | committed summaries |

Three acceptance checks sit outside the run order and re-solve nothing:

| Script | What it does | Inputs | Outputs |
|---|---|---|---|
| `check_index_alignment.py` | Share of stand-alone settlements whose capacity satisfies `E / (ATR x GHI)`; must report ~100% after any `s06` run | the arm CSV named on its command line | stdout only |
| `check_spine_integrity.py` | 22 hard checks on the spine: counts, population reconciliation, column ranges, `PE_ratio` against the curve, `N_hh` against `Pop2030` | `data/processed/zambia_grid3_spine_pe_n20.csv` | stdout only; exits non-zero on any failure |
| `check_mv_sources.py` | Which of the three MV layers sets each settlement's distance | the spine plus the raw ZESCO and Meta layers | `results/summary/2026-09-02_mv_distance_sources.csv` |

One supporting module sits alongside them: `scripts/onsset_helpers.py` holds the shared loaders (solar
and wind profiles, config) used from stage 06 onward. Every gate that used to compare against a
hard-coded headline value — in `s08`, `s09` and `fig_r0r1_allocation_map.py` — now reads it at run
time from the `s06` outputs via `onsset_helpers.central_headline()`.

## The intervention, in detail (stage 05)

`peak_preprocessor/` is the only thing this study adds to OnSSET. It contains one module:

- **`pe_diversity.py`** — the peak-to-energy model itself. Two functions: `compute_beta()` derives the
  curve's exponent from the measured anchors, and `pe_from_n()` returns the ratio for a given
  connection count.
Stage 05 applies that curve across the spine and writes the `PE_ratio` column.

`N_hh = max(1, Pop2030 / household_size)`, with `Pop2030` the engine's own projection
(`SettlementProcessor.project_pop_and_urban`) from `PopStartYear` — not the base-year population.
`s05` writes `Pop2030`, `N_hh` and a reference column `N_hh_2020` (evaluated at the base-year
population, kept for comparison only) to the settlement dataset. `s06`, `s12` and every other solve
assert, on every settlement, that the spine's `Pop2030` equals the engine's own projection before
solving — a guard against sizing peaks on a different population from the one the energy demand is
computed on. The 2050 spine (`s12b`) is built the same way, from the 2050 scenario (38,083,385
people, urban share 0.672).

OnSSET then reads that column as a per-settlement `base_to_peak_load_ratio` (= 1 / `PE_ratio`) in
place of the single scalar it would otherwise use. **The allocation engine's cost equations are
unmodified**, but a patch to the OnSSET core is required, and is disclosed in the paper's
Methodology (§2.2.1): stand-alone PV originally received a hard-coded load factor of 0.9, so it alone
ignored the per-settlement peak. Every other technology already read the per-settlement column.
Correcting that one line is what makes the comparison symmetric across technologies. See
[`patches/README.md`](../patches/README.md).

## Reading the outputs

Outputs are per-settlement CSVs, one per arm. The columns that matter:

| Column | Meaning |
|---|---|
| `MinimumOverallCode2030` | the technology chosen |
| `MinimumOverallLCOE2030` | lifetime cost per kWh |
| `EnergyPerSettlement2030` | energy delivered — used to weight the LCOE |
| `InvestmentCost2030` | upfront capital |

**Use the 2030 columns.** The 2035 columns are *incremental*: for settlements already connected in
2030 they carry almost no additional energy, which produces meaningless LCOEs (values like 2.1, or the
99 sentinel). The same pathology applies to the 2050 incremental columns, which is why the 2050 result
uses a single-year endpoint run (`time_step = 30`) instead.

Two reporting cautions.

- **Capital and lifetime cost move together.** Under explicit peaks investment rises 41.2% and
  capacity 1.6%, alongside the 45.4% rise in lifetime cost. This is the physically expected direction:
  higher peaks require more capacity, which costs more to build.
- **Per-connection cost is now quotable, with one caveat.** The outlier problem is gone: no settlement
  exceeds $1 bn of investment, and `InvestmentPerConnection2030` has a mean of \$7,170 against a median
  of \$7,120 — a ratio of 1.01, i.e. no skew. The aggregate is \$4,159 per new connection. The remaining
  caveat is a period mismatch, which is real and must be stated whenever an absolute figure is
  quoted: `InvestmentCost2030` spans the full 2020–2035 horizon, including a second stand-alone
  installation, while `NewConnections2030` counts households connected in the 2020–2030 step only.

## Which technologies actually compete

Counts below are at 2030 in the R0 output
(`2026-08_final_lcoe_R0.csv`); the two diesel options are omitted because they are never least-cost.
Of the five remaining technologies, only three are ever costed, and for most settlements only one is:

| Technology | Settlements with a finite LCOE (R0) | Why |
|---|---|---|
| Stand-alone PV | 263,050 (97.2%) | — |
| Grid | 31,943 (11.8%) | limited by the extension algorithm's reach. 32,058 settlements are allocated to grid: the extra 115 are base-year electrified, so they carry no extension cost |
| Mini-grid PV hybrid | 2,258 (0.8%) | needs ≥ 100 households (`technology_options.min_mg_size`) |
| Mini-grid wind | **0** | the wind-hybrid optimiser fails to compile under numba; excluded by that failure, not on cost. Median wind capacity factor is 0.103 against PV's 0.232, so it is very unlikely to be competitive, but this is an assumption rather than a result |
| Mini-grid hydro | 6 | five identified hydro sites nationally, median 185 km away |

Counting technologies with a finite cost per settlement: **90.3% have exactly one**, 9.5% have two,
0.2% have three. The genuine contest is grid versus stand-alone PV, which is also why every
technology change in the central case is stand-alone PV → grid and no other transition occurs;
the Tier-2 and N_mid=10 variants carry a small number of other transitions.

### Where explicit peaks reach the levelised cost

The peak treatment is not applied symmetrically across the three live technologies, and this bounds
what the experiment measures:

- **Stand-alone PV** — full effect. `installed_capacity = peak_load / capacity_factor`, so the
  per-settlement peak ratio flows directly into capacity, capital and levelised cost.
- **Grid** — partial, and off the decision variable. Peaks enter T&D sizing through step functions
  (transformer counts are `np.ceil`), and `grid_capacity_investment` is accumulated into reported
  investment but *not* into the discounted cost stream from which the LCOE is formed. The allocation
  therefore cannot see it.
- **Mini-grid PV hybrid** — none. `hybrids.py`'s `calc_load_curve(tier, annual_demand)` builds the
  hourly profile from a fixed per-tier archetype; neither `hybrids.py` nor `hybrids_wind.py`
  references the peak ratio at all. Measured across all 2,258 settlements with a live mini-grid LCOE
  in both arms, the change from R0 to R1 is 0.00% at the 5th, 50th and 95th percentiles.

Holding the R0 allocation throughout (no settlement switches) and freezing stand-alone costs at their
R0 values re-derives the headline as −0.5%: the entire
measured effect travels through the stand-alone channel. The two missing channels pull in opposite
directions: opening the grid channel would raise costs, while mini-grid-eligible settlements are
large and therefore flatter under an explicit peak, so opening that channel could make mini-grids
cheaper and attenuate the measured effect (paper §4.2).

Seeding, arm byte-identity and the index invariant are set out in `REPRODUCING.md` §6.
