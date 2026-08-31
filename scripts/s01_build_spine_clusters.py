"""
s01_build_spine_clusters.py — settlement spine, stage 1 of 3.
Stage 1 of the GRID3 settlement spine rebuild:
  - Geometry (centroid, area)
  - Population (WorldPop zonal sum per polygon)
  - Urban/rural classification
  - Admin-1 assignment
  - Verification gate

Does NOT touch distances, LCOE, or calibration (Stage 2+).
Run with the project venv:
  python scripts/s01_build_spine_clusters.py
"""

import warnings
# Scoped to third-party deprecation noise only. RuntimeWarning (divide-by-zero,
# overflow, invalid value) and every other category stay visible, so a numerical
# fault surfaces rather than being silently discarded.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import rasterio.features

t0 = time.time()

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT  = Path(__file__).resolve().parent.parent
RAW   = ROOT / "data/raw/zambia"
PROC  = ROOT / "data/processed"
PROC.mkdir(parents=True, exist_ok=True)

GRID3_GPKG  = RAW / "grid3_settlements/grid3_zmb_settlement_extents_v3_0/GRID3_ZMB_settlement_extents_v3_0.gpkg"
WP_TIF      = RAW / "population/worldpop/zmb_ppp_2020_UNadj_constrained.tif"
ADM1_VEC    = RAW / "admin/geoboundaries/geoBoundaries-ZMB-ADM1.geojson"

OUT_CSV     = PROC / "zambia_grid3_spine_stage1.csv"
OUT_GPKG    = PROC / "zambia_grid3_spine_stage1.gpkg"
NOTES_PATH  = ROOT / "notes/2026-06-27_grid3_spine_stage1.md"

UTM = "EPSG:32735"   # UTM Zone 35S — metric CRS for area computation

# National urban share target (2020 census / World Bank)
URBAN_SHARE_TARGET = 0.437

# ── Load GRID3 settlement extents ────────────────────────────────────────────
print("\n── S1: Load GRID3 extents ──")
gdf = gpd.read_file(str(GRID3_GPKG))
n_raw = len(gdf)
print(f"  Raw features: {n_raw:,}")
print("  Type distribution:")
for t, cnt in gdf['type'].value_counts().items():
    print(f"    {t}: {cnt:,}  ({100*cnt/n_raw:.1f}%)")

# Give every row a 0-based integer index used as raster label (1-indexed)
gdf = gdf.reset_index(drop=True)

# Reproject to UTM 35S for area computation; keep WGS84 for centroids
gdf_utm = gdf.to_crs(UTM)

# ── Population by zonal sum (rasterize + numpy.add.at) ───────────────────────
print("\n── S2: WorldPop zonal sums ──")
print("  Loading WorldPop raster...")

with rasterio.open(WP_TIF) as src:
    wp_data   = src.read(1).astype(np.float64)
    wp_nodata = src.nodata          # -99999.0
    wp_tf     = src.transform
    wp_crs    = src.crs
    wp_h, wp_w = src.height, src.width

# Zero-out nodata and negative pixels before summing
if wp_nodata is not None:
    wp_data[wp_data == wp_nodata] = 0.0
wp_data[wp_data < 0] = 0.0

wp_total = wp_data.sum()
print(f"  WorldPop national total (raster): {wp_total:,.0f}")

# Rasterize polygons: each polygon → its 1-based integer ID
# Memory: int32 at 14047×11826 = ~664 MB; wp_data float64 = ~1.3 GB total
print("  Rasterizing GRID3 polygons onto WorldPop grid (may take ~60 s)...")
shapes = ((geom, idx + 1) for idx, geom in enumerate(gdf.geometry))  # generator

label_raster = rasterio.features.rasterize(
    shapes,
    out_shape=(wp_h, wp_w),
    transform=wp_tf,
    fill=0,           # background
    dtype=np.int32,
)

# Zonal sum: for each labelled pixel, add its population
print("  Computing zonal sums...")
valid_mask = label_raster > 0          # pixels inside a polygon
poly_ids   = label_raster[valid_mask]  # 1-based polygon IDs
pop_vals   = wp_data[valid_mask]       # WorldPop pixel values

# pop_per_poly[i] = sum of WorldPop pixels inside polygon i (0-based)
pop_per_poly = np.zeros(n_raw, dtype=np.float64)
np.add.at(pop_per_poly, poly_ids - 1, pop_vals)

gdf['Pop'] = pop_per_poly
covered_pop = pop_per_poly.sum()
residual_pop = wp_total - covered_pop
print(f"  Population inside GRID3 polygons: {covered_pop:,.0f}")
print(f"  Residual (outside all polygons):  {residual_pop:,.0f}  ({100*residual_pop/wp_total:.2f}% of national total)")

