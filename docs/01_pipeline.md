# The pipeline

Every script lives in `scripts/`, named `sNN_<what it does>.py`, and runs in numeric order. Each stage
writes files the next stage reads.

The `s` prefix is deliberate: some later stages import functions from earlier ones, and a filename
beginning with a digit (`06_run_arms.py`) cannot be imported by Python. This is the same reason OnSSET
itself numbers only its notebooks and leaves its package modules unnumbered.

## Run order

| Stage | Script | What it does | Key output |
|---|---|---|---|
| 00 | `s00_validate_inputs.py` | Pre-run gate. Checks the spine, calibration and parameters are internally consistent before anything expensive runs. Produces a pass/fail table | validation report |
| 01 | `s01_build_spine_clusters.py` | Builds settlement polygons from GRID3: geometry, WorldPop population, urban/rural class, admin-1 | cluster spine |
| 02 | `s02_build_spine_dispersed.py` | Recovers the ~18% of population living outside any GRID3 polygon by aggregating residual pixels to ~2.8 km cells, so the spine reconciles to the national total | **combined spine, 270,526 settlements** |
| 03 | `s03_build_spine_attributes.py` | Computes every OnSSET spatial column: solar and wind resource, travel time, road and grid distances (ZESCO MV lines, NEP planned extensions, transformers) | spine with attributes |
| 04 | `s04_calibrate_base_year.py` | Calibrates who is already electrified in the base year against the national survey. Variant A (2 km transformer gate, NEAS-2023) is the one used | calibrated spine |
| 05 | `s05_compute_peak_ratios.py` | **The intervention.** Adds `N_hh` and `PE_ratio` per settlement using `peak_preprocessor/`. Writes one spine per swept `N_mid` ∈ {10, 20, 50} | PE-augmented spines |
| 06 | `s06_run_arms.py` | The main event: solves R0 and R1 through OnSSET and compares them | R0/R1 outputs |
| 07 | `s07_run_demand_sensitivity.py` | Repeats the comparison at rural Tier 2 (219 kWh/HH/yr). One changed value; everything else identical | Tier-2 outputs |
| 08 | `s08_run_global_sensitivity.py` | Morris elementary-effects screen (6 parameters, 8 trajectories, 56 paired evaluations) plus Latin-hypercube uncertainty propagation | sensitivity results |
| 09 | `s09_run_oat_checks.py` | One-at-a-time checks on the grid side, and full-spine validation of the sensitivity subsample bias correction | OAT results |
| 10 | `s10_run_sizing_decomposition.py` | Post-processes existing outputs to recompute the headline with only a fraction `f` of stand-alone capital scaled by peak. Produces the +14.1% / +21.7% / +36.9% band | f-band |
| 11 | `s11_run_drought_oat.py` | Re-runs the grid-cost OAT at 2024 drought import prices (0.17–0.26 USD/kWh) | drought OAT |
| 12 | `s12_run_2050_horizon.py` | Re-solves both arms at the projected 2050 population. Helpers: `s12a` builds the 2050 peak ratios, `s12b` the 2050 spine, `s12c` summarises | 2050 outputs |
| 13 | `s13_generate_figures.py` | Regenerates every figure in the paper from current outputs | figures |

Two supporting modules sit alongside them: `scripts/onsset_helpers.py` holds shared loaders (solar and
wind profiles, config) used from stage 06 onward, and `scripts/plot_pe_distribution.py` is a small
figure helper.

## The intervention, in detail (stage 05)

`peak_preprocessor/` is the only thing this study adds to OnSSET. It contains two modules:

- **`pe_diversity.py`** — the peak-to-energy model itself. Two functions: `compute_beta()` derives the
  curve's exponent from the measured anchors, and `pe_from_n()` returns the ratio for a given
  connection count.
- **`compute_settlement_pe.py`** — applies that curve across the spine and writes the `PE_ratio`
  column.

OnSSET then reads that column as a per-settlement `base_to_peak_load_ratio` (= 1 / `PE_ratio`) in
place of the single scalar it would otherwise use. **The allocation engine itself is unmodified.**

One patch to the OnSSET core was required, and is documented in the paper: stand-alone PV originally
received a hard-coded load factor of 0.9, so it alone ignored the per-settlement peak. Every other
technology already read the per-settlement column. Correcting that one line is what makes the
comparison symmetric across technologies — and note the direction: the bug was *suppressing* the
effect, not creating it.

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

Two further reporting cautions, both learned the hard way:

- **Compare lifetime cost, not capital.** Capital *falls* under explicit peaks while lifetime cost
  *rises*. Reading only `InvestmentCost2030` gives the opposite of the correct conclusion.
- **Do not quote cost per connection.** Eight outlier settlements account for 47% of investment, and
  8,276 zero-capacity connections send the per-connection figure to infinity. Median per-household
  lifecycle cost (~$7k) is the defensible statistic.

## Reproducibility

- All random draws are seeded (`seed = 42`).
- R0 and R1 are built from one in-memory spine with only the peak column overwritten, so the two arms
  are verified byte-identical in every shared column.
- Every contested parameter lives in `config/config.yaml`, not in code.
