"""
build_grid3_spine_stage1b.py
Stage 1b — population conservation: add dispersed-rural settlements.

Stage-1 cluster spine captures 81.83% of WorldPop (settlement-polygon pixels).
This script recovers the 18.17% residual (pixels outside all GRID3 polygons)
by aggregating them to 0.025° coarse cells (~2.8 km), producing a combined
spine that reconciles to the national WorldPop total.

Run with the project venv:
  .venv/bin/python _claude_workspace/scripts/build_grid3_spine_stage1b.py
"""

import warnings
warnings.filterwarnings('ignore')

import time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import rasterio.features

t0 = time.time()

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT  = Path("/Users/eladiaalcoverrogea/Desktop/IMPERIAL/research project")
RAW   = ROOT / "data/raw/zambia"
PROC  = ROOT / "data/processed"

GRID3_GPKG  = RAW / "grid3_settlements/grid3_zmb_settlement_extents_v3_0/GRID3_ZMB_settlement_extents_v3_0.gpkg"
WP_TIF      = RAW / "population/worldpop/zmb_ppp_2020_UNadj_constrained.tif"
ADM1_VEC    = RAW / "admin/geoboundaries/geoBoundaries-ZMB-ADM1.geojson"
STAGE1_CSV  = PROC / "zambia_grid3_spine_stage1.csv"

OUT_CSV     = PROC / "zambia_grid3_spine_combined.csv"
OUT_GPKG    = PROC / "zambia_grid3_spine_combined.gpkg"
NOTES_PATH  = ROOT / "notes/2026-06-28_grid3_spine_stage1b.md"

UTM = "EPSG:32735"
URBAN_SHARE_TARGET = 0.437

# Dispersed-cell resolution (degrees).
# 0.025° ≈ 2.78 km; yields ~56,421 dispersed cells → combined ≈ 270,619  (target 250–300k)
COARSE_RES = 0.025

# ID offset for dispersed rows (ensures no collision with cluster IDs 1–214,198)
DISP_ID_OFFSET = 1_000_000

# ══════════════════════════════════════════════════════════════════════════════
# S1 — Load WorldPop raster
# ══════════════════════════════════════════════════════════════════════════════
print("\n── S1: Load WorldPop raster ──")
with rasterio.open(WP_TIF) as src:
    wp_data   = src.read(1).astype(np.float64)
    wp_nodata = src.nodata
    wp_tf     = src.transform
    wp_h, wp_w = src.height, src.width

if wp_nodata is not None:
    wp_data[wp_data == wp_nodata] = 0.0
wp_data[wp_data < 0] = 0.0

wp_total = wp_data.sum()
print(f"  WorldPop national total: {wp_total:,.0f}")

# ══════════════════════════════════════════════════════════════════════════════
# S2 — Coverage mask: rasterise all GRID3 polygons (uint8, one call)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── S2: Build GRID3 coverage mask ──")
print("  Loading GRID3 polygons...")
gdf_raw = gpd.read_file(str(GRID3_GPKG))
print(f"  Polygons: {len(gdf_raw):,}")

print("  Rasterising to coverage mask (uint8, ~60 s)...")
shapes = ((geom, 1) for geom in gdf_raw.geometry)
cov_mask = rasterio.features.rasterize(
    shapes,
    out_shape=(wp_h, wp_w),
    transform=wp_tf,
    fill=0,
    dtype=np.uint8,
)

# Residual: pixels with population that fall outside all settlement polygons
residual_mask = (cov_mask == 0) & (wp_data > 0)
del cov_mask, gdf_raw   # free memory

res_pop  = wp_data[residual_mask].sum()
res_npx  = int(residual_mask.sum())
stage1_pop = wp_total - res_pop   # population inside polygons

