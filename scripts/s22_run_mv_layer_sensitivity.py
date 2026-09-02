#!/usr/bin/env python3
"""
s22_run_mv_layer_sensitivity.py — the explicit-peak result on the ZESCO record alone.

WHY
---
s03 sets CurrentMVLineDist to the minimum over three layers: the ZESCO record, OpenStreetMap
power lines and the Meta predictive grid. The predicted layer is the closer one for 65% of
settlements (check_mv_sources.py). The base-year calibration does not read that column (it uses
the transformer gate), but the solve does: the maximum-extension test, the T&D length in
grid-extension cost, the mini-grid exclusion radius and the extension order. This re-solves both
arms with the ZESCO record as the only MV layer.

DESIGN
------
  * The published N_mid = 20 spine, with CurrentMVLineDist replaced by the ZESCO-only distance
    (recomputed from the shapefile with s03's method); every other column unchanged.
  * Both arms, config.yaml untouched. The as-run row is read from the canonical
    2026-08_final_lcoe outputs, not re-run.

    python scripts/s22_run_mv_layer_sensitivity.py --self-test   # runs no arm
    python scripts/s22_run_mv_layer_sensitivity.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(REPO / "peak_preprocessor"))
sys.path.insert(0, str(HERE))

OUTDIR      = REPO / "data" / "onsset_outputs"
SUMDIR      = REPO / "results" / "summary"
RUN_LABEL   = "2026-09-02_mvzesco"
SUMMARY_CSV = SUMDIR / "2026-09-02_mv_layer_sensitivity.csv"
SOURCES_CSV = SUMDIR / "2026-09-02_mv_distance_sources.csv"

YEAR  = 2030
N_MID = 20
R0_CENTRAL = OUTDIR / "2026-08_final_lcoe_R0.csv"
R1_CENTRAL = OUTDIR / f"2026-08_final_lcoe_R1_n{N_MID}.csv"

METRIC_COLS = [f"MinimumOverallLCOE{YEAR}", f"EnergyPerSettlement{YEAR}",
               f"FinalElecCode{YEAR}", f"InvestmentCost{YEAR}", f"NewCapacity{YEAR}",
               f"Pop{YEAR}", "CurrentMVLineDist"]


def arm_paths() -> dict:
    return {"R0": OUTDIR / f"{RUN_LABEL}_R0.csv",
            "R1": OUTDIR / f"{RUN_LABEL}_R1_n{N_MID}.csv"}


def zesco_only_distance(spine: pd.DataFrame) -> np.ndarray:
    """Distance to the ZESCO record alone, by s03's densify-and-nearest-neighbour method."""
    import geopandas as gpd
    from check_mv_sources import ZESCO, UTM, densify_lines, nn_dist_km
    pts = gpd.GeoDataFrame(spine[["id"]], geometry=gpd.points_from_xy(spine.X_deg, spine.Y_deg),
                           crs="EPSG:4326").to_crs(UTM)
    xy = np.column_stack([pts.geometry.x, pts.geometry.y])
    zesco = gpd.read_file(str(ZESCO)).to_crs(UTM)
    zesco = zesco[zesco.geometry.notna() & zesco.geometry.is_valid]
    return nn_dist_km(xy, densify_lines(zesco))


def metrics(r0: pd.DataFrame, r1: pd.DataFrame) -> dict:
    """Same energy-weighted formula as s14/s18: both arms weighted by the R0 energy column."""
    lc, ec = f"MinimumOverallLCOE{YEAR}", f"EnergyPerSettlement{YEAR}"
    code, inv, cap, pop = (f"FinalElecCode{YEAR}", f"InvestmentCost{YEAR}",
                           f"NewCapacity{YEAR}", f"Pop{YEAR}")
    e = r0[ec].to_numpy()
    c0, c1 = (r0[lc].to_numpy() * e).sum(), (r1[lc].to_numpy() * e).sum()
    f0, f1 = r0[code].to_numpy(), r1[code].to_numpy()
    p = r0[pop].to_numpy()
    d = r0["CurrentMVLineDist"].to_numpy()
    return {"dlcoe_pct":           (c1 - c0) / c0 * 100.0,
            "lcoe_r0":             c0 / e.sum(),
            "lcoe_r1":             c1 / e.sum(),
            "switches_sapv_grid":  int(((f0 == 3) & (f1 == 1)).sum()),
            "switches_total":      int((f0 != f1).sum()),
            "d_investment_pct":    (r1[inv].sum() / r0[inv].sum() - 1.0) * 100.0,
            "d_capacity_pct":      (r1[cap].sum() / r0[cap].sum() - 1.0) * 100.0,
            "r0_grid_settlements": int((f0 == 1).sum()),
            "r1_grid_settlements": int((f1 == 1).sum()),
            "r0_grid_pop_share":   p[f0 == 1].sum() / p.sum(),
            "r1_grid_pop_share":   p[f1 == 1].sum() / p.sum(),
            "within_10km_mv":      int((d < 10).sum()),
            "median_mv_km":        float(np.median(d))}


