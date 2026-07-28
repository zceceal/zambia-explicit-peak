# Reproducing the published results

Everything needed to re-run the experiment, in order. The published figures come from the
`grid3_central` configuration: rural Tier 3, `N_mid = 20`, seed 42.

## 1. Environment

Python 3.13.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 2. OnSSET, with the patch

The allocation engine is OnSSET at upstream commit `c154ece`, with the two-line patch in `patches/`
applied. **The results do not reproduce without it** — see `patches/README.md` for what it changes and
why.

```bash
git clone https://github.com/onsset/OnSSET.git
cd OnSSET && git checkout c154ece
git apply ../patches/onsset-explicit-peak.patch
pip install -e . && cd ..
```

## 3. Data

Not distributed with this repository — roughly 17 GB, under third-party licences. `docs/04_data_sources.md`
lists every source, its licence, and the directory layout the scripts expect under `data/`.

## 4. Run

Scripts run in numeric order; each writes what the next reads.

```bash
python scripts/s00_validate_inputs.py          # pre-run gate; stop if it fails
python scripts/s01_build_spine_clusters.py
python scripts/s02_build_spine_dispersed.py
python scripts/s03_build_spine_attributes.py
python scripts/s04_calibrate_base_year.py
python scripts/s05_compute_peak_ratios.py      # writes PE_ratio for N_mid 10, 20, 50
python scripts/s06_run_arms.py                 # the headline R0 vs R1 comparison
```

Robustness and reporting stages, in any order after `s06`:

```bash
python scripts/s07_run_demand_sensitivity.py   # rural Tier 2
python scripts/s08_run_global_sensitivity.py   # Morris screen + Latin-hypercube propagation
python scripts/s09_run_oat_checks.py           # grid-side one-at-a-time checks
python scripts/s10_run_sizing_decomposition.py # the f-band on existing outputs, no re-solve
python scripts/s11_run_drought_oat.py          # drought-price generation cost
python scripts/s12_run_2050_horizon.py         # 2050 endpoint (helpers s12a, s12b, s12c)
python scripts/s13_generate_figures.py
```

## 5. What you should get

From `s06`, on the 2030 columns, at rural Tier 3 and `N_mid = 20`:

| Quantity | R0 (energy-only) | R1 (explicit peak) | Change |
|---|---|---|---|
| Energy-weighted LCOE | 0.555 USD/kWh | 0.760 USD/kWh | **+36.9%** |
| Aggregate investment to 2030 | USD 75.5 bn | USD 68.1 bn | −9.8% |
| New capacity to 2030 | 6,540 MW | 5,889 MW | −10.0% |
| Settlements changing technology | — | — | 18,224 (6.7%) |

Across the `N_mid` sweep the lifetime-cost change is +34.6% / +36.9% / +38.8% for `N_mid` 10 / 20 / 50,
with 16,999 / 17,787 / 18,260 settlements moving from stand-alone solar to grid.

From `s12`, at the projected 2050 population: +23.9% central, band +22.1% to +26.1%, with 16,901
settlements changing technology.

## 6. Determinism

- All random draws are seeded (`seed = 42`). The PV-hybrid optimiser varied by 0.2% between unseeded
  runs; seeding removes it.
- Both arms are built from one in-memory spine with only the peak column overwritten, and a pre-run
  assertion fails the run if any shared column differs. The two arms are byte-identical in every
  column except the peak.
- Read costs on the **2030** columns. The 2035 and 2050 incremental columns carry almost no energy for
  settlements already connected and produce meaningless levelised costs; `docs/01_pipeline.md`
  explains this.