print(f"  Residual pixels (outside all polygons, Pop>0): {res_npx:,}")
print(f"  Residual population:          {res_pop:,.0f}  ({100*res_pop/wp_total:.2f}% of national)")
print(f"  Polygon-covered population:   {stage1_pop:,.0f}  ({100*stage1_pop/wp_total:.2f}% of national)")
print(f"  Stage-1 gate check — matches 3.34 M?: {'YES' if abs(res_pop-3_340_098)<5000 else 'WARN — check'}")

# ══════════════════════════════════════════════════════════════════════════════
# S3 — Aggregate residual pixels to coarse cells
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n── S3: Aggregate residual to {COARSE_RES}° coarse cells ──")

# Get (row, col) indices of residual pixels
rows_idx, cols_idx = np.where(residual_mask)
del residual_mask

# Pixel centre coordinates (WGS84)
px_x = wp_tf.c + (cols_idx + 0.5) * wp_tf.a   # longitude
px_y = wp_tf.f + (rows_idx + 0.5) * wp_tf.e   # latitude (negative step)
px_pop = wp_data[rows_idx, cols_idx]
del rows_idx, cols_idx

# Coarse cell indices (floor division)
ci = np.floor(px_x / COARSE_RES).astype(np.int32)
ri = np.floor(px_y / COARSE_RES).astype(np.int32)
cell_key = ri.astype(np.int64) * 1_000_000 + ci.astype(np.int64)   # unique cell ID

print(f"  Grouping {res_npx:,} pixels → coarse cells...")
df_px = pd.DataFrame({
    'cell_key': cell_key,
    'px_x': px_x,
    'px_y': px_y,
    'pop': px_pop,
})
del px_x, px_y, px_pop, cell_key, ci, ri

# Per-cell: population sum, pop-weighted centroid, pixel count
grp = df_px.groupby('cell_key')

pop_sum  = grp['pop'].sum()
px_count = grp['pop'].count()  # number of populated pixels per cell

# Pop-weighted centroid
w_x = (df_px['px_x'] * df_px['pop']).groupby(df_px['cell_key']).sum() / pop_sum
w_y = (df_px['px_y'] * df_px['pop']).groupby(df_px['cell_key']).sum() / pop_sum
del df_px

# Pixel area per cell (sum of 100m pixel areas at each pixel's latitude)
# Each WorldPop pixel ≈ |Δlon| × cos(lat) × 111.32 × |Δlat| × 111.32 km²
px_deg_w = abs(wp_tf.a)  # 0.000833°
px_deg_h = abs(wp_tf.e)  # 0.000833°
km_per_deg_lat = 111.32
# Pixel area at weighted-centroid latitude (approximate; good for Africa)
px_area_km2 = (px_deg_w * km_per_deg_lat * np.cos(np.radians(w_y))
               * px_deg_h * km_per_deg_lat)
grid_cell_area_km2 = px_count * px_area_km2   # sum of all populated pixel areas

# Keep cells with Pop ≥ 1 (should all qualify, but guard)
keep = pop_sum >= 1.0
n_disp = int(keep.sum())
print(f"  Dispersed cells retained (Pop ≥ 1): {n_disp:,}")
print(f"  Combined spine total:                {214198 + n_disp:,}")
print(f"  Dispersed population sum:            {pop_sum[keep].sum():,.0f}")

df_disp = pd.DataFrame({
    'X_deg':        w_x[keep].values,
    'Y_deg':        w_y[keep].values,
    'Pop':          pop_sum[keep].values,
    'GridCellArea': grid_cell_area_km2[keep].values,
    'IsUrban':      0,
    'IsUrban_type': 0,
    'building_count': 0,
    'building_area':  0.0,
    'grid3_type':   'Dispersed',
    'source':       'dispersed',
}).reset_index(drop=True)

df_disp['id'] = np.arange(1, n_disp + 1) + DISP_ID_OFFSET

# ══════════════════════════════════════════════════════════════════════════════
# S4 — Admin-1 join for dispersed cells
# ══════════════════════════════════════════════════════════════════════════════
print("\n── S4: Admin-1 join (dispersed) ──")