def preflight() -> int:
    clash = [p for p in arm_paths().values() if p.exists()]
    if clash:
        print("REFUSING TO RUN — these output paths already exist:")
        for p in clash:
            print(f"    {p}")
        return 1
    from s06_run_arms import PE_N20
    for p in (PE_N20, R0_CENTRAL, R1_CENTRAL, SOURCES_CSV):
        if not p.exists():
            print(f"  missing input {p.name}" + ("  (run check_mv_sources.py)" if p == SOURCES_CSV else ""))
            return 1
    print("  output collision check: PASS; inputs present")
    return 0


def self_test() -> int:
    """
    Runs no arm. The ZESCO-only distance is never below the as-run minimum, and equals it on the
    settlements check_mv_sources.py attributes to ZESCO — the recomputation is s03's.
    """
    from s06_run_arms import PE_N20
    print("=" * 72)
    print("  s22 self-test — ZESCO-only distance against the as-run minimum (no arm is run)")
    print("=" * 72)
    spine = pd.read_csv(PE_N20, usecols=["id", "X_deg", "Y_deg", "CurrentMVLineDist"])
    zd = zesco_only_distance(spine)
    as_run = spine["CurrentMVLineDist"].to_numpy()
    never_below = bool(np.all(zd >= as_run - 1e-3))
    n_equal = int((zd - as_run <= 1e-3).sum())      # same rule as check_mv_sources.py
    src = pd.read_csv(SOURCES_CSV).set_index("metric")["value"]
    n_src = int(src["settlements_set_by_zesco"])
    print(f"  ZESCO-only >= as-run everywhere: {never_below}")
    print(f"  equal on {n_equal:,} settlements; check_mv_sources.py attributes {n_src:,} to ZESCO")
    ok = never_below and n_equal == n_src
    print("\n  " + ("SELF-TEST PASS" if ok else "SELF-TEST FAIL"))
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    from onsset_helpers import load_solar_profile, load_wind_profile, load_config
    from s06_run_arms import (run_arm, assert_base_cols_match, PE_N20, TX_SHP,
                              SOLAR_PROFILE, WIND_PROFILE)
    from onsset import SettlementProcessor
    print("=" * 72)
    print(f"  s22 — MV-layer sensitivity: ZESCO record only   (N_mid={N_MID}, {RUN_LABEL})")
    print("=" * 72)
    if preflight() != 0:
        return 1
    if self_test() != 0:
        print("self-test failed; refusing to run")
        return 1
    cfg = load_config()
    t_all = time.time()

    spine = pd.read_csv(PE_N20)
    spine["CurrentMVLineDist"] = zesco_only_distance(spine)
    df_r0 = spine.drop(columns=["PE_ratio", "N_hh"])
    df_r1 = df_r0.copy()
    df_r1["PE_ratio"] = spine["PE_ratio"].to_numpy()
    assert_base_cols_match(df_r0, df_r1, f"R1_n{N_MID}_mvzesco")
    print(f"\n  median MV distance: {np.median(spine['CurrentMVLineDist']):.2f} km (ZESCO only)")

    np.random.seed(42)
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    paths, pair = arm_paths(), {}
    for arm, frame, n_mid in (("R0", df_r0, None), ("R1", df_r1, N_MID)):
        proc, _, _ = run_arm(f"{arm}_mvzesco", frame, cfg, x_tx, y_tx,
                             ghi_profile, temp_profile, wind_profile, n_mid=n_mid)
        proc.df.sort_values("id", inplace=True)
        proc.df.to_csv(paths[arm], index=False)
        pair[arm] = proc.df[METRIC_COLS].reset_index(drop=True).copy()
        del proc

    rows = []
    m = metrics(pair["R0"], pair["R1"])
    m.update({"mv_layer": "ZESCO record only", "source": RUN_LABEL})
    rows.append(m)
    r0c = pd.read_csv(R0_CENTRAL, usecols=METRIC_COLS)
    r1c = pd.read_csv(R1_CENTRAL, usecols=METRIC_COLS)
    m = metrics(r0c, r1c)
    m.update({"mv_layer": "min of ZESCO, Meta, OSM (published)", "source": "2026-08_final_lcoe (canonical)"})
    rows.append(m)

    out = pd.DataFrame(rows)
    out.to_csv(SUMMARY_CSV, index=False)
    print("\n" + "=" * 72)
    print("  MV-LAYER SENSITIVITY — N_mid = 20, 2030 columns")
    print("=" * 72)
    print(out.set_index("mv_layer").T.to_string())
    print(f"\n  summary -> {SUMMARY_CSV}")
    print(f"  done in {(time.time() - t_all) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
