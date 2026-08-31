"""
s03_build_spine_attributes.py — settlement spine, stage 3 of 3.
Stage 2: compute all OnSSET spatial columns on the 270,526-row GRID3 combined spine.

Inputs (from Stage 1b):
  data/processed/zambia_grid3_spine_combined.csv   — 270,526 settlements

New grid inputs:
  ZESCO MV distribution lines (Arc 1950 / UTM 35S → datum-transform to EPSG:32735)
  NEP planned MV extensions (EPSG:4326)

Reused layers (same paths as build_zambia_settlements.py):
  GHI, WindVel, NightLights, TravelHours, SRTM/Slope, HV transmission,
  transformers, substations, FB predictive MV, OSM roads, hydro

Outputs:
  data/processed/zambia_grid3_spine_stage2.csv
  data/processed/zambia_grid3_spine_stage2.gpkg

Hard rules:
  - All distance computations in EPSG:32735 (UTM 35S)
  - ZESCO MV must be reprojected with proper datum transform (Arc 1950 → WGS84)
  - No calibration or LCOE computations
  - Do NOT overwrite Stage 1/1b outputs
"""

import warnings
# Scoped to third-party deprecation noise only. RuntimeWarning (divide-by-zero,
# overflow, invalid value) and every other category stay visible, so a numerical
# fault surfaces rather than being silently discarded.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import re
import time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import rowcol
from rasterio.merge import merge as raster_merge
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from scipy.spatial import cKDTree
import pyogrio

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
RAW      = ROOT / "data/raw/zambia"
PROC     = ROOT / "data/processed"
GRID_DIR = RAW / "grid"

# Input: combined spine from s02
SPINE_IN = PROC / "zambia_grid3_spine_combined.csv"

# Rasters (all pre-existing)
GHI_TIF  = RAW / "resource/ghi/GHI.tif"
WIND_TIF = RAW / "resource/wind/ZMB_wind-speed_100m.tif"
NTL_TIF  = RAW / "resource/nightlights/zmb_viirs_ntl_2020_avg_masked.tif"
TTM_TIF  = RAW / "transport/travel_time/zambia_travel_time_to_cities.tif"
DEM_MRG  = PROC / "zmb_srtm_merged.tif"
SLP_TIF  = PROC / "zmb_slope_degrees.tif"
SRTM_DIR = RAW / "terrain/dem/unzipped"

# NEW grid vectors
MV_ZESCO_SHP = GRID_DIR / "mv_distribution_2023/distribution_medium_voltage_overhead_line_network/Distribution_Medium_Voltage_Overhead_Line_Network.shp"
NEP_MV_GEO   = GRID_DIR / "nep_mv_extension_2023/mv-lines-extensions.geojson"

# Existing grid vectors (reused)
HV_SHP       = GRID_DIR / "transmission_network_wb/zambia-electricity-transmission-network/Zambia Electricity Transmission Network.shp"
MV_FB_CSV    = GRID_DIR / "mv_predictive_fb/electrical_grid_zambia_15.csv"
TX_MV_SHP    = GRID_DIR / "transformers_substations/Zambia - Distribution MV Transformers/Zambia - Distribution MV Transformers.shp"
TX_MVLV_SHP  = GRID_DIR / "transformers_substations/Zambia - Distribution MVLV Transformers/Zambia - Distribution MVLV Transformers.shp"
SUB_DIST_SHP = GRID_DIR / "transformers_substations/Zambia - Distribution_Substations/Zambia - Distribution_Substations.shp"
SUB_HVMV_SHP = GRID_DIR / "transformers_substations/Zambia - HVMVsubstation/HVMVsubstation/HVMVsubstation.shp"
SUB_MVLV_SHP = GRID_DIR / "transformers_substations/Zambia - MVLVsubstation/MVLVsubstation.shp"
ROADS_PBF    = RAW / "transport/roads/zambia-latest.osm.pbf"
HYDRO_CSV    = RAW / "resource/hydro/zambia_hydro_plants.csv"
ADM1_VEC     = RAW / "admin/geoboundaries/geoBoundaries-ZMB-ADM1.geojson"

# Outputs consumed by s04
OUT_CSV  = PROC / "zambia_grid3_spine_stage2.csv"
OUT_GPKG = PROC / "zambia_grid3_spine_stage2.gpkg"

UTM  = "EPSG:32735"
BBOX = (21.9, -18.1, 33.8, -8.1)   # W, S, E, N — Zambia clip

t0 = time.time()

# ── Helpers ────────────────────────────────────────────────────────────────────

