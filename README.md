# Explicit peak demand in least-cost electrification modelling — Zambia

A controlled OnSSET experiment testing whether representing **peak demand per settlement**, rather
than through one national load factor, changes the least-cost electrification plan for Zambia.

**Headline: doing so raises the modelled lifetime cost of universal access by +49.9%, and changes
the least-cost technology for 34,461 settlements (12.7%) — see [Headline results](#headline-results)
below, or `results/summary/` for the committed numbers behind the reported figures, with no setup
required. See [Reproducibility: what this clone gives you](#reproducibility-what-this-clone-gives-you)
for exactly what that does and does not include.**

Model and code behind the MSc research paper *Explicit peak demand representation in least-cost
electrification modelling: evidence from Zambia* (Imperial College London, 2026).

---

## Reproducibility: what this clone gives you

Three tiers, stated as a boundary rather than left implicit.

**1. From the clone alone, no input data required.** Every script and its docstring; the OnSSET patch
in `patches/`, verified against upstream `c154ece`; the acceptance and regression tests in `test/`; and
`results/summary/` — the committed, machine-readable CSVs behind the numbers this README and the paper
report. In particular, `results/summary/2026-08_final_lcoe_paper_numbers.csv` (from `s14`) carries every
figure in the paper's Table 2 and §3.1-3.2, and `2026-08_final_provincial_rho.csv` (from `s20`) carries
§4.4's provincial comparison. This is enough to read the code, run the tests, and check any reported
number without obtaining anything else.

**2. With the input data, obtained separately, the full pipeline solves.** `docs/04_data_sources.md`
lists every source, its vintage and its licence. The data are not redistributed here because their
licences do not permit it — GRID3 is CC BY-SA 4.0 (share-alike), the renewables.ninja profiles are
CC BY-NC (non-commercial), and several others carry their own terms — not because the roughly 17 GB was
simply left out. With the data in place as `docs/04_data_sources.md` describes, `s01` through `s20` run
end to end and reproduce every committed number byte-for-byte (§8 of `REPRODUCING.md`). The
per-settlement outputs behind the two allocation/switching maps (`fig_results_switching_map.pdf`,
`fig_results_r0_r1_allocation_map.pdf`; ~11 GB, gitignored) are not committed either, for size rather
than licence reasons, and are available from the author on request.

**3. Not currently reproducible, even with the data: the published settlement spine.** It is dated four
weeks before this repository's first commit and was built by a version of the stage-3 attribute builder
that no longer exists on disk. Rebuilding it from raw data with the current `s01`-`s05` reproduces every
column that feeds the R0/R1 solve exactly, except one (`TransformerDist`), and moves the central result
by 0.95 percentage points — still inside the reported `N_mid` sweep band, with every qualitative
conclusion unchanged. `REPRODUCING.md` §8 has the full account, including what was ruled out as the
cause. Every result reported anywhere in this repository is built on the published spine, not a
rebuilt one.

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

Run of 2026-08-16, the first with the index-alignment defect corrected (see
[`REPRODUCING.md`](REPRODUCING.md) §7). **Earlier figures from this repository are superseded.**
Every number below is drawn from `results/summary/2026-08_final_*.csv`, committed to this repository
— readable directly, with no data download and no engine to build, for anyone who wants to check a
number without reproducing the full run.

| Result | Value |
|---|---|
| Change in lifetime cost of universal access | **+49.9%** (+34.1% to +70.6% across the `N_mid` sweep) |
| Change in upfront capital | **+45.6%**; new capacity +2.9% |
| Settlements changing least-cost technology | **34,461** (12.7%); every one stand-alone solar → grid |
| Same comparison at lower (Tier-2) demand | −2.2% to +8.4% — a boundary condition, not a confirmation |
| Same comparison at projected 2050 population | Cost penalty falls to **+34.9%**; reallocation falls ~7% |

Two qualifications belong with the headline. About 26 of the 49.9 percentage points come from
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
[`patches/`](patches/README.md) applied. **The results do not reproduce without it.** It does six
things: resets the DataFrame index after `condition_df()` sorts, so that peak load and capacity factor
are no longer mispaired across settlements; adds a runtime guard that raises if that invariant is ever
broken again; corrects a medium-voltage line-count formula that over-counted feeders against a
transformer rating instead of the line's own rating; makes stand-alone PV read the same per-settlement
peak field every other technology already read; casts a capital-cost accumulator to float so it
stops truncating non-integer costs; and adds an off-by-default switch to a full reinvestment schedule,
used only by the labelled robustness variant in `scripts/s16_run_corrected_conventions.py`. The
unpatched code *suppressed* the effect this study measures on both counts, so the patch does not
create the result. See [`patches/README.md`](patches/README.md) for all six and the paper's
Methodology (§2.2.1) for the three — the index-alignment fix, the medium-voltage line-count
correction (371 settlements, 0.14%, 0.24 pp), and the peak-symmetry fix — that it discloses.

The input data is **not** in this repository: roughly 17 GB under third-party licences. See
[`docs/04_data_sources.md`](docs/04_data_sources.md) for every source and the expected layout.

Full step-by-step instructions, pinned versions and expected outputs are in
[`REPRODUCING.md`](REPRODUCING.md).

## Repository layout

```
config/                  config.yaml — every contested value, with its source
docs/                    pipeline, variables, assumptions, data sources
patches/                 the changes to the OnSSET core, and why
peak_preprocessor/       the study's contribution: the peak-to-energy sub-model
scripts/                 the pipeline, in run order (s01 … s13), the standalone
                         analyses s14 … s20, and the two acceptance checks
                         (check_index_alignment.py, check_spine_integrity.py)
test/                    unit tests for the sub-model; OnSSET install check;
                         index-alignment regression test
resources/               small reference inputs (specs templates)
results/                 summary outputs (committed); per-settlement CSVs gitignored
```

## Running the pipeline

Scripts run in numeric order. Each writes files the next one reads.

```bash
python scripts/s01_build_spine_clusters.py   # … through to …
python scripts/s13_generate_figures.py
```

Full description of every stage: [`docs/01_pipeline.md`](docs/01_pipeline.md).

The whole intervention is one equation, in `peak_preprocessor/pe_diversity.py` (~150 lines):

```
P/E(N) = P_inf + (P_1 - P_inf) * N ** (-beta)
```

`P_1 = 3.98`, `P_inf = 1.45` and the calibration anchor `P_step = 2.43` are all **measured** values
(Lorenzoni et al. 2020, 61 metered mini-grids). `beta` is derived, not chosen. The one assumed
quantity, `N_mid`, is swept over {10, 20, 50} and every result is reported as a band.

## Tests

```bash
PYTHONPATH=peak_preprocessor python test/test_pe_diversity.py     # 8 tests on the sub-model
python test/test_onsset_install.py                                # end-to-end OnSSET install check
python test/test_index_alignment.py                               # regression test for the 2026-08-16 defect
```

`test_index_alignment.py`'s third check, `test_stand_alone_capacity_closed_form`, needs
`data/onsset_outputs/2026-08_final_lcoe_R0.csv` — a completed `s06` run (see "Running the pipeline"
above). Run before that, it FAILS by design, not skips: a reviewer on a clean checkout must not see a
green suite for a check that never executed. Its own assertion message says so.

After any run of `s06`, before trusting anything downstream:

```bash
python scripts/check_index_alignment.py data/onsset_outputs/<run>_R0.csv   # must report ~100%
python scripts/check_spine_integrity.py                                    # 22 checks on the spine
```

## Reading order for a reviewer

1. This file.
2. [`docs/03_assumptions.md`](docs/03_assumptions.md) — what the model takes on trust, and how each is tested.
3. [`docs/01_pipeline.md`](docs/01_pipeline.md) — what runs, in what order.
4. [`docs/02_variables.md`](docs/02_variables.md) — every number, with its source.
5. `peak_preprocessor/pe_diversity.py` — the intervention itself.

## Licence

Code MIT (see `LICENSE`). **Input data is not MIT** and is not redistributed here — the
renewables.ninja profiles in particular are CC BY-NC (non-commercial). Check
`docs/04_data_sources.md` before reusing anything derived from the inputs.