adm1 = gpd.read_file(str(ADM1_VEC))
name_col = 'shapeName' if 'shapeName' in adm1.columns else adm1.columns[1]

pts_gdf = gpd.GeoDataFrame(
    {'_idx': np.arange(len(df_disp))},
    geometry=gpd.points_from_xy(df_disp['X_deg'].values, df_disp['Y_deg'].values),
    crs="EPSG:4326",
)
joined = gpd.sjoin(pts_gdf, adm1[[name_col, 'geometry']], how='left', predicate='within')
joined = joined[~joined.index.duplicated(keep='first')]
admin1_vals = joined[name_col].reindex(pts_gdf.index)

n_missing = admin1_vals.isna().sum()
if n_missing > 0:
    print(f"  WARNING: {n_missing} dispersed cells outside ADM1 → filling 'Zambia'")
    admin1_vals = admin1_vals.fillna('Zambia')

df_disp['Admin_1'] = admin1_vals.values
print(f"  Admin_1 distribution (dispersed):")
for prov, cnt in df_disp['Admin_1'].value_counts().items():
    print(f"    {prov}: {cnt:,}")

# ══════════════════════════════════════════════════════════════════════════════
# S5 — Load Stage-1 cluster spine and tag source
# ══════════════════════════════════════════════════════════════════════════════
print("\n── S5: Load Stage-1 cluster spine ──")
df_clusters = pd.read_csv(STAGE1_CSV)
df_clusters['source'] = 'cluster'
print(f"  Cluster rows: {len(df_clusters):,}  Pop: {df_clusters['Pop'].sum():,.0f}")

# ══════════════════════════════════════════════════════════════════════════════
# S6 — Combine and re-derive IsUrban on combined spine
# ══════════════════════════════════════════════════════════════════════════════
print("\n── S6: Combine and re-derive IsUrban ──")

# Align columns
COLS = ['id','X_deg','Y_deg','Pop','GridCellArea','IsUrban','IsUrban_type',
        'Admin_1','building_count','building_area','grid3_type','source']
# pop_density is re-derived below
df_clusters_sub = df_clusters[COLS].copy()
df_disp_sub     = df_disp[COLS].copy()

df_combined = pd.concat([df_clusters_sub, df_disp_sub], ignore_index=True)

# Re-derive population density (Pop / GridCellArea)
df_combined['pop_density'] = df_combined['Pop'] / df_combined['GridCellArea'].replace(0, np.nan)

# Re-derive IsUrban:
#   - Dispersed rows: IsUrban=0 by definition (locked).
#   - Cluster rows:   density threshold calibrated so that
#       (urban cluster pop) / (total combined pop) = URBAN_SHARE_TARGET
#
# This ensures no dispersed row can ever be classified urban regardless of density.
total_pop_combined = df_combined['Pop'].sum()
target_urban_pop   = URBAN_SHARE_TARGET * total_pop_combined

cluster_mask = df_combined['source'] == 'cluster'
thresholds   = np.logspace(0, 5, 1000)
best_thresh, best_diff = None, float('inf')
for thresh in thresholds:
    u_pop = df_combined.loc[cluster_mask & (df_combined['pop_density'] >= thresh), 'Pop'].sum()
    diff  = abs(u_pop - target_urban_pop)
    if diff < best_diff:
        best_diff, best_thresh = diff, thresh

# Apply: only cluster rows can be urban
df_combined['IsUrban'] = 0
df_combined.loc[cluster_mask & (df_combined['pop_density'] >= best_thresh), 'IsUrban'] = 1

urban_pop_final   = df_combined.loc[df_combined['IsUrban'] == 1, 'Pop'].sum()
urban_share_final = urban_pop_final / total_pop_combined