def sample_raster(tif_path, xs, ys, nodata_val=np.nan, band=1):
    """Sample raster at (xs, ys) in EPSG:4326. Returns 1-D float array."""
    with rasterio.open(tif_path) as src:
        rows, cols = rowcol(src.transform, xs, ys)
        rows = np.clip(np.asarray(rows), 0, src.height - 1)
        cols = np.clip(np.asarray(cols), 0, src.width  - 1)
        data = src.read(band).astype(float)
        nd   = src.nodata
        vals = data[rows, cols]
        if nd is not None:
            vals[vals == nd] = nodata_val
    return vals


def densify_lines(gdf_utm, spacing_m=500):
    """
    Sample points along every linestring every spacing_m metres.
    Returns (N,2) array in the same projected CRS as gdf_utm.
    """
    coords = []
    for geom in gdf_utm.geometry:
        if geom is None or geom.is_empty:
            continue
        length = geom.length
        if length == 0:
            coords.append((geom.centroid.x, geom.centroid.y))
            continue
        n = max(2, int(length / spacing_m) + 1)
        for frac in np.linspace(0, 1, n):
            pt = geom.interpolate(frac, normalized=True)
            coords.append((pt.x, pt.y))
    return np.array(coords) if coords else np.empty((0, 2))


def nn_dist_km(pts_xy, ref_xy):
    """cKDTree nearest-neighbour distance, km. Returns 9999 if ref_xy empty."""
    if len(ref_xy) == 0:
        return np.full(len(pts_xy), 9999.0)
    tree = cKDTree(ref_xy)
    dists_m, _ = tree.query(pts_xy, workers=-1)
    return dists_m / 1000.0


def parse_hstore(s):
    if not isinstance(s, str):
        return {}
    return dict(re.findall(r'"([^"]+)"=>"([^"]*)"', s))


def dist_stats(arr, name):
    """Print and return a distance summary dict."""
    stats = {
        "mean":   float(np.mean(arr)),
        "median": float(np.median(arr)),
        "min":    float(np.min(arr)),
        "max":    float(np.max(arr)),
        "n_lt_2km":  int((arr < 2).sum()),
        "n_lt_5km":  int((arr < 5).sum()),
        "n_lt_10km": int((arr < 10).sum()),
    }
    print(f"    {name}: mean={stats['mean']:.2f}  median={stats['median']:.2f}  "
          f"min={stats['min']:.4f}  max={stats['max']:.2f} km")
    print(f"    → <2 km: {stats['n_lt_2km']:,}   <5 km: {stats['n_lt_5km']:,}   "
          f"<10 km: {stats['n_lt_10km']:,}")
    return stats

# ── Load the combined spine from s02 ──────────────────────────────────────────────────────
print("\n── S0: Load Stage 1b combined spine ──")
spine = pd.read_csv(SPINE_IN)
print(f"  Rows: {len(spine):,}   Columns: {list(spine.columns)}")
assert len(spine) == 270526, f"Expected 270,526 rows, got {len(spine)}"

xs = spine["X_deg"].values
ys = spine["Y_deg"].values

# Project all centroids to UTM 35S (used for all distance computations)
sett_gdf = gpd.GeoDataFrame(
    {"idx": spine["id"].values},
    geometry=gpd.points_from_xy(xs, ys),
    crs="EPSG:4326"
).to_crs(UTM)
sett_xy = np.column_stack([sett_gdf.geometry.x, sett_gdf.geometry.y])
print(f"  UTM 35S extent: X {sett_xy[:,0].min():.0f}–{sett_xy[:,0].max():.0f}  "
      f"Y {sett_xy[:,1].min():.0f}–{sett_xy[:,1].max():.0f}")

# ── SRTM merged DEM + slope (regenerate if missing) ──────────────────────────
print("\n── S1: SRTM merged DEM + slope ──")

if not DEM_MRG.exists():
    print("  Merged DEM not found — building from SRTM tiles...")
    tile_paths = sorted(SRTM_DIR.glob("srtm_*.tif"))
    print(f"  Merging {len(tile_paths)} tiles...")
    datasets = [rasterio.open(p) for p in tile_paths]
    mosaic, mosaic_tf = raster_merge(datasets)
    for ds in datasets:
        ds.close()
    W, S, E, N = BBOX
    with rasterio.open(tile_paths[0]) as ref:
        crs_  = ref.crs
        dtype = ref.dtypes[0]
        nd_   = ref.nodata if ref.nodata is not None else -32768
    new_w = int(round((E - W) / abs(mosaic_tf.a)))
    new_h = int(round((N - S) / abs(mosaic_tf.e)))
    clip_tf = from_bounds(W, S, E, N, new_w, new_h)
    clipped = np.full((1, new_h, new_w), nd_, dtype=dtype)
    reproject(source=mosaic, destination=clipped,
              src_transform=mosaic_tf, src_crs=crs_,
              dst_transform=clip_tf,  dst_crs=crs_,
              resampling=Resampling.nearest)
    profile = {"driver": "GTiff", "dtype": dtype, "crs": crs_,
               "width": new_w, "height": new_h, "transform": clip_tf,
               "count": 1, "nodata": nd_, "compress": "lzw"}
    with rasterio.open(DEM_MRG, "w", **profile) as dst:
        dst.write(clipped)
    print(f"  Written: {DEM_MRG.name}")
