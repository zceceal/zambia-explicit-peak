# Data sources

None of the input data is stored in this repository. It totals roughly 17 GB, and every dataset
carries its own licence. This file lists what is needed, where it comes from, and what the terms are.

## Required inputs

| Dataset | Used for | Source | Licence |
|---|---|---|---|
| GRID3 Zambia settlement extents v3.0 | The settlement dataset (stage 01) | CIESIN, Columbia University (2024), doi:10.7916/0pet-p051 | **CC BY-SA 4.0 — share-alike** |
| WorldPop population, 100 m | Population per settlement (stages 01–02) | worldpop.org | CC BY 4.0 |
| ZESCO MV distribution lines | Grid distances (stage 03) | World Bank Group (2022), *Zambia — Electrical Lines*, ENERGYDATA.INFO | CC BY 4.0 |
| NEP planned MV extensions | Planned-grid distances (stage 03) | Rural Electrification Authority | terms not published with the layer — see note below |
| Facebook/Meta MV predictive grid | Additional MV-line distance signal (stage 03) | Meta Data for Good (Gershenson, Rohrer, Lerner) (2019), via energydata.info / HDX | CC BY 4.0 |
| MV / MVLV transformers, substations | Base-year electrification gate (stage 04) | World Bank / EnergyData.info | terms not published with the layer — see note below |
| Transmission network | Grid distances (stage 03) | World Bank | terms not published with the layer — see note below |
| Global Solar Atlas GHI | Solar resource (stage 03) | globalsolaratlas.info | CC BY 4.0 |
| Global Wind Atlas 3.0, 250 m | Wind resource (stage 03) | DTU / World Bank ESMAP, globalwindatlas.info — confirmed against the raster's own 0.0025° pixel grid | CC BY 4.0 |
| EOG VIIRS annual composite, 15 arc-sec | Night-lights, base-year electrification proxy (stages 03–04) | Elvidge et al. (2021), Colorado School of Mines, Earth Observation Group — confirmed against the raster's own 0.0041666667° pixel grid | CC BY 4.0 (EOG products licence, eogdata.mines.edu/files/EOG_products_CC_License.pdf, names VIIRS nighttime lights explicitly) |
| Global Power Plant Database (hydro, Zambia) | Distance to hydropower sites (stage 03) | Global Energy Observatory, Google, KTH, Enipedia and WRI (2021), v1.3.0, datasets.wri.org | CC BY 4.0 |
| CIAT-CSI SRTM (hole-filled) | Elevation and slope (stage 03) | Jarvis, Reuter, Nelson & Guevara (2008), CIAT, srtm.csi.cgiar.org, V4.1 | **CIAT custom terms — citation required; commercial or non-free redistribution needs CIAT's permission** |
| OpenStreetMap roads (Zambia extract) | Road network / distance (stage 03) | OpenStreetMap contributors, via Geofabrik (download.geofabrik.de); extract obtained 2026-06-16 | ODbL 1.0 — share-alike |
| Global accessibility-to-cities map, 30 arc-sec | Travel time to market (stage 03) | Weiss et al. (2018), *Nature* 553:333–336, doi:10.1038/nature25181 (Malaria Atlas Project / Oxford) — confirmed against the raster's own 0.0083333° (30 arc-sec) pixel grid | licence not yet confirmed — see note below |
| renewables.ninja hourly solar | PV-hybrid mini-grid lookup tables | renewables.ninja (MERRA-2, 5 points, 2025) | **CC BY-NC 4.0 — non-commercial only** |
| UN World Population Prospects 2024 | Population projections to 2035 and 2050 | population.un.org | CC BY 3.0 IGO |
| ZamStats 2022 Census | Household sizes (urban 4.6, rural 5.0) | Zambia Statistics Agency | official publication |
| NEAS 2023 | Base-year access targets (34% / 70% / 7.6%) | Ministry of Energy | official publication |
| Integrated Resource Plan | Scenario context, connection programme | Ministry of Energy | official publication |
| ERB pump-price bulletin | Diesel price | Energy Regulation Board | official publication |

Two clauses bind redistribution. The **renewables.ninja profiles are CC BY-NC**: anything derived from
them, including the PV-hybrid lookup tables, inherits the non-commercial restriction. The **GRID3
settlement extents are CC BY-SA 4.0**: the settlement dataset and anything derived from it carries a
share-alike obligation. Neither dataset is redistributed here, and no derived product of either is
committed to this repository.

Three layers above are marked *terms not published with the layer*: the NEP planned MV extensions, the
transformer/substation records and the transmission network were obtained without an accompanying
licence statement. They are used here for academic analysis and are not redistributed. Anyone reusing
them should confirm terms with the publisher first.

The travel-time layer is a similar case: publisher, product and vintage are identified (the paper's own
citation, confirmed against the raster's 30 arc-second pixel grid), but its redistribution terms have
not yet been checked against the Malaria Atlas Project's current data policy. Not redistributed here
either way; confirm directly with the publisher before reuse.

The hydro layer lists five existing grid-scale stations (Kafue Gorge 990 MW, Kariba 930 MW,
Itezhi-Tezhi 120 MW, Victoria Falls 108 MW, Lusiwasi 12 MW), not a mini-hydro potential assessment —
there is no sixth site waiting to be found in it. This is why `docs/01_pipeline.md` and the paper
report mini-grid hydro as near-absent from the allocation: only settlements within reach of one of
these five named stations are ever costed on that technology.

`admin/geoboundaries/geoBoundaries-ZMB-ADM1.geojson` is not a Required input, even though `s01`, `s02`
and `s05` all read it. Traced its use: it is spatially joined onto each settlement to populate the
`Admin_1` column (province name), which `s05` also uses to relabel 135 border-sliver settlements to
their nearest province. Downstream, `onsset.py`'s own `conditioning()` step only null-checks `Admin_1`
and prints a warning if it finds one — no cost or allocation formula anywhere in the pipeline reads it.
It is a labelling/QA field, not a model input, so it carries no publisher, version or licence row here;
its version and licence remain unconfirmed regardless.

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
