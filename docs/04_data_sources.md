# Data sources

None of the input data is stored in this repository. It totals roughly 17 GB, and every dataset
carries its own licence. This file lists what is needed, where it comes from, and what the terms are.

## Required inputs

| Dataset | Used for | Source | Licence |
|---|---|---|---|
| GRID3 Zambia settlement extents | The settlement spine (stage 01) | GRID3 / WorldPop | CC BY 4.0 |
| WorldPop population, 100 m | Population per settlement (stages 01–02) | worldpop.org | CC BY 4.0 |
| ZESCO MV distribution lines | Grid distances (stage 03) | World Bank / EnergyData.info | check layer terms |
| NEP planned MV extensions | Planned-grid distances (stage 03) | Rural Electrification Authority | check terms |
| MV / MVLV transformers, substations | Base-year electrification gate (stage 04) | World Bank / EnergyData.info | check layer terms |
| Transmission network | Grid distances (stage 03) | World Bank | check terms |
| Global Solar Atlas GHI | Solar resource (stage 03) | globalsolaratlas.info | CC BY 4.0 |
| renewables.ninja hourly solar | PV-hybrid mini-grid lookup tables | renewables.ninja (MERRA-2, 5 points, 2025) | **CC BY-NC 4.0 — non-commercial only** |
| UN World Population Prospects 2024 | Population projections to 2035 and 2050 | population.un.org | CC BY 3.0 IGO |
| ZamStats 2022 Census | Household sizes (urban 4.6, rural 5.0) | Zambia Statistics Agency | official publication |
| NEAS 2023 | Base-year access targets (34% / 68% / 7.4%) | Ministry of Energy | official publication |
| Integrated Resource Plan | Scenario context, connection programme | Ministry of Energy | official publication |
| ERB pump-price bulletin | Diesel price | Energy Regulation Board | official publication |

The **renewables.ninja non-commercial clause is the binding constraint** on redistribution. Anything
derived from those profiles — including the PV-hybrid lookup tables — inherits it. This matters if the
repository is ever made public alongside derived data.

## Expected local layout

Scripts expect a `data/` directory at the repository root:

```
data/
  raw/zambia/        downloaded source datasets, unmodified
  processed/         the settlement spine at each build stage
  onsset_inputs/     the OnSSET specs workbook
  onsset_outputs/    model results
```

`data/` is gitignored. In the thesis working tree the same directory is named `5. data/`; paths in
this repository have been normalised to `data/` so the repo is internally consistent. The working
copy in the thesis tree is unchanged.

## Data that does not exist

No public multi-site metered Zambian mini-grid load dataset exists. This was searched for
specifically, because it is exactly what would let `N_mid` be measured rather than assumed. The one
substantial commercial dataset is proprietary.

This is not a gap left by omission — it is the reason the peak sub-model is calibrated on transferred
archetypes and then externally validated against three independently measured systems, rather than
fitted directly to Zambian data. It is stated in the paper as the primary future-work item.