else:
    print(f"  Already exists: {DEM_MRG.name}")

if not SLP_TIF.exists():
    print("  Computing slope from merged DEM...")
    with rasterio.open(DEM_MRG) as src:
        elev = src.read(1).astype(float)
        nd_  = src.nodata if src.nodata is not None else -32768
        elev[elev == nd_] = np.nan
        res_m = abs(src.transform.a) * 111320
        prof  = src.profile.copy()
    dy, dx = np.gradient(elev, res_m, res_m)
    slope  = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
    slope  = np.where(np.isnan(slope), -9999.0, slope).astype(np.float32)
    prof.update({"dtype": "float32", "nodata": -9999.0, "compress": "lzw"})
    with rasterio.open(SLP_TIF, "w", **prof) as dst:
        dst.write(slope, 1)
    print(f"  Written: {SLP_TIF.name}")
else:
    print(f"  Already exists: {SLP_TIF.name}")

# ── Raster sampling at centroids ─────────────────────────────────────────────
print("\n── S2: Raster sampling ──")

# GHI (daily kWh/m²/day × 365 → annual kWh/m²/yr)
ghi_raw = sample_raster(GHI_TIF, xs, ys, nodata_val=np.nan)
ghi     = ghi_raw * 365.0
n_nan_ghi = np.isnan(ghi).sum()
print(f"  GHI: {np.nanmin(ghi):.0f}–{np.nanmax(ghi):.0f} kWh/m²/yr  "
      f"mean={np.nanmean(ghi):.0f}  NaN={n_nan_ghi}")
if n_nan_ghi > 0:
    print(f"  WARNING: {n_nan_ghi} GHI NaN — filling median")
    ghi = np.where(np.isnan(ghi), np.nanmedian(ghi), ghi)

# WindVel (m/s at 100m)
wind = sample_raster(WIND_TIF, xs, ys, nodata_val=np.nan)
n_nan_wind = np.isnan(wind).sum()
print(f"  WindVel: {np.nanmin(wind):.2f}–{np.nanmax(wind):.2f} m/s  "
      f"mean={np.nanmean(wind):.2f}  NaN={n_nan_wind}")
if n_nan_wind > 0:
    wind = np.where(np.isnan(wind), np.nanmedian(wind), wind)

# WindCF: OnSSET approximate capacity factor from wind speed at hub height
# Formula: max(0, 0.087*v - 0.5) — linear interpolation of generic power curve
wind_cf = np.maximum(0.0, 0.087 * wind - 0.5)
print(f"  WindCF:  {wind_cf.min():.4f}–{wind_cf.max():.4f}  mean={wind_cf.mean():.4f}")

# NightLights (nW/cm²/sr)
ntl = sample_raster(NTL_TIF, xs, ys, nodata_val=0.0)
print(f"  NightLights: {ntl.min():.4f}–{ntl.max():.4f}  mean={ntl.mean():.5f}")

# TravelHours (minutes → hours)
ttm_raw = sample_raster(TTM_TIF, xs, ys, nodata_val=np.nan)
trav    = ttm_raw / 60.0
n_nan_ttm = np.isnan(trav).sum()
print(f"  TravelHours: {np.nanmin(trav):.2f}–{np.nanmax(trav):.2f} hrs  "
      f"mean={np.nanmean(trav):.2f}  NaN={n_nan_ttm}")
if n_nan_ttm > 0:
    trav = np.where(np.isnan(trav), np.nanmedian(trav), trav)

# Elevation (m)
elev_s = sample_raster(DEM_MRG, xs, ys, nodata_val=0.0)
print(f"  Elevation: {elev_s.min():.0f}–{elev_s.max():.0f} m  mean={elev_s.mean():.0f}")

# Slope (degrees)
slope_s = sample_raster(SLP_TIF, xs, ys, nodata_val=0.0)
slope_s = np.where(slope_s < 0, 0.0, slope_s)
print(f"  Slope: {slope_s.min():.2f}–{slope_s.max():.2f}°  mean={slope_s.mean():.2f}")