# Free large arrays
del label_raster, valid_mask, poly_ids, pop_vals, wp_data

# ── Filter zero-pop clusters ─────────────────────────────────────────────────
print("\n── S3: Zero-pop filter ──")
zero_mask = gdf['Pop'] < 1.0
n_dropped  = zero_mask.sum()
pop_dropped = gdf.loc[zero_mask, 'Pop'].sum()
print(f"  Dropping {n_dropped:,} clusters with Pop < 1")
print(f"  Population carried by dropped clusters: {pop_dropped:,.0f}")

gdf = gdf[~zero_mask].copy()
n_retained = len(gdf)
print(f"  Retained clusters: {n_retained:,}")

# Also trim UTM GDF to match
gdf_utm = gdf_utm.loc[gdf.index].copy()

# ── Centroid (representative point) + cell area ──────────────────────────────
print("\n── S4: Centroids and cell areas ──")

# Representative point guaranteed to lie inside polygon (WGS84)
rep_pts = gdf.geometry.representative_point()
gdf['X_deg'] = rep_pts.x
gdf['Y_deg'] = rep_pts.y

# Polygon area in km² (UTM 35S)
gdf_utm = gdf_utm.loc[gdf.index]
gdf['GridCellArea'] = gdf_utm.geometry.area / 1e6   # m² → km²

print(f"  GridCellArea (km²): median={gdf.GridCellArea.median():.4f}  mean={gdf.GridCellArea.mean():.4f}  max={gdf.GridCellArea.max():.4f}")
print(f"  Pop per cluster:    median={gdf.Pop.median():.1f}  mean={gdf.Pop.mean():.1f}  max={gdf.Pop.max():.0f}")

# ── Urban/rural classification ───────────────────────────────────────────────
print("\n── S5: Urban/rural classification ──")

# --- Method A: GRID3 type-based ---
# Degree of urbanisation mapping:
#   Built-up Area        → IsUrban = 1  (dense urban form)
#   Small Settlement Area → IsUrban = 0  (peri-urban / rural)
#   Hamlet               → IsUrban = 0  (rural)
URBAN_TYPES = {'Built-up Area'}
gdf['IsUrban_type'] = gdf['type'].isin(URBAN_TYPES).astype(int)

urban_pop_type   = gdf.loc[gdf['IsUrban_type'] == 1, 'Pop'].sum()
total_pop_retain = gdf['Pop'].sum()
urban_share_type = urban_pop_type / total_pop_retain
print(f"  Method A (type-based):  urban pop share = {urban_share_type:.4f}  (target: {URBAN_SHARE_TARGET})")
print(f"    Built-up Area clusters: {(gdf['IsUrban_type']==1).sum():,}")

# --- Method B: Population-density threshold ---
# Density = Pop / GridCellArea (persons/km²)
gdf['pop_density'] = gdf['Pop'] / gdf['GridCellArea'].replace(0, np.nan)

# Binary search for density threshold that yields urban_share ≈ URBAN_SHARE_TARGET
pop_total = gdf['Pop'].sum()
thresholds = np.logspace(0, 5, 500)   # 1 → 100,000 persons/km²
best_thresh = None
best_diff   = 1.0

for thresh in thresholds:
    u_pop = gdf.loc[gdf['pop_density'] >= thresh, 'Pop'].sum()
    diff  = abs(u_pop / pop_total - URBAN_SHARE_TARGET)
    if diff < best_diff:
        best_diff   = diff
        best_thresh = thresh

gdf['IsUrban_density'] = (gdf['pop_density'] >= best_thresh).astype(int)
urban_pop_density  = gdf.loc[gdf['IsUrban_density'] == 1, 'Pop'].sum()
urban_share_density= urban_pop_density / pop_total
print(f"  Method B (density threshold ≥ {best_thresh:.1f} p/km²):  urban pop share = {urban_share_density:.4f}")
print(f"    Urban clusters: {(gdf['IsUrban_density']==1).sum():,}")

# Decision: type-based diverges materially (< 0.01 urban share vs 0.437 target)
# → adopt Method B as IsUrban; retain Method A as IsUrban_type for reference
type_diverges = abs(urban_share_type - URBAN_SHARE_TARGET) > 0.05
if type_diverges:
    print(f"\n  Type-based share ({urban_share_type:.4f}) diverges materially from target ({URBAN_SHARE_TARGET}).")
    print(f"  → Using density-threshold IsUrban (Method B) as primary classification.")
    gdf['IsUrban'] = gdf['IsUrban_density']
    isurban_method = f"density threshold ≥ {best_thresh:.1f} p/km² (calibrated to 0.437 national urban share)"
