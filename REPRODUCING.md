# Reproducing the published results

Everything needed to re-run the experiment, in order. The published figures come from the
`grid3_central` configuration: rural Tier 3, `N_mid = 20`, seed 42.

## 1. Environment

Python 3.13 specifically — several pins (numpy 2.4.6, pandas 3.0.3, scipy 1.17.1) have no wheels for
other minor versions.

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

If you have no Python 3.13, [uv](https://docs.astral.sh/uv/) fetches one without touching the system:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.13
uv venv --python 3.13 .venv
uv pip install -r requirements.txt
```

`requirements.txt` includes `setuptools<81`, `geojson` and `requests`. These are dependencies of the
vendored OnSSET package rather than of the analysis code, and they were implicit in the environment
that produced the published results; a from-scratch install fails at import without them.

## 2. OnSSET, with the patch

The allocation engine is OnSSET at upstream commit `c154ece`, with the patch in `patches/` applied.
**The results do not reproduce without it.** It makes three changes, all documented inline at the point
of change:

1. `condition_df()` resets the DataFrame index after its sort. Without this, row positions and index
   labels diverge and `Technology.get_lcoe()` divides each settlement's peak load by a different
   settlement's capacity factor — silently, because the energy term cancels out of the levelised cost.
   See §7 and `test/test_index_alignment.py`.
2. `SettlementProcessor._assert_positional_index()` is added and called at the two points where that
   invariant matters, so the failure can never again be silent.
3. Stand-alone PV reads the per-settlement `AverageToPeakLoadRatio` like every other technology,
   instead of a hard-coded load factor; and its `cap_cost` accumulator is cast to float so
   non-integer capital costs are not truncated.

Clone it into `data/onsset_repo`, which is where `test/test_onsset_install.py` looks for its
test fixtures:

```bash
mkdir -p data
git clone https://github.com/onsset/OnSSET.git data/onsset_repo
cd data/onsset_repo && git checkout c154ece
git apply ../../patches/onsset-explicit-peak.patch
pip install -e . && cd ../..
```

## 3. Data

Not distributed with this repository — roughly 17 GB, under third-party licences. `docs/04_data_sources.md`
lists every source, its licence, and the directory layout the scripts expect under `data/`.

## 4. Run

Scripts run in numeric order; each writes what the next reads. **`PYTHONPATH` must point at the
repository root**: the scripts add `data/onsset_repo` and `scripts/` to `sys.path` themselves, but
Python puts only the *script's* directory on the path when a file is executed directly, so
`peak_preprocessor` is otherwise not importable.

```bash
cd zambia-explicit-peak
export PYTHONPATH="$(pwd)"

python scripts/s01_build_spine_clusters.py
python scripts/s02_build_spine_dispersed.py
python scripts/s03_build_spine_attributes.py
python scripts/s04_calibrate_base_year.py
python scripts/s05_compute_peak_ratios.py      # writes PE_ratio for N_mid 10, 20, 50
python scripts/s06_run_arms.py                 # the headline R0 vs R1 comparison
```

**Check `s06` before going further.** The acceptance test below must print ~100%; it printed 14.137%
under the defect described in §7, and every downstream number would be wrong:

```bash
python scripts/check_index_alignment.py data/onsset_outputs/<run>_R0.csv
python test/test_index_alignment.py
```

Robustness and reporting stages. The order matters in three places, marked below:

```bash
python scripts/s10_run_sizing_decomposition.py   # post-processing only, no re-solve; fastest first
python scripts/s07_run_demand_sensitivity.py     # rural Tier 2                     -> needed by s13
python scripts/s11_run_drought_oat.py            # drought-price generation cost

# 2050 endpoint. Use 2050only: the default mode reaches 100% electrification at the
# 2030 stage, leaving the 2050 columns incremental-only and their levelised costs meaningless.
python scripts/s12a_build_2050_peak_ratios.py
python scripts/s12b_build_2050_spine.py
python scripts/s12_run_2050_horizon.py 2050only        # R0 + R1_n20
python scripts/s12_run_2050_horizon.py 2050only_sweep  # R1_n10 and R1_n50; reuses that R0
python scripts/s12c_summarise_2050.py scripts/outputs/2050only_grid3_lcoe_R0.csv \
    scripts/outputs/2050only_grid3_lcoe_R1_n20.csv 2050

python scripts/s08_run_global_sensitivity.py     # Morris + LHS; ~64 min       -> needed by s09, s13
# s08 prints the bias-correction factor. Set BIAS_FACTOR in s09 from it before running s09.
python scripts/s09_run_oat_checks.py             # grid-side OAT               -> needed by s13
python scripts/s13_generate_figures.py           # last: reads s07, s08 and s09 outputs
```

Two optional analyses, independent of the above:

```bash
python scripts/s14_paper_numbers.py <run-label>              # every quoted figure, in one table
python scripts/s15_run_capex_curve_sensitivity.py --self-test
python scripts/s15_run_capex_curve_sensitivity.py smooth     # continuous capital-cost curve
python scripts/s15_run_capex_curve_sensitivity.py monotone   # and with the >1 kW premium removed
python scripts/s16_run_corrected_conventions.py             # full reinvestment schedule
python scripts/s17_run_fitted_anchors.py                    # curve fitted to the two measured anchors
python scripts/check_spine_integrity.py                     # 22 hard checks on the spine, no re-run
```

`s16` returns +50.56% against the +49.92% headline: repricing the only channel that carries the effect
by 5.9% moves the result by 0.64 pp. `s17` returns +35.6% with 33,549 stand-alone-to-grid switches,
inside the swept band, and removes the `N_mid` assumption by fitting the curve to the study's own two
measured anchors instead.

## 5. What you should get

All values below are from the run of 2026-08-16, the first with the index-alignment defect of §7
corrected. Figures from earlier runs of this repository are superseded and should not be quoted.

From `s06`, on the 2030 columns, at rural Tier 3 and `N_mid = 20`, over 270,526 settlements:

| Quantity | R0 (energy-only) | R1 (explicit peak) | Change |
|---|---|---|---|
| Energy-weighted LCOE | 0.2757 USD/kWh | 0.4133 USD/kWh | **+49.92%** |
| Aggregate investment to 2030 | USD 15.58 bn | USD 22.68 bn | +45.59% |
| New capacity to 2030 | 2,664 MW | 2,743 MW | +2.95% |
| Settlements changing technology | — | — | 34,461 (12.74%) |

Every one of the 34,461 moves is stand-alone PV to grid; no other transition occurs. They carry
0.44 M people, 1.8% of the 2030 population.

Technology split at 2030 — grid 32,058 → 66,519 settlements, stand-alone PV 236,843 → 202,382,
mini-grid PV hybrid 1,625 in both arms.

`N_mid` sweep: **+34.1% / +49.9% / +70.6%** for `N_mid` 10 / 20 / 50, with 33,603 / 34,461 / 34,862
settlements moving from stand-alone solar to grid. The switch count is stable across the sweep; the
cost change is not, because `N_mid` governs how many settlements cross the 1 kW per household step in
OnSSET's stand-alone capital-cost schedule (`s15` quantifies this).

From `s07`, rural Tier 2: **−2.2% / +3.3% / +8.4%** across the same sweep, with 12 / 72 / 436
switches. The script's verdict is `FRAGILE: direction or sign reversal at Tier 2`. This is a boundary
condition, not a confirmation: at Tier 2 no settlement crosses the capital-cost step, OnSSET's tier
table already assumes ρ = 2.50 rather than 2.00, and stand-alone settlements carry 7.5% of national
energy rather than 17.5%.

From `s12` `2050only`, at the projected 2050 population: **+34.9%** central with 32,157 switches,
sweep band **+23.1% to +50.9%** across `N_mid` ∈ {10, 50}. Note that this band overlaps the 2030 band.

From `s08`: LHS (200 samples, bias-corrected) 5th–50th–95th **+23.7% / +55.5% / +77.2%**. Morris μ*
ranking Rural_tier (60.1) > N_mid (14.5) > MaxGridDist_km (10.7) > SA_PV_capex_mult (6.2) >
Discount_rate (2.2) > Diesel_price (0.0), no sign reversal across all 56 trajectory evaluations. The
emulator failed its own validation threshold (RMSE 11.48 pp against a 5.0 pp limit, R² = 0.520) and
all 200 samples were therefore evaluated with the full model — check the `method` column is
`full_OnSSET` throughout.

## 6. Determinism

- All random draws are seeded (`seed = 42`). The PV-hybrid optimiser varied by 0.2% between unseeded
  runs; seeding removes it.
- Both arms are built from one in-memory spine with only the peak column overwritten, and a pre-run
  assertion fails the run if any shared column differs. The two arms are byte-identical in every
  column except the peak.
- Read costs on the **2030** columns. The 2035 and 2050 incremental columns carry almost no energy for
  settlements already connected and produce meaningless levelised costs; `docs/01_pipeline.md`
  explains this. For a 2050 headline use `s12_run_2050_horizon.py 2050only`, which solves a single
  analysis year at 2050 demand.
- The DataFrame index must equal its row order whenever costs are computed. `condition_df()` enforces
  it and `_assert_positional_index()` raises if it is ever violated. This is not a style rule: §7
  explains what happens without it.

## 7. The index-alignment defect (fixed 2026-08-16)

Any result produced by this repository before 2026-08-16 is wrong and should not be cited.

`SettlementProcessor.condition_df()` sorted the settlements by latitude and longitude without
resetting the index, so the frame's row positions and its index labels became two different orderings.
Inside `Technology.get_lcoe()`, `peak_load` is built from a numpy array and is therefore labelled by
position, while `capacity_factor` is passed straight off the frame and is labelled by index. Pandas
aligns those on labels, so **every settlement's peak load was divided by a different settlement's
capacity factor**.

Upstream this is masked because `condition_df()` is normally followed by a CSV write and re-read,
which silently repairs the index. This pipeline passes the frame in memory, which is faster and
otherwise correct, and which exposed the latent fragility.

It stayed hidden because for stand-alone PV the T&D cost is zero, so

    LCOE = cap_cost x (A + om x D) / (ATR x GHI x D)

— the energy term cancels top and bottom. Levelised cost stayed plausible while capacity and
investment were wrong by orders of magnitude. Diagnosis and verification:

| | before the fix | after |
|---|---|---|
| stand-alone settlements satisfying `capacity = E / (ATR x GHI)` | **14.137%** | **100.000%** |
| total stand-alone capacity, R0 | 5,186 MW | 1,087 MW |
| total investment, R0 | USD 75.5 bn | USD 15.58 bn |
| headline ΔLCOE% | +36.87% | +49.92% |
| stand-alone-to-grid switches | 17,787 | 34,461 |

The defect suppressed the effect being measured rather than creating it, and it produced the
"capital falls while lifetime cost rises" result that earlier drafts had to explain; corrected,
capital and capacity both rise.

Guard rails now in place: the index reset, `_assert_positional_index()` at the two points where the
invariant matters, `scripts/check_index_alignment.py` as an acceptance test on any run output, and
`test/test_index_alignment.py` as a regression test.

## Reproducibility: the hybrid-LUT cache (fixed 2026-08-12)

*Historical. The settlement counts in this section belong to the pre-2026-08-16 series and are
superseded by §5 and §7; the section is retained because the fix it describes is still in force
and explains why the OAT block rebuilds its lookup table per arm.*

`s06_run_arms.py` rebuilds the PV-hybrid differential-evolution lookup table inside each arm,
immediately after `np.random.seed(42)`. `s09_run_oat_checks.py` originally built the table once at the
top of the script and reused it (`pv_lut_cache`) across both the LHS full-spine validation and the OAT
block. Because the OAT therefore drew from the random stream at a different point, its mini-grid costs
differed marginally, and that was enough to flip one settlement at the grid-extension margin:

- settlement index 72830, 521.8 people, 31.814 E / 13.930 S, 7.4 km from the nearest MV line
- headline run (`s06`): assigned **Grid**, LCOE 0.1395 USD/kWh (8th percentile of grid assignments)
- cached-LUT OAT run: assigned **stand-alone PV**, LCOE 4.5113 USD/kWh
- consequence: OAT reported 17,786 stand-alone-to-grid switches instead of **17,787**

**Fix.** The OAT block now passes `pv_lut_cache=None`, so each arm rebuilds the table exactly as `s06`
does. The switch-count gate is correspondingly tightened to require an exact match
(`OAT_SWITCH_TOL = 0`). The LHS validation block still uses the cache: its comparison is internal to
itself (subsample-corrected versus full-spine for the same sample), so cache reuse is consistent there
and its published values are unaffected.

**Cost.** Rebuilding the table adds roughly two minutes per arm, so the OAT block runs in about 35
minutes rather than 19.

**Re-run completed, 2026-08-16**, after the index-alignment fix of §7. The central variant reproduced
`s06` to six decimal places and **exactly 34,461** switches — the switch-count gate passed with zero
residual:

| variant | grid_cap_cost | grid_gen_cost | ΔLCOE% | switches |
|---|---|---|---|---|
| central | 1441.10 | 0.013 | 49.685932 | 34,461 |
| cap−30pct | 1008.77 | 0.013 | 49.685932 | 34,461 |
| cap+30pct | 1873.43 | 0.013 | 49.685932 | 34,461 |
| gen−drought | 1441.10 | 0.050 | 45.444815 | 35,092 |

gen−drought against central: −4.24 pp on ΔLCOE% and +1.83% on switches.

The two capacity-cost rows are identical to central to six decimal places, and necessarily so: OnSSET
accumulates `grid_capacity_investment` into the reported investment total but not into the discounted
cost stream from which the LCOE is formed (`onsset.py`, `get_lcoe`), so that parameter cannot move
either the levelised cost or the allocation made on it. The generation-cost variant, which reaches the
LCOE through the fuel term, is the informative grid-side test. The paper states this in §3.5 and
Supplementary S4.