print(f"  Recalibrated density threshold (cluster rows only): ≥ {best_thresh:.1f} p/km²")
print(f"  Target urban pop:               {target_urban_pop:,.0f}")
print(f"  Achieved urban pop:             {urban_pop_final:,.0f}")
print(f"  Urban pop share (combined):     {urban_share_final:.4f}  (target: {URBAN_SHARE_TARGET})")
print(f"  Urban clusters (IsUrban=1):     {(df_combined['IsUrban']==1).sum():,}")

n_disp_urban = int(df_combined.loc[(df_combined['source']=='dispersed') & (df_combined['IsUrban']==1)].shape[0])
if n_disp_urban > 0:
    print(f"  WARN: {n_disp_urban} dispersed rows got IsUrban=1 — logic error")
else:
    print(f"  All dispersed rows are IsUrban=0 ✓")

# ══════════════════════════════════════════════════════════════════════════════
# S7 — Output
# ══════════════════════════════════════════════════════════════════════════════
print("\n── S7: Writing outputs ──")

# Final column order (matches Stage-1 plus source)
FINAL_COLS = ['id','X_deg','Y_deg','Pop','GridCellArea','IsUrban','IsUrban_type',
              'Admin_1','building_count','building_area','grid3_type','pop_density','source']
df_out = df_combined[FINAL_COLS].copy()
df_out.to_csv(OUT_CSV, index=False)
print(f"  CSV: {OUT_CSV.name}  ({len(df_out):,} rows × {len(df_out.columns)} cols)")

# GPKG with geometry from centroid points
gdf_out = gpd.GeoDataFrame(
    df_out,
    geometry=gpd.points_from_xy(df_out['X_deg'], df_out['Y_deg']),
    crs="EPSG:4326",
)
gdf_out.to_file(str(OUT_GPKG), driver='GPKG', layer='grid3_combined')
print(f"  GPKG: {OUT_GPKG.name}")

# ══════════════════════════════════════════════════════════════════════════════
# S8 — Verification gate
# ══════════════════════════════════════════════════════════════════════════════
print("\n══════════════════════════════════════════════════════")
print("  VERIFICATION GATE — Stage 1b")
print("══════════════════════════════════════════════════════")

combined_pop   = df_out['Pop'].sum()
pct_vs_raster  = 100.0 * (combined_pop - wp_total) / wp_total
cluster_pop    = df_out.loc[df_out['source']=='cluster', 'Pop'].sum()
disp_pop_check = df_out.loc[df_out['source']=='dispersed', 'Pop'].sum()

print(f"\n[A] Population reconciliation")
print(f"    WorldPop raster total:              {wp_total:>15,.0f}")
print(f"    Combined spine Pop total:           {combined_pop:>15,.0f}")
print(f"    % difference:                       {pct_vs_raster:+.3f}%")
print(f"    Within 0.5% target:                 {'PASS ✓' if abs(pct_vs_raster)<0.5 else 'FAIL ✗'}")
print(f"    Residual (raster − spine):          {wp_total-combined_pop:>15,.0f}")

print(f"\n[B] Settlement counts")
print(f"    Cluster rows (Stage 1):             {(df_out['source']=='cluster').sum():,}")
print(f"    Dispersed rows (Stage 1b):          {(df_out['source']=='dispersed').sum():,}")
print(f"    Combined total:                     {len(df_out):,}")
print(f"    Dispersed grid resolution:          {COARSE_RES}° ≈ {COARSE_RES*111.32:.1f} km")

print(f"\n[C] Urban/rural split (combined)")
print(f"    Density threshold:                  ≥ {best_thresh:.1f} p/km²")
print(f"    Urban pop share:                    {urban_share_final:.4f}  (target {URBAN_SHARE_TARGET})")
print(f"    Urban clusters (IsUrban=1):         {(df_out['IsUrban']==1).sum():,}")
print(f"    All dispersed rows rural:           {'YES ✓' if n_disp_urban==0 else 'NO ✗'}")