# LandCover: no Copernicus layer available for Zambia; set to 0 and shared across arms
land_cover = np.zeros(len(xs))
print("  LandCover: set to 0 [Copernicus LC not acquired]")

# GridPenalty — set to 1 (no terrain-adjusted penalty layer available)
grid_penalty = np.ones(len(xs))
print("  GridPenalty: set to 1 (no penalty layer — standard default)")

# ── Grid distances (UTM 35S) ─────────────────────────────────────────────────
print("\n── S3: Grid distances (all in EPSG:32735, output km) ──")

# ── S3.1: CurrentHVLineDist — World Bank transmission network ─────────────
print("\n  [3.1] CurrentHVLineDist — WB transmission (HV polylines)")
hv_gdf = gpd.read_file(str(HV_SHP)).to_crs(UTM)
hv_gdf = hv_gdf[hv_gdf.geometry.notna() & hv_gdf.geometry.is_valid]
print(f"    Loaded {len(hv_gdf)} HV features → densifying at 500 m...")
hv_pts  = densify_lines(hv_gdf, spacing_m=500)
hv_dist = nn_dist_km(sett_xy, hv_pts)
hv_stats = dist_stats(hv_dist, "CurrentHVLineDist")

# ── S3.2: CurrentMVLineDist — ZESCO (primary) + OSM MV + FB predictive ───
# Source A: ZESCO MV (Arc 1950 / UTM 35S → datum-transform to EPSG:32735)
print("\n  [3.2a] ZESCO MV — loading and datum-transforming Arc 1950 → EPSG:32735")
zesco_raw = gpd.read_file(str(MV_ZESCO_SHP))
print(f"    Source CRS: {zesco_raw.crs.name}")
zesco_utm = zesco_raw.to_crs(UTM)   # PROJ applies proper Helmert datum shift
zesco_utm = zesco_utm[zesco_utm.geometry.notna() & zesco_utm.geometry.is_valid]
# Sanity: confirm WGS84 bounds are within Zambia
zesco_wgs84 = zesco_utm.to_crs("EPSG:4326")
wgs_bounds = zesco_wgs84.total_bounds
print(f"    Post-transform WGS84 bounds: "
      f"lon {wgs_bounds[0]:.3f}–{wgs_bounds[2]:.3f}  "
      f"lat {wgs_bounds[1]:.3f}–{wgs_bounds[3]:.3f}")
zambia_ok = (21.0 < wgs_bounds[0] < 25.0 and
             31.0 < wgs_bounds[2] < 35.0 and
             -20.0 < wgs_bounds[1] < -10.0 and
             -6.0  < wgs_bounds[3] < -6.0)
# Use broader check: bounds should be in Zambia region
in_zambia = (wgs_bounds[0] > 20 and wgs_bounds[2] < 36 and
             wgs_bounds[1] > -20 and wgs_bounds[3] < -7)
print(f"    Datum transform check: bounds within Zambia = {in_zambia}")
if not in_zambia:
    print("    *** DATUM TRANSFORM FAILED — bounds outside Zambia ***")
    raise RuntimeError("ZESCO datum transform produced coordinates outside Zambia")

print(f"    Densifying {len(zesco_utm):,} ZESCO segments at 500 m...")
zesco_pts   = densify_lines(zesco_utm, spacing_m=500)
print(f"    Densified to {len(zesco_pts):,} sample points")
zesco_dist  = nn_dist_km(sett_xy, zesco_pts)
print(f"    ZESCO MV distances:")
_ = dist_stats(zesco_dist, "  ZESCO_MV_dist")

# Source B: OSM power lines classified as MV
print("\n  [3.2b] OSM MV lines — loading from PBF")
lines_raw = pyogrio.read_dataframe(
    str(ROADS_PBF), layer='lines',
    columns=['osm_id', 'highway', 'other_tags', 'geometry']
)
tags_all = lines_raw['other_tags'].apply(parse_hstore)
lines_raw['power']   = tags_all.apply(lambda d: d.get('power', ''))
lines_raw['voltage'] = tags_all.apply(lambda d: d.get('voltage', ''))

pwr = lines_raw[lines_raw['power'].isin(['line', 'minor_line'])].copy().to_crs(UTM)
pwr['length_km'] = pwr.geometry.length / 1000.0

def classify_power(row):
    if row['power'] == 'minor_line':
        return 'MV'
    v = row['voltage']
    if isinstance(v, str) and v:
        try:
            kv = int(v.split(';')[0])
            return 'HV' if kv >= 66000 else 'MV'
        except ValueError:
            pass
    return 'HV' if row['length_km'] >= 5.0 else 'MV'

