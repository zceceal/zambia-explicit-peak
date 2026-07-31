# Explicit peak demand in least-cost electrification modelling — Zambia

A controlled OnSSET experiment testing whether representing **peak demand per settlement**, rather
than through one national load factor, changes the least-cost electrification plan for Zambia.

Model and code behind the MSc research paper *Explicit peak demand representation in least-cost
electrification modelling: evidence from Zambia* (Imperial College London, 2026).

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

| Result | Value |
|---|---|
| Change in lifetime cost of universal access | **+36.9%** (+28.5% to +38.8% across sensitivities; +14.1% under the most conservative sizing assumption) |
| Change in upfront capital | **−9.8%** |
| Settlements changing least-cost technology | **18,224** (6.7%, exclusively rural; 97.6% stand-alone solar → grid) |
| Same comparison at lower (Tier-2) demand | Cost rise persists; reallocation largely disappears |
| Same comparison at projected 2050 population | Cost penalty falls to **+23.9%**; reallocation falls only ~7% |

Capital falls while lifetime cost rises. Both are true: grid extension is capital-light and
operating-heavy, and OnSSET optimises lifetime cost, not capital.

## Installation

```bash
git clone https://github.com/zceceal/zambia-explicit-peak.git
cd zambia-explicit-peak
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

or with conda:

```bash
conda env create -f environment.yml && conda activate zambia-peak
```

The allocation engine is OnSSET at upstream commit `c154ece` with a two-line patch applied — see
[`patches/README.md`](patches/README.md). **The results do not reproduce without it.**

The input data is **not** in this repository: roughly 17 GB under third-party licences. See
[`docs/04_data_sources.md`](docs/04_data_sources.md) for every source and the expected layout.

Full step-by-step instructions, pinned versions and expected outputs are in
[`REPRODUCING.md`](REPRODUCING.md).

## Repository layout

```
config/                  config.yaml — every contested value, with its source
docs/                    pipeline, variables, assumptions, data sources
patches/                 the two-line change to the OnSSET core, and why
peak_preprocessor/       the study's contribution: the peak-to-energy sub-model
scripts/                 the pipeline, in run order (s00 … s13)
test/                    unit tests for the sub-model; OnSSET install check
resources/               small reference inputs (specs templates)
results/                 model outputs (gitignored; summaries only)
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
