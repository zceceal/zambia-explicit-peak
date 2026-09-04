# Reproducing the published results

Everything needed to re-run the experiment, in order. The published figures come from rural Tier 3
(`config.yaml`'s `demand_tiers.rural_tier_large`/`rural_tier_small`), central `N_mid = 20` and seed 42
— the latter two hardcoded in `s06_run_arms.py`, not read from any config key. Output files carry the
label `RUN_LABEL = "2026-08_final_lcoe"`, also hardcoded there. (`config.yaml` does have a `run_label`
key, but nothing reads it — don't infer anything from its value.)

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

**Known environment issue, not a defect in this repository's code:** under numba 0.65.1 / Python
3.13.15, the wind-hybrid optimiser in the vendored OnSSET (`hybrids_wind.py`) fails to JIT-compile
(`No implementation of function Function(<built-in function getitem>)`, a numba typing error on
`net_load[int(hour)]`) and falls back to `LCOE = 99`, disabling `MG_Wind` for every arm. This changes
no reported number — `MG_Wind` is zero settlements in every technology split, canonical and
reproduced alike — but it means a reader watching a run for the first time will see a large traceback
printed for every arm, and on an environment where numba treats this as a hard error rather than a
caught exception the pipeline would stop. Confirmed independently in a from-scratch clean-room clone
2026-08-28/29.

## 2. OnSSET, with the patch

The allocation engine is OnSSET at upstream commit `c154ece`. The exact modifications are recorded as
commit `cd64900445feb6a41c03c86cfe3d46c2d30cfee8` on the `explicit-peak-thesis` branch of the vendored
copy at `data/onsset_repo` — a local branch, not pushed to any remote, built directly on top of
upstream `c154ece` with no rewriting of upstream history. `patches/onsset-explicit-peak.patch` is the
human-readable record of that same commit, regenerated 2026-08-24 as `git diff c154ece cd64900` so it
reconstructs the engine byte-for-byte (verified: applying it to a clean `c154ece` checkout and diffing
the result against the live `onsset.py` returns no difference). **The results do not reproduce without
it.** It makes six changes, all documented inline at the point of change:

1. `condition_df()` resets the DataFrame index after its sort. Without this, row positions and index
   labels diverge and `Technology.get_lcoe()` divides each settlement's peak load by a different
   settlement's capacity factor — silently, because the energy term cancels out of the levelised cost.
   See §7 and `test/test_index_alignment.py`.
2. `SettlementProcessor._assert_positional_index()` is added and called at the two points where that
   invariant matters, so the failure can never again be silent.
3. `no_of_mv_lines` is computed against the medium-voltage line's own amperage rating rather than a
   75 kVA distribution-transformer rating it was previously (and mistakenly) derived from — applied at
   both call sites. Affects 371 of 270,526 settlements (0.137%, ~0.09% of aggregate investment); not
   the source of the headline effect. See `patches/README.md`.
4. Stand-alone PV reads the per-settlement `AverageToPeakLoadRatio` like every other technology,
   instead of a hard-coded load factor.
5. `Technology.get_lcoe`'s `cap_cost` accumulator (shared by every technology, not just
   stand-alone PV) is cast to float so non-integer capital costs are not truncated.
6. `CORRECTED_CONVENTIONS["full_reinvestment"]` (default `False`) and the reinvestment-schedule
   refactor it switches: OnSSET books at most one reinvestment regardless of horizon length and
   compensates with a salvage term; with the switch on, an asset already installed is replaced every
   `tech_life` years for as long as it generates. Off by default — the central case and every other
   reported number reproduce unmodified OnSSET's convention.
   `scripts/s16_run_corrected_conventions.py` sets it `True` for the labelled robustness variant this
   file quotes below; without this change in the patch, that script raised `AttributeError` on a
   freshly-patched checkout even though the headline still reproduced.

Reproducers with access to the vendored copy and its branch can check out `cd64900` directly. Anyone
else clones upstream and applies the patch, which is verified equivalent:

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

python scripts/s01_build_spine_clusters.py     # ~1.3 GB peak memory (recorded in the script's own comment)
python scripts/s02_build_spine_dispersed.py
python scripts/s03_build_spine_attributes.py
python scripts/s04_calibrate_base_year.py
python scripts/s05_compute_peak_ratios.py      # writes PE_ratio for N_mid 10, 20, 50
python scripts/s06_run_arms.py                 # the headline R0 vs R1 comparison
```

`s01`–`s05` together measured **~5.1 min** (95s + 70s + 105s + 20s + 18s) in an independent clean-room
run 2026-08-28. `s06`'s four arms (R0, R1 at `N_mid` 10/20/50) measured **~9–15 min** in that same run;
one arm was seen to take 122.7 min against ~2.5 min for its three siblings on a loaded machine with no
code-path difference between them — treat single-run timings here as upper-ish bounds on contended
hardware, not clean benchmarks.

**Check `s06` before going further.** The acceptance test below must print ~100%; it printed 14.137%
under the defect described in §7, and every downstream number would be wrong:

```bash
python scripts/check_index_alignment.py data/onsset_outputs/<run>_R0.csv
python test/test_index_alignment.py
```

Robustness and reporting stages. The order matters in three places, marked below:

```bash
python scripts/s10_run_sizing_decomposition.py   # post-processing only, no re-solve; fastest first
python scripts/s07_run_demand_sensitivity.py     # rural Tier 2                     -> needed by s13; measured 4.8 min
python scripts/s11_run_drought_oat.py            # drought-price generation cost; 4 variants, 674.6s total
                                                  # (recorded in results/summary/2026-08_final_oat_drought_price.csv's elapsed_s column)

# 2050 endpoint. Use 2050only: the default mode reaches 100% electrification at the
# 2030 stage, leaving the 2050 columns incremental-only and their levelised costs meaningless.
python scripts/s12a_build_2050_peak_ratios.py
python scripts/s12b_build_2050_spine.py
python scripts/s12_run_2050_horizon.py 2050only        # R0 + R1_n20
python scripts/s12_run_2050_horizon.py 2050only_sweep  # R1_n10 and R1_n50; reuses that R0
python scripts/s12c_summarise_2050.py scripts/outputs/2050only_grid3_lcoe_R0.csv \
    scripts/outputs/2050only_grid3_lcoe_R1_n20.csv 2050
# s12a+s12b+both s12 horizon runs measured ~8 min total (2026-08-28 clean-room run)

python scripts/s08_run_global_sensitivity.py     # Morris + LHS; ~64 min       -> needed by s09, s13
                                                  # measured 63.4 min (2026-08-28 clean-room run)
# s08 prints the bias-correction factor. Set BIAS_FACTOR in s09 from it before running s09.
python scripts/s09_run_oat_checks.py             # grid-side OAT               -> needed by s13
                                                  # ~2 min per arm; --lhs-only runs the LHS validation block
                                                  # alone. Per-variant times are in the elapsed_s column of
                                                  # each block's results/summary CSV; they are machine-load
                                                  # dependent and are not upper bounds.
python scripts/s13_generate_figures.py           # last: reads s07, s08 and s09 outputs; measured 36.4s
python scripts/fig_r0r1_allocation_map.py [run-label]   # paper Figure 2: R0/R1 technology allocation maps
```

`fig_r0r1_allocation_map.py` is kept separate from `s13` because it reads the two arm outputs
directly rather than the summary tables, and because it is drawn at its printed width (0.66x
textwidth) rather than scaled down by LaTeX, which is what previously rendered its panel titles
at 6.2 pt.

No advance runtime or memory figure is available for any other stage above or below (`s02`, `s04`,
`s14`, `fig_r0r1_allocation_map.py`, `s19`, `s20`, the acceptance checks, or the tests) — none is
recorded anywhere in the repository, so none is stated here rather than estimated. `s01`, `s03`, `s07`,
`s08`, `s09`, `s10` (6.8s), `s12`/`s12a`/`s12b`/`s12c`, `s13`, `s15`, `s16`, `s17` and `s18` are all
measured above or below, from an independent clean-room reproduction 2026-08-28/29 — see also §8.

Two optional analyses, independent of the above:

```bash
python scripts/s14_paper_numbers.py <run-label>              # every quoted figure, in one table;
                                                              # also writes results/summary/<run-label>_paper_numbers.csv
python scripts/s15_run_capex_curve_sensitivity.py --self-test
python scripts/s15_run_capex_curve_sensitivity.py smooth     # continuous capital-cost curve
python scripts/s15_run_capex_curve_sensitivity.py monotone   # and with the >1 kW premium removed
python scripts/s16_run_corrected_conventions.py             # full reinvestment schedule; measured 4.8 min
python scripts/s17_run_fitted_anchors.py                    # curve fitted to the metered Tum mini-grid
                                                              # and Zambia's own IRP load-factor assumption
                                                              # measured 2.6 min (plus <1s --self-test)
python scripts/s18_run_hhsize_sensitivity.py                 # rural household size 4.5 / 5.5 vs census 5.0; four arms
                                                              # measured 9.0 min (README previously said ~7 min)
python scripts/s19_band_and_channel_decomposition.py         # step-crossing and channel-freeze decomposition, no re-solve -> 2026-08_final_band_and_channel_decomposition.csv
python scripts/s20_provincial_rho.py                        # provincial peak-to-mean comparison against REMP Table 9,
                                                              # no re-solve -> 2026-08_final_provincial_rho.csv
python scripts/s21_run_calibration_gate_sensitivity.py      # base-year gate transformer OR MV < 2 km vs the published
                                                              # transformer gate; two arms -> 2026-09-02_calibration_gate_sensitivity.csv
python scripts/check_mv_sources.py                          # which layer sets each settlement's MV distance, no re-solve
                                                              # -> 2026-09-02_mv_distance_sources.csv
python scripts/s22_run_mv_layer_sensitivity.py              # ZESCO record as the only MV layer vs the published minimum
                                                              # over ZESCO, Meta, OSM; two arms -> 2026-09-02_mv_layer_sensitivity.csv
python scripts/s24_switcher_profile.py                      # switcher profile: rural share, base-year household
                                                            # distribution, population at 2030 (paper §3.3)
python scripts/s23_summarise_variants.py                    # Tier-2, 2050, anchor-fitted, schedule, reinvestment and
                                                              # single-household summaries from existing outputs, no re-solve
                                                              # -> 2026-09-02_variant_summaries.csv
python scripts/check_spine_integrity.py                     # 21 hard checks on the spine, no re-run
```

`s15 --self-test` (100.000% agreement, instant) then `smooth` and `monotone` measured 4.5 min and 4.3
min respectively.

`s16` returns +50.56% against the +49.92% headline: repricing the only channel that carries the effect
by 5.9% moves the result by 0.64 pp. `s17` returns **+49.37%** with **34,461** stand-alone-to-grid
switches (re-run 2026-08-27, exact two-point solve, after correcting the Zambian calibration point —
see below), inside the swept band, and removes the `N_mid` assumption by fitting the curve to the
metered Tum mini-grid and Zambia's own IRP national residential load-factor assumption instead (the
IRP states residential load factor as constant at 68.5%; it does not measure a national peak-to-mean
ratio directly — Table 3.01's 769 MW and 4,618 GWh are both generated from that one assumption, so
rho = 769 / (4,618,000 / 8,760) = 1.4587 — the table's own peak over its own mean, not 1/0.685 (which
gives 1.4599; the two differ only because 769 MW is itself rounded in the source table) — is a
planning parameter, not an independent observation). This is materially
closer to the +49.92% central case than the figures an earlier, misattributed version of this
calibration point produced (+35.6%, 33,549 switches): the corrected point (rho = 1.4587 at
N ~ 1.0e6, IRP Table 3.01) implies a solved equivalent `N_mid` of 19.49, next to the central case's
assumed 20, rather than the 10.6 implied by the old, misattributed figure.
`s18` perturbs the census rural household size (5.0) by ±10% and returns
**+48.10%** with 33,605 stand-alone-to-grid switches at 4.5 persons, and **+51.62%** with 34,694
switches at 5.5 — a band narrower than the `N_mid` sweep, so household size is not a material driver
of the headline.

## 5. What you should get

`ls data/onsset_outputs/2026-08_final_*` returns far more than the twelve files below, because the
one-at-a-time grid-cost sensitivity runs (`2026-08_final_oat_*`) share the same `2026-08_final` prefix.
They are a separate sensitivity, re-solved on the unchanged spine (`s09` reads
`data/processed/zambia_grid3_spine_pe_n20.csv` directly, without rebuilding it), not additional
full-spine solves. The twelve full-spine solves behind every headline figure are:

- `2026-08_final_lcoe_{R0, R0_ruralT2, R1_n10, R1_n20, R1_n50, R1_ruralT2_n10, R1_ruralT2_n20,
  R1_ruralT2_n50}.csv` — the eight primary solves (rural Tier 3 and Tier 2, `N_mid` swept where R1)
- `2026-08-21_hhsize_*` — the four household-size solves, from `s18` above

Four further solves are the input sensitivities added on 2026-09-02, not part of the twelve:

- `2026-09-02_txormv_*` — the transformer-or-MV base-year gate, from `s21`
- `2026-09-02_mvzesco_*` — the ZESCO-only MV layer, from `s22`

`results/summary/2026-08_final_provincial_rho.csv`, from `s20` (no re-solve, reads `R1_n20` only), is
the source for the provincial peak-to-mean comparison in §4.4.

`results/summary/2026-08_final_lcoe_paper_numbers.csv`, from `s14`, is the machine-readable source for
every number in this section and in the paper's Table 2, §3.1 and §3.2. **Do not use
`results/summary/2026-08_final_lcoe_tech_split.csv`'s `population` column for a population share of the
2030 allocation** — that column is base-year (`Pop`, ~18.38 M total), not the projected 2030 population
(`Pop2030`, 24.38 M total) the paper quotes; using it gives, for example, a grid share of 58.35% where
the paper states 62.8%. `s14`'s own technology-split table and `2026-08_final_lcoe_paper_numbers.csv`
use `Pop2030` throughout and reproduce the paper's figures exactly.

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
Discount_rate (2.2) > Diesel_price (0.0). ΔLCOE% itself was positive in all 56 underlying model
evaluations; individual elementary effects are not all positive (16 of 48 are negative, chiefly for
Discount_rate and MaxGridDist_km, whose higher settings reduce the effect) — the two claims are about
different quantities. The
emulator failed its own validation threshold (RMSE 11.44 pp against a 5.0 pp limit, R² = 0.524) and
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

## 8. Independent clean-room reproduction (2026-08-28/29)

A from-scratch reproduction — fresh `git clone` of `origin/main`, fresh `python3.13 -m venv`, fresh
`pip install -r requirements.txt`, fresh OnSSET clone at `c154ece` with the patch applied — was carried
out independently of the working copy that produced the published results. Starting from the
**published spine** (`data/processed/zambia_grid3_spine_pe_n{10,20,50}.csv`, committed nowhere but
distributed as described in §3), every one of the following reproduced **byte-for-byte (SHA-256)**: the
four headline solves (R0, R1 at `N_mid` 10/20/50), the rural-Tier-2 family, the 2050 family, `s10`,
`s15` (both variants), `s16`, `s17`, `s18`, `s19`, and all eight `s08` result files (Morris + LHS,
including the `method` column and the emulator-validation RMSE). `s09`'s grid-side OAT table matched
the published figures to six decimal places. That is the strongest form this reproducibility claim can
take, and it holds for every stage that starts from the published spine.

**The spine rebuild, resolved.** The published spine (`data/processed/zambia_grid3_spine_pe_n20.csv`,
and the `zambia_grid3_calib_distgate.csv` it derives from) is dated 1 July 2026; the repository's first
commit, `def8184`, is dated 29 July. The clean-room rebuild from the current `s01`–`s05` reproduced
`PE_ratio` and `N_hh` exactly on all 270,526 rows but not `TransformerDist`: 247,676 rows (91.6%)
differed, `ElecPopCalib`/`ElecPop2020` moved on 3.2% of rows, and re-solving on the rebuilt spine gave
**+50.8709%, 34,153 switches** against the published **+49.9231%, 34,461**.

The cause is the base-year gate. The published calibration used the 2 km transformer gate
(`ElecStart = 1` on 7,476 settlements; `TransformerDist` unchanged), the procedure OnSSET applies when
a transformer layer is supplied. The `s04` in the repository at the time ran a transformer-or-MV gate,
implemented by overwriting `TransformerDist` with `min(TransformerDist, CurrentMVLineDist)`: that
overwrite changes exactly 247,676 rows of the stage-2 spine, and the gate admits 1,186 further lit
settlements (8,662). The calibration file for that gate is on disk beside the published one
(`zambia_grid3_calib_distgate_txORmv_REJECTED.csv`, 8,662 settlements); the published file is
byte-identical to `zambia_grid3_calib_distgate_v1.csv`, the transformer-gate run. `s04` now runs the
transformer gate, and its re-run reproduces the published `ElecStart` and `ElecPopCalib` on every
settlement (`s21 --self-test`). The transformer-or-MV gate is kept as `run_variant(mv_or_gate=True)`
and solved as a sensitivity by `s21`; the +50.87% / 34,153 above is that sensitivity.

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
(`OAT_SWITCH_TOL = 0`). The LHS validation block rebuilds the table per arm as well, and solves each
sample at its sampled `N_mid` rather than the nearest multiple of ten (both changed 2026-09-02; the
re-solved values are in `2026-09-02_lhs_fullspine_validation.csv`).

**Cost.** Rebuilding the table adds roughly two minutes per arm, so the OAT block runs in about 35
minutes rather than 19.

**Re-run completed, 2026-08-16**, after the index-alignment fix of §7. The central variant reproduced
`s06` to six decimal places and **exactly 34,461** switches — the switch-count gate passed with zero
residual. *Updated 2026-08-23: the values below are read from
`results/summary/2026-08_final_oat_grid_costs.csv`, the canonical run. An earlier version of this
table carried values from the intermediate `2026-08-16_grid3fix` run, which differ by about 0.24 pp
on ΔLCOE% (see §7).*

| variant | grid_cap_cost | grid_gen_cost | ΔLCOE% | switches |
|---|---|---|---|---|
| central | 1441.10 | 0.013 | 49.923139 | 34,461 |
| cap−30pct | 1008.77 | 0.013 | 49.923139 | 34,461 |
| cap+30pct | 1873.43 | 0.013 | 49.923139 | 34,461 |
| gen−drought | 1441.10 | 0.050 | 45.649720 | 35,092 |

gen−drought against central: −4.27 pp on ΔLCOE% and +1.83% on switches.

The two capacity-cost rows are identical to central to six decimal places, and necessarily so: OnSSET
accumulates `grid_capacity_investment` into the reported investment total but not into the discounted
cost stream from which the LCOE is formed (`onsset.py`, `get_lcoe`), so that parameter cannot move
either the levelised cost or the allocation made on it. The generation-cost variant, which reaches the
LCOE through the fuel term, is the informative grid-side test. The paper states this in §3.5 and
Supplementary S4.