pwr['cls'] = pwr.apply(classify_power, axis=1)
osm_mv  = pwr[pwr['cls'] == 'MV']
osm_hv  = pwr[pwr['cls'] == 'HV']
print(f"    OSM MV features: {len(osm_mv)}  OSM HV features: {len(osm_hv)}")
print(f"    Densifying OSM MV at 500 m...")
osm_mv_pts  = densify_lines(osm_mv, spacing_m=500)
osm_mv_dist = nn_dist_km(sett_xy, osm_mv_pts)

# Source C: Facebook/Meta predictive MV (point cloud)
print("\n  [3.2c] FB predictive MV grid")
mv_fb_df  = pd.read_csv(MV_FB_CSV)
mv_fb_gdf = gpd.GeoDataFrame(
    mv_fb_df, geometry=gpd.points_from_xy(mv_fb_df["lon"], mv_fb_df["lat"]),
    crs="EPSG:4326"
).to_crs(UTM)
fb_xy    = np.column_stack([mv_fb_gdf.geometry.x, mv_fb_gdf.geometry.y])
fb_dist  = nn_dist_km(sett_xy, fb_xy)
print(f"    FB predictive MV points: {len(fb_xy):,}")

# Combine: take minimum distance across all three MV sources
# ZESCO is primary/most authoritative; others improve coverage in its gaps
mv_dist = np.minimum(np.minimum(zesco_dist, osm_mv_dist), fb_dist)
print(f"\n  [3.2d] CurrentMVLineDist (min of ZESCO, OSM-MV, FB-predictive):")
mv_stats = dist_stats(mv_dist, "CurrentMVLineDist")

# Datum transform sanity: compare ZESCO vs HV transmission for a sample
# In the corridor near transmission lines, MV should be roughly comparable
sample_near_hv = hv_dist < 5.0   # settlements within 5 km of HV line
n_sample = sample_near_hv.sum()
if n_sample > 0:
    zesco_near_hv = zesco_dist[sample_near_hv]
    print(f"\n  [Datum-transform check] Settlements within 5 km of HV ({n_sample:,}):")
    print(f"    ZESCO MV dist: mean={zesco_near_hv.mean():.2f} km  "
          f"median={np.median(zesco_near_hv):.2f} km")
    print(f"    (Expected: ZESCO MV often parallels HV corridors, so median "
          f"should be < 20 km in this subsample — not a constant offset ~300 m)")

# ── S3.3: PlannedMVLineDist — NEP planned extensions ─────────────────────
# NOTE: The NEP extensions are the adopted national plan; they are also a
# shared input into the OnSSET base-case arm, creating mild circularity, but
# this is the same as the nationally published plan.
print("\n  [3.3] PlannedMVLineDist — NEP planned MV extensions")
nep_gdf  = gpd.read_file(str(NEP_MV_GEO)).to_crs(UTM)
nep_gdf  = nep_gdf[nep_gdf.geometry.notna() & nep_gdf.geometry.is_valid]
print(f"    NEP features: {len(nep_gdf)} (51 LineStrings, NEP least-cost-derived plan)")
print(f"    Note: mild circularity — NEP plan is a shared input across OnSSET arms")
nep_pts  = densify_lines(nep_gdf, spacing_m=500)
nep_dist = nn_dist_km(sett_xy, nep_pts)
nep_stats = dist_stats(nep_dist, "PlannedMVLineDist")

# ── S3.4: PlannedHVLineDist — proxy ─────────────────────────────────────
# No planned HV layer acquired. Use CurrentHVLineDist as a conservative proxy
# (no new HV planned → distance remains same as current).
planned_hv_dist = hv_dist.copy()
print("\n  [3.4] PlannedHVLineDist: proxy = CurrentHVLineDist "
      "(no planned HV layer available — conservative)")

# ── S3.5: TransformerDist — MV + MVLV distribution transformers ──────────
print("\n  [3.5] TransformerDist — MV + MVLV distribution transformers")
tx_mv_gdf   = gpd.read_file(str(TX_MV_SHP)).to_crs(UTM)
tx_mvlv_gdf = gpd.read_file(str(TX_MVLV_SHP)).to_crs(UTM)
tx_mv_gdf   = tx_mv_gdf  [tx_mv_gdf.geometry.notna()   & tx_mv_gdf.geometry.is_valid]
tx_mvlv_gdf = tx_mvlv_gdf[tx_mvlv_gdf.geometry.notna() & tx_mvlv_gdf.geometry.is_valid]
tx_xy = np.vstack([
    np.column_stack([tx_mv_gdf.geometry.x,   tx_mv_gdf.geometry.y]),
    np.column_stack([tx_mvlv_gdf.geometry.x, tx_mvlv_gdf.geometry.y]),
])
print(f"    MV transformers: {len(tx_mv_gdf):,}   MVLV transformers: {len(tx_mvlv_gdf):,}  "
      f"→ combined: {len(tx_xy):,}")