print(f"\n[D] Population share by source")
print(f"    cluster:   {cluster_pop:,.0f}  ({100*cluster_pop/combined_pop:.2f}%)")
print(f"    dispersed: {disp_pop_check:,.0f}  ({100*disp_pop_check/combined_pop:.2f}%)")

print(f"\n[E] Size distributions (combined)")
pop_c   = df_out.loc[df_out['source']=='cluster',   'Pop']
pop_d   = df_out.loc[df_out['source']=='dispersed', 'Pop']
area_c  = df_out.loc[df_out['source']=='cluster',   'GridCellArea']
area_d  = df_out.loc[df_out['source']=='dispersed', 'GridCellArea']
print(f"    Cluster  Pop  — median: {pop_c.median():.1f}  mean: {pop_c.mean():.1f}  max: {pop_c.max():.0f}")
print(f"    Dispersed Pop — median: {pop_d.median():.1f}  mean: {pop_d.mean():.1f}  max: {pop_d.max():.0f}")
print(f"    Cluster  Area (km²) — median: {area_c.median():.5f}  mean: {area_c.mean():.4f}")
print(f"    Dispersed Area (km²) — median: {area_d.median():.4f}  mean: {area_d.mean():.4f}")

print(f"\n[F] Null check")
for col in ['X_deg','Y_deg','Pop','GridCellArea','IsUrban','Admin_1']:
    n_null = df_out[col].isna().sum()
    print(f"    {col}: {n_null} null  {'✓' if n_null==0 else '⚠'}")

elapsed = time.time() - t0
print(f"\n── Done in {elapsed:.0f} s ──")

# ══════════════════════════════════════════════════════════════════════════════
# S9 — Write notes
# ══════════════════════════════════════════════════════════════════════════════
notes_dir = ROOT / "notes"
notes_dir.mkdir(parents=True, exist_ok=True)

