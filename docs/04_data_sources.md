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

Scripts resolve every path relative to the repository root, so the tree below is exact. Paths are
taken from the code, not from memory; a missing file fails at the stage that needs it.

```
data/
  raw/zambia/
    grid3_settlements/grid3_zmb_settlement_extents_v3_0/
        GRID3_ZMB_settlement_extents_v3_0.gpkg      settlement polygons          s01, s02
    population/worldpop/
        zmb_ppp_2020_UNadj_constrained.tif          population raster            s01, s02
    resource/ghi/GHI.tif                            solar resource               s03
    resource/wind/ZMB_wind-speed_100m.tif           wind speed                   s03
    resource/nightlights/
        zmb_viirs_ntl_2020_avg_masked.tif           night lights                 s03, s04
    resource/hydro/zambia_hydro_plants.csv          hydro sites                  s03
    terrain/dem/unzipped/                           SRTM tiles (merged by s03)   s03
    transport/travel_time/
        zambia_travel_time_to_cities.tif            travel time surface          s03
    transport/roads/zambia-latest.osm.pbf           road network                 s03
    admin/geoboundaries/
        geoBoundaries-ZMB-ADM1.geojson              admin-1 boundaries           s03
    grid/
      mv_distribution_2023/distribution_medium_voltage_overhead_line_network/
        Distribution_Medium_Voltage_Overhead_Line_Network.shp   ZESCO MV lines   s03
      nep_mv_extension_2023/mv-lines-extensions.geojson         NEP planned MV   s03
      mv_predictive_fb/electrical_grid_zambia_15.csv            predictive MV    s03
      transmission_network_wb/zambia-electricity-transmission-network/
        Zambia Electricity Transmission Network.shp             HV network       s06+
      transformers_substations/                                 transformers     s03, s04
    renewables_hourly/solar/solar_lusaka.csv        hourly GHI + temperature     s06+
    renewables_hourly/wind/wind_lusaka.csv          hourly wind speed            s06+

  onsset_inputs/
    specs_zambia.xlsx                               copy from resources/         s04
  onsset_repo/                                      patched OnSSET clone         test/
  processed/                                        written by s01-s05
  onsset_outputs/                                   written by s06-s12
```

`figures/` and `notes/` are created at the repository root by s13 and by s01/s02 respectively. All
four generated directories are gitignored.

Two of these are derived rather than downloaded: `terrain/dem/unzipped/` holds the raw SRTM tiles,
which s03 merges into `data/processed/zmb_srtm_merged.tif` and `zmb_slope_degrees.tif`; and
`transformers_substations/` holds the MV, MVLV and substation shapefiles that s03 combines into a
single transformer-distance column.

## Data that does not exist

No public multi-site metered Zambian mini-grid load dataset exists. This was searched for
specifically, because it is exactly what would let `N_mid` be measured rather than assumed. The one
substantial commercial dataset is proprietary.

This is not a gap left by omission — it is the reason the peak sub-model is calibrated on transferred
archetypes and then externally validated against three independently measured systems, rather than
fitted directly to Zambian data. It is stated in the paper as the primary future-work item.