tx_dist  = nn_dist_km(sett_xy, tx_xy)
tx_stats = dist_stats(tx_dist, "TransformerDist")
print(f"    Reference: 1 km spine had 30,766 settlements <2 km of transformer")

# ── S3.6: SubstationDist — Distribution + HVMV + MVLV substations ────────
print("\n  [3.6] SubstationDist — all ZESCO substation tiers")
sub_dist_gdf = gpd.read_file(str(SUB_DIST_SHP)).to_crs(UTM)
sub_hvmv_gdf = gpd.read_file(str(SUB_HVMV_SHP)).to_crs(UTM)
sub_mvlv_gdf = gpd.read_file(str(SUB_MVLV_SHP)).to_crs(UTM)
for g in [sub_dist_gdf, sub_hvmv_gdf, sub_mvlv_gdf]:
    g = g[g.geometry.notna() & g.geometry.is_valid]
sub_xy = np.vstack([
    np.column_stack([sub_dist_gdf.geometry.x, sub_dist_gdf.geometry.y]),
    np.column_stack([sub_hvmv_gdf.geometry.x, sub_hvmv_gdf.geometry.y]),
    np.column_stack([sub_mvlv_gdf.geometry.x, sub_mvlv_gdf.geometry.y]),
])
print(f"    Distribution: {len(sub_dist_gdf):,}  HVMV: {len(sub_hvmv_gdf):,}  "
      f"MVLV: {len(sub_mvlv_gdf):,}  → combined: {len(sub_xy):,}")
sub_dist  = nn_dist_km(sett_xy, sub_xy)
sub_stats = dist_stats(sub_dist, "SubstationDist")

# ── Vector distances: roads and hydropower ───────────────────────────────────
print("\n── S4: Roads and hydropower distances ──")

# ── S4.1: RoadDist — OSM primary/secondary/tertiary/unclassified ──────────
print("\n  [4.1] RoadDist — OSM roads")
ROAD_TAGS = {'primary', 'secondary', 'tertiary', 'unclassified'}
roads = lines_raw[lines_raw['highway'].isin(ROAD_TAGS)].copy().to_crs(UTM)
print(f"    Road segments: {len(roads):,}")
rd_pts  = densify_lines(roads, spacing_m=500)
rd_dist = nn_dist_km(sett_xy, rd_pts)
_ = dist_stats(rd_dist, "RoadDist")

# ── S4.2: HydropowerDist + Hydropower ─────────────────────────────────────
print("\n  [4.2] HydropowerDist + Hydropower (nearest plant)")
hydro_df  = pd.read_csv(HYDRO_CSV)
hydro_gdf = gpd.GeoDataFrame(
    hydro_df,
    geometry=gpd.points_from_xy(hydro_df["longitude"], hydro_df["latitude"]),
    crs="EPSG:4326"
).to_crs(UTM)
hydro_pts = np.column_stack([hydro_gdf.geometry.x, hydro_gdf.geometry.y])
tree_h    = cKDTree(hydro_pts)
h_dists_m, h_idxs = tree_h.query(sett_xy, workers=-1)
hydro_dist = h_dists_m / 1000.0
hydro_cap  = hydro_gdf["capacity_mw"].values[h_idxs] * 1000  # MW → kW
hydro_fid  = h_idxs.astype(int)
print(f"    Hydro plants: {len(hydro_gdf)}")
print(f"    HydropowerDist: {hydro_dist.min():.1f}–{hydro_dist.max():.1f} km  "
      f"mean={hydro_dist.mean():.1f}")
print(f"    Hydropower: {hydro_cap.min():.0f}–{hydro_cap.max():.0f} kW")

# ── Assemble the output CSV (OnSSET schema + spine columns) ───────────
print("\n── S5: Assembling Stage 2 CSV ──")

n = len(spine)
ZERO = np.zeros(n)

