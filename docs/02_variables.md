# Variables

Every number the model uses, where it comes from, and whether it is swept.

All values are **identical across R0 and R1** unless the last column says otherwise. That is the point
of the design: only the peak representation differs, so anything shared cancels out of the comparison.

## 1. The peak sub-model (the study's intervention — R1 only)

| Variable | Value | Meaning | Source |
|---|---|---|---|
| `p_1` | 3.98 (±0.46) | Peak-to-energy ratio of a single household | Lorenzoni et al. 2020, Table 2, "Peak" archetype |
| `p_inf` | 1.45 (±0.26) | Ratio approached by a very large settlement | Lorenzoni et al. 2020, Table 2, "Flat" archetype |
| `p_step` | 2.43 (±0.23) | Intermediate anchor used to fix `beta` | Lorenzoni et al. 2020, Table 2, "Step-peak" archetype |
| `n_mid` | **20** | Connection count at which a load resembles the Step-peak archetype | **Assumed, not measured.** Swept {10, 20, 50} |
| `beta` | 0.317 central | Curve steepness | Derived, not set: `0.9484 / ln(n_mid)`. Sweep gives {0.412, 0.317, 0.242} |

`n_mid` is the only free quantity in the model. Everything else in this table is measured.

## 2. Costs and finance

| Variable | Value | Unit | Source |
|---|---|---|---|
| Discount rate (all technologies) | 8.0 | % real | OnSSET/CCG convention. Sensitivities: 10% flat (Mapulanga 2024); Egli 2023 technology-differentiated Zambia rates. Zambia's IRP states no rate |
| Grid capacity investment cost | 1,441.1 | USD/kW | Egli et al. 2023, Table S8 (Zambia) |
| Grid generation cost | 0.013 | USD/kWh | Egli et al. 2023, Table S8 (Zambia) |
| Grid T&D losses | 15 | % | Egli et al. 2023, Table S8 (Zambia) |
| Stand-alone PV capital cost | 4,470–9,620 | USD/kW, size-banded | OnSSET/GEP default set |
| Battery storage | 300 | USD/kWh | NREL ATB 2025. Swept [247, 300, 334] |
| Mini-grid PV capital cost | 1,400 | USD/kW | OnSSET/GEP default |
| Diesel price | 1.90 | USD/litre | Zambia ERB, May 2026. Swept ±20% |
| Technology lives | SA-PV 5 yr, mini-grid 20 yr | years | OnSSET/GEP default |

**Important:** the off-grid cost parameters are **byte-identical to the official OnSSET/GEP defaults**.
They are not tuned. They are the same values the World Bank's Global Electrification Platform and the
published Zambia study (Imasiku 2025) use, which is what makes those benchmarks comparable. They
cannot be "corrected" to better values — they *are* the field's reference set.

## 3. Demand

| Variable | Value | Source |
|---|---|---|
| Urban demand tier | MTF Tier 5 | Imasiku 2025 (urban Zambia) |
| Rural demand tier | MTF Tier 3 | Imasiku 2025. Sensitivity: Tier 2 |
| kWh/HH/yr per tier | locked in OnSSET | Bhatia & Angelou 2015 (ESMAP Multi-Tier Framework) |
| Household size, urban | 4.6 | ZamStats 2022 Census |
| Household size, rural | 5.0 | ZamStats 2022 Census |
| Per-household demand growth | none | Held flat over the horizon; total demand rises only with population |

Household size is used **both** to compute demand and to derive `N` in the peak sub-model, from the
same source, so the two are consistent.

## 4. Grid and scenario

| Variable | Value | Source |
|---|---|---|
| Maximum grid-extension distance | 10 km | OnSSET/GEP convention. Swept [5, 20] km |
| Reliability target | 0.963 | OnSSET default; cost of non-served energy = 0 |
| Annual grid build rate | unconstrained | See `03_assumptions.md` |
| Start year | 2020 | — |
| Analysis years | 2030, 2035 | **Use the 2030 columns.** See `01_pipeline.md` |
| Electrification target | 100% by end year | Universal-access scenario |
| 2050 variant | single-year endpoint, `time_step = 30` | `scripts/s12_run_2050_horizon.py` |

## 5. Spatial inputs

| Layer | Source |
|---|---|
| Settlement spine (270,526 settlements) | GRID3 |
| Transformers, MV/HV lines | World Bank / EnergyData |
| Base-year electrification target | NEAS 2023 — 34% national, 70% urban, 7.6% rural |
| Solar resource | Global Solar Atlas |
| PV-hybrid hourly profiles | renewables.ninja (MERRA-2, 5 points, 2025) |
| Population projection | UN WPP 2024 |

The base year is calibrated with a **2 km transformer-distance gate** — the standard criterion. An
earlier calibration used night-lights only; it was rejected because it over-counted urban access and
under-counted rural. Documented in the paper's supplementary material.
