"""
s05_compute_peak_ratios.py — the demand pre-processor: per-settlement P/E.

Reads  : data/processed/zambia_grid3_calib_distgate.csv  (270,526 rows)
Writes : data/processed/zambia_grid3_spine_pe_n10.csv
         data/processed/zambia_grid3_spine_pe_n20.csv   (central case — used for R1)
         data/processed/zambia_grid3_spine_pe_n50.csv

Each output is identical to the input except for two added columns:
  N_hh     = max(1, Pop / HH_size)   (ZamStats 2022: urban 4.6, rural 5.0)
  PE_ratio  = pe_from_n(N_hh, N_mid=N_MID)

IsUrban > 1 is used for urban (standard OnSSET convention; after calibrate_current_pop_and_urban
IsUrban ∈ {0, 2}). IsUrban_type is NOT used (inconsistent — 57 urban rows carry type 0).

Admin_1 = 'Zambia' border slivers (135 settlements, 0.047% of pop) are reassigned to
the nearest province by centroid (Euclidean distance on X_deg/Y_deg).
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

sys.path.insert(0, str(REPO / "peak_preprocessor"))
from pe_diversity import pe_from_n, compute_beta

SPINE_IN   = REPO / "data" / "processed" / "zambia_grid3_calib_distgate.csv"
OUT_N10    = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n10.csv"
OUT_N20    = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"
OUT_N50    = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n50.csv"

HH_URBAN   = 4.6   # ZamStats 2022 Census, Section 4.3
HH_RURAL   = 5.0   # ZamStats 2022 Census, Section 4.3
N_MID_VALS = [10, 20, 50]
OUT_PATHS  = {10: OUT_N10, 20: OUT_N20, 50: OUT_N50}


def reassign_border_slivers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reassign settlements with Admin_1 = 'Zambia' (border slivers) to the nearest
    province by Euclidean distance on X_deg / Y_deg centroids.
    """
    known = df[df["Admin_1"] != "Zambia"]
    slivers = df["Admin_1"] == "Zambia"
    n_slivers = slivers.sum()
    if n_slivers == 0:
        return df

    # Province centroids from known settlements
    centroids = known.groupby("Admin_1")[["X_deg", "Y_deg"]].mean()
    prov_names = centroids.index.tolist()
    cx = centroids["X_deg"].values
    cy = centroids["Y_deg"].values

    sx = df.loc[slivers, "X_deg"].values
    sy = df.loc[slivers, "Y_deg"].values

    assigned = []
    for x, y in zip(sx, sy):
        dists = np.sqrt((cx - x) ** 2 + (cy - y) ** 2)
        assigned.append(prov_names[int(np.argmin(dists))])

    df = df.copy()
    df.loc[slivers, "Admin_1"] = assigned
    print(f"  Reassigned {n_slivers:,} border slivers (Admin_1='Zambia') to nearest province.")
    from collections import Counter
    print(f"  Reassigned to: {dict(Counter(assigned))}")
    return df


def main():
    print("=" * 65)
    print("  s05 — demand pre-processor (per-settlement P/E)")
    print("=" * 65)

    print(f"\nReading spine: {SPINE_IN.name}")
    df = pd.read_csv(SPINE_IN)
    print(f"  {len(df):,} rows × {len(df.columns)} columns")
    print(f"  IsUrban unique: {sorted(df['IsUrban'].unique())}")
    print(f"  Admin_1='Zambia' slivers: {(df['Admin_1'] == 'Zambia').sum():,}")

    # Drop IsUrban_type to prevent downstream confusion
    if "IsUrban_type" in df.columns:
        df = df.drop(columns=["IsUrban_type"])
        print(f"  Dropped IsUrban_type (inconsistent legacy column).")

    # Reassign border slivers
    df = reassign_border_slivers(df)
    print(f"  Admin_1 unique after reassignment: {sorted(df['Admin_1'].unique())}")

    # Compute N_hh (urban = IsUrban > 1, consistent with onsset convention)
    is_urban  = df["IsUrban"] > 1
    hh_size   = np.where(is_urban, HH_URBAN, HH_RURAL)
    N_raw     = df["Pop"].values / hh_size
    N_hh      = np.maximum(N_raw, 1.0)
    n_clipped = int((N_raw < 1.0).sum())
    df["N_hh"] = N_hh

    print(f"\n  Household sizes: urban={HH_URBAN}, rural={HH_RURAL}")
    print(f"  N_hh < 1 (clipped to 1): {n_clipped:,}")
    print(f"  N_hh range: [{N_hh.min():.1f}, {N_hh.max():.1f}]")
    print(f"  N_hh urban median: {np.median(N_hh[is_urban.values]):.1f}")
    print(f"  N_hh rural median: {np.median(N_hh[~is_urban.values]):.1f}")

    for n_mid in N_MID_VALS:
        beta = compute_beta(n_mid)
        pe   = pe_from_n(N_hh, N_mid=n_mid)
        df_out = df.copy()
        df_out["PE_ratio"] = pe
        out_path = OUT_PATHS[n_mid]
        df_out.to_csv(str(out_path), index=False)
        print(f"\n  N_mid={n_mid:2d}, beta={beta:.4f}: "
              f"PE range [{pe.min():.4f}, {pe.max():.4f}], "
              f"median={np.median(pe):.4f}, mean={pe.mean():.4f}")
        print(f"  → {out_path.name}  ({out_path.stat().st_size/1e6:.1f} MB)")

    print(f"\nDone. R1 central case: {OUT_N20.name}")


if __name__ == "__main__":
    main()