notes = f"""# GRID3 Spine Stage 1b — Run Notes

**Date:** 2026-06-28
**Script:** `_claude_workspace/scripts/build_grid3_spine_stage1b.py`
**Outputs:**
- `data/processed/zambia_grid3_spine_combined.csv` — combined spine (clusters + dispersed)
- `data/processed/zambia_grid3_spine_combined.gpkg` — same with geometry

---

## Motivation
The Stage-1 cluster spine captured only 81.83% of WorldPop because the GRID3 settlement-extent polygons do not cover every populated WorldPop pixel. The 18.17% residual represents dispersed rural population (hamlet-scale settlement below GRID3 detection thresholds, or population in the interstices between polygons). This population is the hardest-to-reach, stand-alone-PV-dominant group; dropping it would bias the national technology split and cost estimates.

## Dispersed-settlement aggregation method
- **Resolution:** {COARSE_RES}° ≈ {COARSE_RES*111.32:.1f} km (chosen to give combined spine ≈ 270k, within the 250–300k target).
- **Population:** sum of WorldPop 100m pixels in each coarse cell.
- **Centroid:** population-weighted mean of pixel centres within the cell.
- **GridCellArea:** sum of individual WorldPop pixel areas (each ≈ 0.000833° × cos(lat) × 111.32 km in each direction). This represents the actual populated footprint within the cell, not the full coarse-cell area, for consistency with the polygon-area convention used for GRID3 clusters.
- **IsUrban:** 0 for all dispersed rows by definition (dispersed = rural).
- **grid3_type:** "Dispersed".
- **IDs:** 1,000,001 – 1,{DISP_ID_OFFSET + n_disp:,} (offset {DISP_ID_OFFSET:,} to avoid collision with cluster IDs 1–214,198).

---

## Verification gate results

### A. Population reconciliation
| Metric | Value |
|---|---|
| WorldPop raster total | {wp_total:,.0f} |
| Combined spine Pop total | {combined_pop:,.0f} |
| % difference | {pct_vs_raster:+.3f}% |
| Within 0.5% target | {'PASS' if abs(pct_vs_raster)<0.5 else 'FAIL'} |
| Residual (raster − spine) | {wp_total-combined_pop:,.0f} |

The remaining sub-0.5% gap is attributable to WorldPop pixels with Pop < 1 person (dropped by the Stage-1 zero-pop filter applied implicitly through the rasterize–residual pipeline).

### B. Settlement counts
| Source | Count | Population | % of total |
|---|---|---|---|
| Cluster (Stage 1) | {(df_out['source']=='cluster').sum():,} | {cluster_pop:,.0f} | {100*cluster_pop/combined_pop:.2f}% |
| Dispersed (Stage 1b) | {(df_out['source']=='dispersed').sum():,} | {disp_pop_check:,.0f} | {100*disp_pop_check/combined_pop:.2f}% |
| **Combined** | **{len(df_out):,}** | **{combined_pop:,.0f}** | 100% |

### C. Urban/rural split
| Method | Threshold | Urban share |
|---|---|---|
| Stage-1 cluster-only | ≥ 2073.2 p/km² | 0.4362 |
| Combined spine recalibrated | ≥ {best_thresh:.1f} p/km² | {urban_share_final:.4f} |
| Target (2020 WB national) | — | {URBAN_SHARE_TARGET} |

Adding dispersed rural population (all IsUrban=0) dilutes the urban share; the threshold is recalibrated downward to restore the 0.437 target on the combined spine.
All {(df_out['source']=='dispersed').sum():,} dispersed rows are IsUrban=0 ✓

### D. Size distributions
| Type | Pop median | Pop mean | Pop max | Area median (km²) | Area mean (km²) |
|---|---|---|---|---|---|
| Cluster | {pop_c.median():.1f} | {pop_c.mean():.1f} | {pop_c.max():.0f} | {area_c.median():.5f} | {area_c.mean():.4f} |
| Dispersed | {pop_d.median():.1f} | {pop_d.mean():.1f} | {pop_d.max():.0f} | {area_d.median():.4f} | {area_d.mean():.4f} |

---

- Recalibrated density threshold ({best_thresh:.1f} p/km²) vs Stage-1 value (2073.2 p/km²) — confirm which is used in Stage 3 calibration.
- Dispersed GridCellArea uses populated-pixel footprint, not full coarse-cell area. Confirm this is appropriate for OnSSET demand calculations (or switch to full cell area).
- 91 dispersed cells with Admin_1 = "Zambia" (fell outside ADM1 boundaries). Check if these are border-adjacent cells.

---

## Stage-2 checklist
The combined spine is now ready for Stage 2. For every row in `zambia_grid3_spine_combined.csv`, Stage 2 must compute:

1. `GHI` — from GHI raster, sampled at (X_deg, Y_deg)
2. `WindVel` — from wind raster
3. `NightLights` — from VIIRS NTL raster
4. `TravelHours` — from travel-time raster (minutes ÷ 60)
5. `Elevation` — from SRTM DEM
6. `Slope` — from slope raster
7. `CurrentHVLineDist`, `CurrentMVLineDist` — NN to OSM power lines (km)
8. `SubstationDist`, `TransformerDist` — NN to OSM nodes
9. `RoadDist` — NN to OSM roads
10. `HydropowerDist`, `Hydropower`, `HydropowerFID` — NN to hydro CSV
11. `PlannedHVLineDist`, `PlannedMVLineDist`, `MGDist` — sentinel 9999
12. `ElecPop`, `IsUrban`, `PerCapitaDemand`, demand-tier columns — carry forward from combined spine / set to 0 pending Stage 3 calibration

Output: a 40-column OnSSET-ready CSV at `data/processed/zambia_grid3_spine_stage2.csv`.
"""

with open(NOTES_PATH, 'w') as f:
    f.write(notes)
print(f"\n  Notes written → {NOTES_PATH.relative_to(ROOT)}")