df = pd.DataFrame({
    # ── Spatial identity (from s02) ──────────────────────────────────
    "X_deg":        xs,
    "Y_deg":        ys,
    "Pop":          spine["Pop"].values,
    "GridCellArea": spine["GridCellArea"].values,
    "Country":      "Zambia",
    "id":           spine["id"].values,
    # ── Stage-1b extra columns ─────────────────────────────────────────────
    "IsUrban":      spine["IsUrban"].values,
    "IsUrban_type": spine["IsUrban_type"].values,
    "Admin_1":      spine["Admin_1"].values,
    "building_count": spine["building_count"].values,
    "building_area":  spine["building_area"].values,
    "grid3_type":     spine["grid3_type"].values,
    "pop_density":    spine["pop_density"].values,
    "source":         spine["source"].values,
    # ── Calibration placeholders (filled by s04) ──────────────────────
    "ElecPop":      ZERO,
    "ElecPopCalib": ZERO,
    "ElecStart":    ZERO,
    "GridDistCalibElec": ZERO,
    "FinalElecCode2020": ZERO,
    "ElecPop2020":  ZERO,
    "PopStartYear": ZERO,
    # ── Resource rasters ──────────────────────────────────────────────────
    "GHI":          ghi,
    "WindVel":      wind,
    "WindCF":       wind_cf,
    "NightLights":  ntl,
    # ── Accessibility & terrain ───────────────────────────────────────────
    "TravelHours":  trav,
    "Elevation":    elev_s,
    "Slope":        slope_s,
    # ── Land cover / penalty ──────────────────────────────────────────────
    "LandCover":    land_cover,     # 0 — Copernicus not acquired
    "GridPenalty":  grid_penalty,   # 1 — no terrain-penalty layer
    # ── Grid distances ────────────────────────────────────────────────────
    "CurrentHVLineDist":  hv_dist,
    "PlannedHVLineDist":  planned_hv_dist,  # proxy = CurrentHVLineDist
    "CurrentMVLineDist":  mv_dist,
    "PlannedMVLineDist":  nep_dist,
    "SubstationDist":     sub_dist,
    "TransformerDist":    tx_dist,
    "RoadDist":           rd_dist,
    # ── Hydropower ────────────────────────────────────────────────────────
    "HydropowerDist": hydro_dist,
    "Hydropower":     hydro_cap,
    "HydropowerFID":  hydro_fid,
    # ── Mini-grid sentinel ────────────────────────────────────────────────
    "MGDist":       9999.0,
    # ── Conflict (no conflict layer acquired) ─────────────────────────────
    "Conflict":     ZERO,
    # ── Demand placeholders (filled by s04) ───────────────────────────
    "ElectrificationOrder":       ZERO,
    "ResidentialDemandTierCustom": ZERO,
    "PerCapitaDemand":            ZERO,
    "HealthDemand":               ZERO,
    "EducationDemand":            ZERO,
    "AgriDemand":                 ZERO,
    "CommercialDemand":           ZERO,
    "ResidentialDemandTier1":     ZERO,
    "ResidentialDemandTier2":     ZERO,
    "ResidentialDemandTier3":     ZERO,
    "ResidentialDemandTier4":     ZERO,
    "ResidentialDemandTier5":     ZERO,
})

# Column order: OnSSET core schema first, then Stage-1b extras
COL_ORDER = [
    "X_deg", "Y_deg", "Pop", "GridCellArea", "Country",
    "ElecPop", "WindVel", "WindCF", "GHI", "TravelHours",
    "Elevation", "ResidentialDemandTierCustom", "Slope", "NightLights",
    "LandCover", "GridPenalty",
    "SubstationDist", "TransformerDist",
    "CurrentHVLineDist", "PlannedHVLineDist",
    "CurrentMVLineDist", "PlannedMVLineDist",
    "RoadDist", "HydropowerDist", "Hydropower", "HydropowerFID",
    "IsUrban", "PerCapitaDemand", "HealthDemand", "EducationDemand",
    "AgriDemand", "ElectrificationOrder", "CommercialDemand",
    "ResidentialDemandTier1", "ResidentialDemandTier2",
    "ResidentialDemandTier3", "ResidentialDemandTier4", "ResidentialDemandTier5",
    "id", "Conflict", "Admin_1", "MGDist",
    "ElecPopCalib", "ElecStart", "GridDistCalibElec",
    "FinalElecCode2020", "ElecPop2020", "PopStartYear",
    # Stage-1b extras
    "IsUrban_type", "building_count", "building_area",
    "grid3_type", "pop_density", "source",
]
df = df[COL_ORDER]

df.to_csv(OUT_CSV, index=False)
print(f"  Written: {OUT_CSV.name}   ({len(df):,} rows × {len(df.columns)} cols)")

print("  Writing GeoPackage...")
gdf_out = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df["X_deg"], df["Y_deg"]),
    crs="EPSG:4326"
)
gdf_out.to_file(str(OUT_GPKG), driver="GPKG", layer="stage2")
print(f"  Written: {OUT_GPKG.name}")

# ── Verification gate ────────────────────────────────────────────────────────
print("\n── S6: Verification gate ──")

# Optional cross-check against the earlier 1 km spine, if one is present.
REF_1KM_PATH = ROOT / "data/processed/zambia_settlements.csv"