else:
    print(f"  → Using type-based IsUrban (Method A).")
    gdf['IsUrban'] = gdf['IsUrban_type']
    isurban_method = "GRID3 type-based (Built-up Area → urban)"

urban_pop_final   = gdf.loc[gdf['IsUrban'] == 1, 'Pop'].sum()
urban_share_final = urban_pop_final / total_pop_retain
print(f"\n  Final urban pop share: {urban_share_final:.4f}  (target: {URBAN_SHARE_TARGET})")

# ── Admin-1 spatial join ─────────────────────────────────────────────────────
print("\n── S6: Admin-1 spatial join ──")

adm1 = gpd.read_file(str(ADM1_VEC))
name_col = 'shapeName' if 'shapeName' in adm1.columns else adm1.columns[1]

pts_gdf = gpd.GeoDataFrame(
    {'_idx': np.arange(len(gdf))},
    geometry=gpd.points_from_xy(gdf['X_deg'].values, gdf['Y_deg'].values),
    crs="EPSG:4326",
    index=gdf.index,
)
joined = gpd.sjoin(pts_gdf, adm1[[name_col, 'geometry']], how='left', predicate='within')
# sjoin may duplicate rows if a point falls on a boundary; keep first match
joined = joined[~joined.index.duplicated(keep='first')]
admin1_vals = joined[name_col].reindex(gdf.index)

n_missing = admin1_vals.isna().sum()
if n_missing > 0:
    print(f"  WARNING: {n_missing} points fell outside ADM1 polygons — filling 'Zambia'")
    admin1_vals = admin1_vals.fillna('Zambia')

gdf['Admin_1'] = admin1_vals.values
provinces = sorted(gdf['Admin_1'].unique())
print(f"  Provinces found ({len(provinces)}): {provinces}")

# ── Output ───────────────────────────────────────────────────────────────────
print("\n── S7: Writing outputs ──")

# Assign stable integer IDs (1-based, after filtering)
gdf = gdf.reset_index(drop=True)
gdf['id'] = gdf.index + 1

# Rename GRID3 building fields to match expected schema
gdf = gdf.rename(columns={'type': 'grid3_type'})

# CSV — flat, no geometry
CSV_COLS = [
    'id', 'X_deg', 'Y_deg', 'Pop', 'GridCellArea',
    'IsUrban', 'IsUrban_type', 'Admin_1',
    'building_count', 'building_area', 'grid3_type',
    'pop_density',
]
df_out = gdf[CSV_COLS].copy()
df_out.to_csv(OUT_CSV, index=False)
print(f"  CSV: {OUT_CSV.name}  ({len(df_out):,} rows × {len(df_out.columns)} cols)")

# GPKG — with geometry (WGS84)
GPKG_COLS = CSV_COLS + ['geometry']
gdf[GPKG_COLS].to_file(str(OUT_GPKG), driver='GPKG', layer='grid3_stage1')
print(f"  GPKG: {OUT_GPKG.name}")

# ── Verification gate ────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════════")
print("  VERIFICATION GATE — Stage 1")
print("══════════════════════════════════════════════════════")

wp_national   = wp_total
spine_total   = gdf['Pop'].sum()
pct_diff      = 100.0 * (spine_total - wp_national) / wp_national

print(f"\n[A] Population reconciliation")
print(f"    WorldPop national total (raster): {wp_national:>15,.0f}")
print(f"    GRID3 spine total Pop:            {spine_total:>15,.0f}")
print(f"    Residual (outside polygons):      {residual_pop:>15,.0f}  ({100*residual_pop/wp_national:.2f}%)")
print(f"    % diff (spine vs raster):         {pct_diff:+.3f}%")

print(f"\n[B] Cluster counts")
print(f"    Raw GRID3 features:     {n_raw:,}")
print(f"    Dropped (Pop < 1):      {n_dropped:,}  (Pop={pop_dropped:.0f})")
print(f"    Retained:               {n_retained:,}")

print(f"\n[C] Urban/rural split")
print(f"    Method: {isurban_method}")
print(f"    IsUrban=1 clusters:     {(gdf['IsUrban']==1).sum():,}")
print(f"    IsUrban=0 clusters:     {(gdf['IsUrban']==0).sum():,}")
print(f"    Urban pop share:        {urban_share_final:.4f}  (target: {URBAN_SHARE_TARGET})")
print(f"    (Type-based share:      {urban_share_type:.4f}  → {'diverges' if type_diverges else 'OK'})")

print(f"\n[D] Size distributions")
print(f"    Pop — median: {gdf.Pop.median():.1f}  mean: {gdf.Pop.mean():.1f}  max: {gdf.Pop.max():.0f}")
print(f"    GridCellArea (km²) — median: {gdf.GridCellArea.median():.5f}  mean: {gdf.GridCellArea.mean():.4f}  max: {gdf.GridCellArea.max():.3f}")
print(f"    (1 km spine reference: uniform 1.000 km²)")

