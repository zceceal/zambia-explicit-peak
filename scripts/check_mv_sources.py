#!/usr/bin/env python3
"""
check_mv_sources.py — which layer sets each settlement's medium-voltage distance.

s03 stores CurrentMVLineDist as the minimum of three distances (ZESCO record, OpenStreetMap
power lines, Meta predictive grid) without keeping the components. This script recomputes the
ZESCO and Meta distances from the raw layers with s03's method, attributes the residual to
OpenStreetMap, and writes the shares and the 2 km / 10 km counts the paper quotes (§2.3.2, S6).

    python scripts/check_mv_sources.py
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[1]
SPINE = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"
ZESCO = (REPO / "data/raw/zambia/grid/mv_distribution_2023"
         "/distribution_medium_voltage_overhead_line_network"
         "/Distribution_Medium_Voltage_Overhead_Line_Network.shp")
META = REPO / "data/raw/zambia/grid/mv_predictive_fb/electrical_grid_zambia_15.csv"
OUT = REPO / "results" / "summary" / "2026-09-02_mv_distance_sources.csv"
UTM = "EPSG:32735"
TOL_KM = 0.001


def densify_lines(gdf_utm, spacing_m=500):
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
    return np.array(coords)


def nn_dist_km(pts_xy, ref_xy):
    return cKDTree(ref_xy).query(pts_xy, workers=-1)[0] / 1000.0


def main():
    sp = pd.read_csv(SPINE, usecols=["id", "X_deg", "Y_deg", "Pop", "NightLights",
                                     "TransformerDist", "CurrentMVLineDist"])
    pts = gpd.GeoDataFrame(sp, geometry=gpd.points_from_xy(sp.X_deg, sp.Y_deg),
                           crs="EPSG:4326").to_crs(UTM)
    xy = np.column_stack([pts.geometry.x, pts.geometry.y])

    zesco = gpd.read_file(str(ZESCO)).to_crs(UTM)
    zesco = zesco[zesco.geometry.notna() & zesco.geometry.is_valid]
    d_zesco = nn_dist_km(xy, densify_lines(zesco))

    meta = pd.read_csv(META)
    meta = gpd.GeoDataFrame(meta, geometry=gpd.points_from_xy(meta.lon, meta.lat),
                            crs="EPSG:4326").to_crs(UTM)
    d_meta = nn_dist_km(xy, np.column_stack([meta.geometry.x, meta.geometry.y]))

    blend = sp.CurrentMVLineDist.to_numpy()
    osm = blend < np.minimum(d_zesco, d_meta) - TOL_KM
    meta_wins = ~osm & (d_meta < d_zesco - TOL_KM)
    zesco_wins = ~osm & ~meta_wins
    pop = sp.Pop.to_numpy()
    lit = sp.NightLights.to_numpy() > 0
    tx2 = sp.TransformerDist.to_numpy() < 2

    rows = []
    for name, mask in [("zesco", zesco_wins), ("meta", meta_wins), ("osm", osm)]:
        rows.append({"metric": f"settlements_set_by_{name}", "value": int(mask.sum()),
                     "share_settlements": mask.mean(), "share_population": pop[mask].sum() / pop.sum()})
    for name, d in [("zesco_only", d_zesco), ("as_run", blend)]:
        rows += [
            {"metric": f"{name}_within_2km_mv", "value": int((d < 2).sum())},
            {"metric": f"{name}_within_2km_transformer_or_mv", "value": int((tx2 | (d < 2)).sum())},
            {"metric": f"{name}_lit_within_2km_mv_not_transformer", "value": int((lit & (d < 2) & ~tx2).sum())},
            {"metric": f"{name}_within_10km_mv", "value": int((d < 10).sum())},
            {"metric": f"{name}_median_mv_km", "value": float(np.median(d))},
        ]
    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(out.to_string(index=False))
    print(f"\nwrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