print(f"\n(a) Row count: {len(df):,}   (expected 270,526)")

if REF_1KM_PATH.exists():
    ref_cols    = set(pd.read_csv(REF_1KM_PATH, nrows=0).columns)
    stage2_cols = set(df.columns)
    print(f"\n(b) Column set vs 1 km spine:")
    print(f"    In 1km spine but not Stage 2: {sorted(ref_cols - stage2_cols) or 'none'}")
    print(f"    In Stage 2 but not 1km spine: {sorted(stage2_cols - ref_cols) or 'none'}")
else:
    print(f"\n(b) Column set vs 1 km spine: skipped (no 1 km spine present)")

print(f"\n(c) NaN / inf check in spatial columns:")
crit = ["GHI", "WindVel", "TravelHours", "Elevation", "Slope",
        "CurrentHVLineDist", "CurrentMVLineDist", "PlannedMVLineDist",
        "SubstationDist", "TransformerDist", "RoadDist",
        "HydropowerDist", "NightLights"]
all_ok = True
for c in crit:
    n_nan = df[c].isna().sum()
    n_inf = np.isinf(df[c].values).sum()
    n_neg = (df[c].values < 0).sum()
    status = "OK" if (n_nan == 0 and n_inf == 0 and n_neg == 0) else "*** FAIL"
    print(f"    {c:<24}: NaN={n_nan}  inf={n_inf}  neg={n_neg}  {status}")
    if status != "OK":
        all_ok = False
print(f"    → Overall: {'ALL PASS' if all_ok else 'FAILURES ABOVE'}")
if not all_ok:
    # HARD GATE (2026-08-16): previously this verdict was print-only, so a NaN or negative
    # in a resource column produced output files indistinguishable from a good run.
    raise SystemExit("s03 attribute gate FAILED - see the FAIL rows above; output not trustworthy")

print(f"\n(d) Sanity ranges:")
print(f"    GHI:           {df.GHI.min():.0f}–{df.GHI.max():.0f} kWh/m²/yr   (expected 1,700–2,200)")
print(f"    WindVel:       {df.WindVel.min():.2f}–{df.WindVel.max():.2f} m/s")
print(f"    TravelHours:   {df.TravelHours.min():.2f}–{df.TravelHours.max():.2f} hrs")
print(f"    Elevation:     {df.Elevation.min():.0f}–{df.Elevation.max():.0f} m")
print(f"    Slope:         {df.Slope.min():.1f}–{df.Slope.max():.1f}° (expected ≥0)")
print(f"    NightLights:   {df.NightLights.min():.4f}–{df.NightLights.max():.4f}")
print(f"    Pop total:     {df.Pop.sum():,.0f}   (expected ~18.4 M)")
print(f"    X_deg range:   {df.X_deg.min():.3f}–{df.X_deg.max():.3f}   (Zambia: 21.9–33.8)")
print(f"    Y_deg range:   {df.Y_deg.min():.3f}–{df.Y_deg.max():.3f}   (Zambia: -18.1–-8.1)")

print(f"\n(e) CurrentMVLineDist — realism check vs 1 km spine:")
n_mv_2km   = (df.CurrentMVLineDist < 2.0).sum()
n_mv_2km_pct = 100 * n_mv_2km / len(df)
print(f"    Settlements within 2 km of MV: {n_mv_2km:,}  ({n_mv_2km_pct:.1f}%)")
print(f"    ZESCO-only contribution <2 km: {(zesco_dist < 2.0).sum():,}")
print(f"    (Reference 1 km spine: check compute_grid_distances.py run logs)")

print(f"\n(f) TransformerDist check:")
n_tx_2km = (df.TransformerDist < 2.0).sum()
print(f"    Settlements within 2 km of transformer: {n_tx_2km:,}")
print(f"    (Reference 1 km spine: 30,766 after dense transformer addition)")

print(f"\n(g) PlannedMVLineDist — NEP plan:")
n_plan_2km = (df.PlannedMVLineDist < 2.0).sum()
n_plan_5km = (df.PlannedMVLineDist < 5.0).sum()
print(f"    Settlements within 2 km of NEP planned MV: {n_plan_2km:,}")
print(f"    Settlements within 5 km of NEP planned MV: {n_plan_5km:,}")
print(f"    (51 NEP extension lines — these cover targeted rural corridors)")

print(f"\n(h) PlannedHVLineDist: proxy = CurrentHVLineDist — no new HV planned "
      f"[confirm with ZESCO expansion plans]")

elapsed = time.time() - t0
print(f"\n── Stage 2 complete in {elapsed:.0f} s ──")
print(f"   Output: {OUT_CSV}")
print(f"   Output: {OUT_GPKG}")