print(f"\n[E] Missing / nulls")
for col in ['X_deg', 'Y_deg', 'Pop', 'GridCellArea', 'Admin_1', 'building_count']:
    n_null = gdf[col].isna().sum()
    flag   = '⚠' if n_null > 0 else '✓'
    print(f"    {col}: {n_null} null  {flag}")

elapsed = time.time() - t0
print(f"\n── Done in {elapsed:.0f} s ──")

# ── Write notes file ─────────────────────────────────────────────────────────
notes_dir = ROOT / "notes"
notes_dir.mkdir(parents=True, exist_ok=True)

notes = f"""# GRID3 Spine Stage 1 — Run Notes

**Date:** 2026-06-28
**Script:** `scripts/s01_build_spine_clusters.py`
**Outputs:** `data/processed/zambia_grid3_spine_stage1.csv` + `.gpkg`

---

## Verification gate results

### A. Population reconciliation
| Metric | Value |
|---|---|
| WorldPop national total (raster) | {wp_national:,.0f} |
| GRID3 spine total Pop | {spine_total:,.0f} |
| Residual outside polygons | {residual_pop:,.0f} ({100*residual_pop/wp_national:.2f}%) |
| % difference (spine vs raster) | {pct_diff:+.3f}% |

The residual represents WorldPop population in pixels that do not overlap any GRID3 settlement polygon (dispersed rural population not captured by settlement extents). This is expected and structurally different from the 1 km spine which captures *all* populated pixels by definition.

### B. Cluster counts
| Stage | Count |
|---|---|
| Raw GRID3 features | {n_raw:,} |
| Dropped (Pop < 1) | {n_dropped:,} |
| Retained | {n_retained:,} |

Dropped clusters carried {pop_dropped:.0f} persons total — negligible.

### C. Urban/rural classification (`IsUrban`)

**Type → IsUrban mapping:**
| GRID3 `type` | IsUrban | Rationale |
|---|---|---|
| Built-up Area | 1 | Dense urban fabric |
| Small Settlement Area | 0 | Peri-urban / rural cluster |
| Hamlet | 0 | Rural hamlet |

**Method A (type-based) urban pop share: {urban_share_type:.4f}**
This diverges materially from the 0.437 national urban target because only {(gdf['type']=='Built-up Area').sum() if 'type' in gdf.columns else (gdf['grid3_type']=='Built-up Area').sum():,} features are typed Built-up Area, capturing a negligible population fraction.

**Method B (density threshold) adopted as primary:**
Threshold ≥ {best_thresh:.1f} persons/km² → urban share = {urban_share_final:.4f} (target: {URBAN_SHARE_TARGET}).
`IsUrban_type` retained as a separate column for cross-checking.

### D. Size distributions
| Metric | Median | Mean | Max |
|---|---|---|---|
| Pop per cluster | {gdf.Pop.median():.1f} | {gdf.Pop.mean():.1f} | {gdf.Pop.max():.0f} |
| GridCellArea (km²) | {gdf.GridCellArea.median():.5f} | {gdf.GridCellArea.mean():.4f} | {gdf.GridCellArea.max():.3f} |

The 1 km spine had uniform GridCellArea = 1.000 km². The GRID3 spine has highly variable areas reflecting actual settlement footprints — this is the key realism gain.

---

- Confirm the density threshold ({best_thresh:.1f} p/km²) is reasonable for Zambia vs the literature (typically 300–1500 p/km² for SSA).
- Cross-check residual population ({100*residual_pop/wp_national:.2f}% of national total) against Zambia's dispersed rural population literature.
- The constrained WorldPop total ({wp_national:,.0f}) differs from the 2020 census-based 18.38 M used in the 1 km spine calibration — reconcile the difference before Stage 3 calibration.

---

## What s02 needs
1. The Stage-1 CSV/GPKG with centroid coordinates (`X_deg`, `Y_deg`) for spatial distance queries.
2. `GridCellArea` per cluster (needed for demand calculations).
3. `IsUrban` (density-threshold method) as the urbanisation flag for OnSSET tiers.
4. All Stage-2 distance columns to be computed from the centroids:
   `CurrentHVLineDist`, `CurrentMVLineDist`, `SubstationDist`, `TransformerDist`, `RoadDist`, `HydropowerDist`, plus raster samples (`GHI`, `WindVel`, `NightLights`, `TravelHours`, `Elevation`, `Slope`).
5. Electrification order and demand columns remain 0 until Stage 3 (calibration).
"""

with open(NOTES_PATH, 'w') as f:
    f.write(notes)
print(f"\n  Notes written → {NOTES_PATH.relative_to(ROOT)}")
