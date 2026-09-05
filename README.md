# Explicit peak demand in least-cost electrification modelling — Zambia

A controlled OnSSET experiment testing whether representing **peak demand per settlement**, rather
than through one national load factor, changes the least-cost electrification plan for Zambia.

**Headline: doing so raises the modelled lifetime cost of universal access by +45.4%, and changes
the least-cost technology for 33,665 settlements (12.4%) — see [Headline results](#headline-results)
below, or `results/summary/` for the committed numbers behind the reported figures. See
[Reproducibility: what this clone gives you](#reproducibility-what-this-clone-gives-you) for exactly
what that does and does not include.**

Model and code behind the MSc research paper *Explicit peak demand representation in least-cost
electrification modelling: evidence from Zambia* (Imperial College London, 2026).

---

## Reproducibility: what this clone gives you

The published state is the tag **`paper-2026-09-05`**, which is what the paper's Data availability
statement cites, what `main` points at, and the only tag this repository carries.

Three tiers.

**1. From the clone alone, no input data required.** Every script and its docstring; the OnSSET patch
in `patches/`, verified against upstream `c154ece`; the acceptance and regression tests in `test/`; and
`results/summary/` — the committed, machine-readable CSVs behind the numbers this README and the paper
report. (Throughout, `sNN` is the pipeline script `scripts/sNN_*.py`; `docs/01_pipeline.md` lists all
of them with their inputs and outputs.) In particular,
`results/summary/2026-08_final_lcoe_paper_numbers.csv` (from `s14`) carries every
figure in the paper's Table 2 and §3.1-3.2, `2026-09-02_variant_summaries.csv` (from `s23`) the
Tier-2, 2050-horizon, anchor-fitted, capital-cost-schedule, replacement-schedule and single-household
variants, and `2026-08_final_provincial_rho.csv` (from `s20`) §4.4's provincial comparison. This is
enough to read the code, run the tests, and check every number the paper reports. The per-settlement
solves behind them are not committed, for size; regenerating them requires the input data.

**2. With the input data, obtained separately, the full pipeline solves.** `docs/04_data_sources.md`
lists every source, its vintage and its licence. The data are not redistributed here because their
licences do not permit it — GRID3 is CC BY-SA 4.0 (share-alike), the renewables.ninja profiles are
CC BY-NC (non-commercial), and several others carry their own terms. With the data in place as
`docs/04_data_sources.md` describes, `s01` through `s25` run end to end. §8 of `REPRODUCING.md`
records which stages reproduce byte-for-byte from the published spine. The per-settlement outputs
behind the two allocation/switching maps (`fig_results_switching_map.pdf`,
`fig_results_r0_r1_allocation_map.pdf`; gitignored) are not committed either, for size rather
than licence reasons, and are available from the author on request (`results/README.md`).

**3. The published settlement spine.** Rebuilding it from raw data with the current `s01`-`s05`
reproduces every column that feeds the R0/R1 solve (`REPRODUCING.md` §8). It is calibrated on the
2 km transformer gate; the wider transformer-or-MV gate is the sensitivity in `s21`.

---

## The question, in one paragraph

Geospatial electrification models decide, for every settlement in a country, whether extending the
grid, building a mini-grid, or installing stand-alone solar is cheapest. To do that they need each
settlement's **peak** power, but the standard workflow specifies only **annual energy** and converts
it to a peak with a single national factor — the same factor for a ten-household hamlet and a
three-thousand-household town. That is physically wrong: in a small settlement everyone cooks and
lights at once, while in a large one demands average out. This repository replaces that single factor
with a peak computed per settlement from its connection count, holds everything else identical, and
measures what changes.

## The experiment

| Arm | Name | Peak demand representation |
|-----|------|----------------------------|
| **R0** | Energy-only baseline | One uniform load factor for every settlement (standard practice) |
| **R1** | Explicit peak | Peak-to-energy ratio computed per settlement from its connection count |

Same 270,526-settlement spine, same costs, same resource data, same solver, same random seed. The
demand pre-processor is the only difference, which is what makes the comparison controlled.

## Headline results

Run of 2026-09-05, with N evaluated at the analysis-year (2030) population throughout (see
[`docs/01_pipeline.md`](docs/01_pipeline.md)).
Every number below is drawn from `results/summary/2026-08_final_*.csv`, committed to this repository.

| Result | Value |
|---|---|
| Change in lifetime cost of universal access | **+45.4%** (+30.0% to +66.1% across the `N_mid` sweep — `N_mid` is the sub-model's one assumed parameter, swept over {10, 20, 50}; see [`docs/02_variables.md`](docs/02_variables.md) §1) |
| Change in upfront capital | **+41.2%**; new capacity +1.6% |
| Settlements changing least-cost technology | **33,665** (12.4%); every one stand-alone solar → grid |
| Same comparison at lower (Tier-2) demand | −3.7% to +7.2% — a boundary condition, not a confirmation |
| Same comparison at projected 2050 population | Cost penalty falls to **+34.9%**; reallocation falls ~4.5% |

Two qualifications belong with the headline. About 24 of the 45.4 percentage points come from
settlements crossing a step in OnSSET's stand-alone capital-cost schedule at 1 kW per household,
rather than from the smooth capacity response; `scripts/s15_run_capex_curve_sensitivity.py` measures
that split. And the effect reaches levelised cost through the stand-alone PV channel only — holding
the R0 allocation throughout (no settlement switches) and freezing stand-alone costs at their R0
values leaves −0.5% — because OnSSET keeps grid capacity cost out of the
levelised cost and sizes mini-grid generation from a fixed load archetype. The measured effect is
therefore a lower bound on a model with explicit peaks in all three supply options.

## Installation

```bash
git clone https://github.com/zceceal/zambia-explicit-peak.git
cd zambia-explicit-peak
python3.13 -m venv .venv && source .venv/bin/activate   # Python 3.13 specifically -- see REPRODUCING.md §1 for why
pip install -r requirements.txt
```

or with conda:

```bash
conda env create -f environment.yml && conda activate zambia-peak
```

The allocation engine is OnSSET at upstream commit `c154ece` with the patch in
[`patches/`](patches/README.md) applied. **The results do not reproduce without it.** It makes six
changes, set out in [`patches/README.md`](patches/README.md); the paper's Methodology (§2.2.1)
discloses three of them.

The input data is **not** in this repository; it is held under third-party licences. See
[`docs/04_data_sources.md`](docs/04_data_sources.md) for every source and the expected layout.

Full step-by-step instructions, pinned versions and expected outputs are in
[`REPRODUCING.md`](REPRODUCING.md).

## Repository layout

```
config/                  config.yaml — every contested value, with its source
docs/                    pipeline, variables, assumptions, data sources
patches/                 the changes to the OnSSET core, and why
peak_preprocessor/       the study's contribution: the peak-to-energy sub-model
scripts/                 the pipeline, in run order (s01 … s13), the reporting and
                         robustness stages s14 … s24, s25 (collects the summary CSVs
                         into results/summary/, always the last step), and the three
                         acceptance checks (check_index_alignment.py,
                         check_spine_integrity.py, check_mv_sources.py)
test/                    unit tests for the sub-model; OnSSET install check;
                         index-alignment regression test
resources/               small reference inputs (specs templates)
results/                 summary outputs (committed); per-settlement CSVs gitignored
```

## Running the pipeline

Scripts run in numeric order. Each writes files the next one reads. `PYTHONPATH` must point at the
repository root, or `peak_preprocessor` is not importable.

```bash
export PYTHONPATH="$(pwd)"
python scripts/s01_build_spine_clusters.py   # … through to …
python scripts/s13_generate_figures.py
python scripts/s25_collect_summaries.py      # always the last step
```

Full description of every stage: [`docs/01_pipeline.md`](docs/01_pipeline.md).

The whole intervention is one equation, in `peak_preprocessor/pe_diversity.py` (~150 lines):

```
P/E(N) = P_inf + (P_1 - P_inf) * N ** (-beta)
```

`N` is `N_hh = max(1, Pop2030 / household_size)`. The anchors, `beta` and `N_mid` are set out in
[`docs/02_variables.md`](docs/02_variables.md) §1; how `N_hh` is built and checked, in
[`docs/01_pipeline.md`](docs/01_pipeline.md).

## Tests

With the input data and the patched engine in place, all 11 checks pass. On a clean checkout one of
them fails by design: `test_index_alignment.py`'s third check,
`test_stand_alone_capacity_closed_form`, needs `data/onsset_outputs/2026-08_final_lcoe_R0.csv` from a
completed `s06` run, and it fails rather than skips so that a reviewer never sees a green suite for a
check that never executed. Its own assertion message says so. (`test_condition_df_resets_index`
skips, rather than fails, when OnSSET is not importable.)

```bash
pytest test/                                                      # 11 checks
```

`conftest.py` puts `peak_preprocessor` on `sys.path` and excludes
`test/test_onsset_install.py`, which is a standalone script rather than a pytest module. Each
file also runs on its own:

```bash
PYTHONPATH=peak_preprocessor python test/test_pe_diversity.py     # 8 tests on the sub-model
python test/test_onsset_install.py                                # end-to-end OnSSET install check
python test/test_index_alignment.py                               # regression test for the 2026-08-16 defect
```

After any run of `s06`, before trusting anything downstream, run the two acceptance checks described
in [`docs/01_pipeline.md`](docs/01_pipeline.md):

```bash
python scripts/check_index_alignment.py data/onsset_outputs/<run>_R0.csv
python scripts/check_spine_integrity.py
```

## Reading order for a reviewer

1. This file.
2. [`docs/01_pipeline.md`](docs/01_pipeline.md) — what runs, in what order.
3. [`docs/02_variables.md`](docs/02_variables.md) — every number, with its source.
4. [`docs/03_assumptions.md`](docs/03_assumptions.md) — what the model takes on trust, and how each is tested.
5. `peak_preprocessor/pe_diversity.py` — the intervention itself.

## Licence

Code MIT (see `LICENSE`). **Input data is not MIT** and is not redistributed here — the
renewables.ninja profiles in particular are CC BY-NC (non-commercial). Check
`docs/04_data_sources.md` before reusing anything derived from the inputs.
