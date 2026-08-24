# The pipeline

Every script lives in `scripts/`, named `sNN_<what it does>.py`, and runs in numeric order. Each stage
writes files the next stage reads.

The `s` prefix is deliberate: some later stages import functions from earlier ones, and a filename
beginning with a digit (`06_run_arms.py`) cannot be imported by Python. This is the same reason OnSSET
itself numbers only its notebooks and leaves its package modules unnumbered.

## Run order

| Stage | Script | What it does | Key output |
|---|---|---|---|
| 01 | `s01_build_spine_clusters.py` | Builds settlement polygons from GRID3: geometry, WorldPop population, urban/rural class, admin-1 | cluster spine |
| 02 | `s02_build_spine_dispersed.py` | Recovers the ~18% of population living outside any GRID3 polygon by aggregating residual pixels to ~2.8 km cells, so the spine reconciles to the national total | **combined spine, 270,526 settlements** |
| 03 | `s03_build_spine_attributes.py` | Computes every OnSSET spatial column: solar and wind resource, travel time, road and grid distances (ZESCO MV lines, NEP planned extensions, transformers) | spine with attributes |
| 04 | `s04_calibrate_base_year.py` | Calibrates who is already electrified in the base year against the national survey. Variant A (2 km transformer gate, NEAS-2023) is the one used | calibrated spine |
| 05 | `s05_compute_peak_ratios.py` | **The intervention.** Adds `N_hh` and `PE_ratio` per settlement using `peak_preprocessor/`. Writes one spine per swept `N_mid` ∈ {10, 20, 50} | PE-augmented spines |
| 06 | `s06_run_arms.py` | The main event: solves R0 and R1 through OnSSET and compares them | R0/R1 outputs |
| 07 | `s07_run_demand_sensitivity.py` | Repeats the comparison at rural Tier 2 (219 kWh/HH/yr). One changed value; everything else identical | Tier-2 outputs |
| 08 | `s08_run_global_sensitivity.py` | Morris elementary-effects screen (6 parameters, 8 trajectories, 56 paired evaluations) plus Latin-hypercube uncertainty propagation | sensitivity results |
| 09 | `s09_run_oat_checks.py` | One-at-a-time checks on the grid side, and full-spine validation of the sensitivity subsample bias correction | OAT results |
| 10 | `s10_run_sizing_decomposition.py` | Post-processes existing outputs to recompute the headline with only a fraction `f` of stand-alone capital scaled by peak. Produces the +21.0% / +30.6% / +49.9% band | f-band |
| 11 | `s11_run_drought_oat.py` | Re-runs the grid-cost OAT at 2024 drought import prices (0.17–0.26 USD/kWh) | drought OAT |
| 12 | `s12_run_2050_horizon.py` | Re-solves both arms at the projected 2050 population. Helpers: `s12a` builds the 2050 peak ratios, `s12b` the 2050 spine, `s12c` summarises | 2050 outputs |
| 13 | `s13_generate_figures.py` | Regenerates every figure in the paper from current outputs | figures |

One supporting module sits alongside them: `scripts/onsset_helpers.py` holds the shared loaders (solar
and wind profiles, config) used from stage 06 onward.

## The intervention, in detail (stage 05)

`peak_preprocessor/` is the only thing this study adds to OnSSET. It contains one module:

- **`pe_diversity.py`** — the peak-to-energy model itself. Two functions: `compute_beta()` derives the
  curve's exponent from the measured anchors, and `pe_from_n()` returns the ratio for a given
  connection count.
Stage 05 applies that curve across the spine and writes the `PE_ratio` column.

OnSSET then reads that column as a per-settlement `base_to_peak_load_ratio` (= 1 / `PE_ratio`) in
place of the single scalar it would otherwise use. **The allocation engine's cost equations are
unmodified**, but a patch to the OnSSET core is required, and is disclosed in the paper's
Methodology (§2.2.1): stand-alone PV originally received a hard-coded load factor of 0.9, so it alone
ignored the per-settlement peak. Every other technology already read the per-settlement column.
Correcting that one line is what makes the comparison symmetric across technologies — and note the
direction: the bug was *suppressing* the effect, not creating it. See
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

Two reporting cautions. **Both were rewritten on 2026-08-16**: they described symptoms of the
index-alignment defect (`REPRODUCING.md` §7), not properties of the model, and the earlier versions
said the opposite of what is true.

- **Capital and lifetime cost move together.** Under explicit peaks investment rises 45.6% and
  capacity 2.9%, alongside the 49.9% rise in lifetime cost. This is the physically expected direction:
  higher peaks require more capacity, which costs more to build. The previous version of this note
  claimed capital *falls*; that was an artefact of misaligned capacity accounting.
- **Per-connection cost is now quotable, with one caveat.** The outlier problem is gone: no settlement
  exceeds $1 bn of investment, and `InvestmentPerConnection2030` has a mean of \$7,170 against a median
  of \$7,120 — a ratio of 1.01, i.e. no skew. The aggregate is \$4,159 per new connection. The remaining
  caveat is a period mismatch, which is real and must be stated whenever an absolute figure is
  quoted: `InvestmentCost2030` spans the full 2020–2035 horizon, including a second stand-alone
  installation, while `NewConnections2030` counts households connected in the 2020–2030 step only.

## Which technologies actually compete

Worth knowing before reading any allocation result. Of the five technologies OnSSET can choose, only
three are ever costed, and for most settlements only one is:

| Technology | Settlements with a finite LCOE (R0) | Why |
|---|---|---|
| Stand-alone PV | 263,050 (97.2%) | — |
| Grid | 31,943 (11.8%) | limited by the extension algorithm's reach |
| Mini-grid PV hybrid | 2,258 (0.8%) | needs ≥ 100 households (`technology_options.min_mg_size`) |
| Mini-grid wind | **0** | the wind-hybrid optimiser fails to compile under numba; excluded by that failure, not on cost. Median wind capacity factor is 0.103 against PV's 0.232, so it is very unlikely to be competitive, but this is an assumption rather than a result |
| Mini-grid hydro | 6 | five identified hydro sites nationally, median 185 km away |

Counting technologies with a finite cost per settlement: **90.3% have exactly one**, 9.5% have two,
0.2% have three. The genuine contest is grid versus stand-alone PV, which is also why every
technology change in the results is stand-alone PV → grid and no other transition occurs.

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
measured effect travels through the stand-alone channel. Because the two missing channels would both
*raise* costs under explicit peaks, the reported effect is a lower bound on what a model with explicit
peaks in all three options would produce.

## Reproducibility

- All random draws are seeded (`seed = 42`).
- R0 and R1 are built from one in-memory spine with only the peak column overwritten, so the two arms
  are verified byte-identical in every shared column.
- Every contested parameter lives in `config/config.yaml`, not in code. `technology_options.min_mg_size`
  was moved there on 2026-08-16; it had been a literal in four scripts despite deciding which
  technologies exist.
- The DataFrame index must equal its row order wherever costs are computed. `condition_df()` enforces
  it; `_assert_positional_index()` raises if it is broken; `scripts/check_index_alignment.py` is the
  acceptance test on any run output and must report ~100%.
