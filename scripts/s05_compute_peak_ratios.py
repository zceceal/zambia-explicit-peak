"""
s05_compute_peak_ratios.py — the demand pre-processor: per-settlement P/E.

Reads  : data/processed/zambia_grid3_calib_distgate.csv  (270,526 rows)
Writes : data/processed/zambia_grid3_spine_pe_n10.csv
         data/processed/zambia_grid3_spine_pe_n20.csv   (central case — used for R1)
         data/processed/zambia_grid3_spine_pe_n50.csv

Each output is identical to the input except for four added columns:
  Pop2030   = the engine's own projection of PopStartYear to the 2030 analysis year
              (SettlementProcessor.project_pop_and_urban, with the scenario block of
              config/config.yaml), so the household count sits on the same population as
              the energy it is paired with in the solve.
  N_hh      = max(1, Pop2030 / HH_size)   (household_size in config/config.yaml;
                                            ZamStats 2022: urban 4.6, rural 5.0)
  N_hh_2020 = max(1, Pop / HH_size)       kept for reference only; not used by the solve.
  PE_ratio  = pe_from_n(N_hh, N_mid=N_MID)

s06 asserts, after running the same projection itself, that its Pop2030 equals the one
written here on every settlement.

IsUrban > 1 is used for urban (standard OnSSET convention; after calibrate_current_pop_and_urban
IsUrban ∈ {0, 2}). IsUrban_type is NOT used (inconsistent — 57 urban rows carry type 0).

Admin_1 = 'Zambia' border slivers (135 settlements, 0.047% of pop) are reassigned to
the nearest province by centroid (Euclidean distance on X_deg/Y_deg).
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(REPO / "peak_preprocessor"))
sys.path.insert(0, str(HERE))
from pe_diversity import pe_from_n, compute_beta
from onsset import SettlementProcessor

SPINE_IN   = REPO / "data" / "processed" / "zambia_grid3_calib_distgate.csv"
OUT_N10    = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n10.csv"
OUT_N20    = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"
OUT_N50    = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n50.csv"
CONFIG     = REPO / "config" / "config.yaml"

# Household sizes are read from config.yaml (household_size.urban / .rural), NOT hard-coded here.
N_MID_VALS = [10, 20, 50]
OUT_PATHS  = {10: OUT_N10, 20: OUT_N20, 50: OUT_N50}


# Prefer the repo's shared loader (scripts/onsset_helpers.load_config).  That module is documented
# as "stages 06 onward" and imports the whole OnSSET stack, which this pre-processor does not
# otherwise need, so fall back to reading the same file the same way when that stack is absent.
try:
    from onsset_helpers import load_config
except ImportError:
    def load_config() -> dict:
        with open(CONFIG) as f:
            return yaml.safe_load(f)


def project_pop(df: pd.DataFrame, pop_future: float, urban_future: float,
                start_year: int, years: list) -> np.ndarray:
    """
    The engine's own projection of PopStartYear to years[0], on a copy of df, by
    SettlementProcessor.project_pop_and_urban with exactly the arguments the solve uses.
    That routine neither sorts nor re-indexes, so the result aligns with df by position.
    Requires the PopStartYear and IsUrban columns that s04 writes.
    """
    o = SettlementProcessor.__new__(SettlementProcessor)
    o.df = df.copy()
    o.project_pop_and_urban(float(pop_future), float(urban_future), int(start_year), list(years))
    assert o.df.index.equals(df.index), "project_pop_and_urban changed the index"
    return o.df[f"Pop{years[0]}"].to_numpy()


def project_pop_2030(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    """project_pop() with the scenario block of config.yaml — the primary-run analysis year."""
    sc = cfg["scenario"]
    return project_pop(df, sc["pop_end_year"], sc["urban_ratio_end_year"],
                       sc["start_year"], sc["years_of_analysis"])


def n_hh_from_pop(pop: np.ndarray, is_urban: np.ndarray, hh_urban: float, hh_rural: float) -> np.ndarray:
    """max(1, pop / household size), household size by urban flag."""
    hh_size = np.where(is_urban, hh_urban, hh_rural)
    return np.maximum(pop / hh_size, 1.0)


def household_sizes(cfg: dict) -> tuple:
    """
    (urban, rural) household size from config.yaml.

    pe_model.hh_size_urban / hh_size_rural duplicate the same two values.  If they ever diverged,
    the demand calculation and the peak sub-model's connection count would silently disagree, so
    assert they match rather than let the two drift apart.
    """
    hh_urban = float(cfg["household_size"]["urban"])
    hh_rural = float(cfg["household_size"]["rural"])

    pe_cfg = cfg.get("pe_model") or {}
    for key, val, name in (("hh_size_urban", hh_urban, "urban"),
                           ("hh_size_rural", hh_rural, "rural")):
        if key in pe_cfg:
            assert float(pe_cfg[key]) == val, (
                f"config.yaml: pe_model.{key} = {pe_cfg[key]} but household_size.{name} = {val}. "
                f"The peak sub-model and the demand calculation would use different household "
                f"sizes; make them equal.")
    return hh_urban, hh_rural


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

    cfg = load_config()
    hh_urban, hh_rural = household_sizes(cfg)

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

    # Population at the analysis year, by the engine's own projection from PopStartYear
    analysis_year = int(cfg["scenario"]["years_of_analysis"][0])
    pop_ay = project_pop_2030(df, cfg)
    df[f"Pop{analysis_year}"] = pop_ay
    print(f"\n  Projected to {analysis_year} from PopStartYear: "
          f"{df['PopStartYear'].sum()/1e6:.2f} M -> {pop_ay.sum()/1e6:.2f} M")

    # Compute N_hh at the analysis-year population (urban = IsUrban > 1, onsset convention)
    is_urban  = (df["IsUrban"] > 1).to_numpy()
    N_hh      = n_hh_from_pop(pop_ay, is_urban, hh_urban, hh_rural)
    N_hh_2020 = n_hh_from_pop(df["Pop"].to_numpy(), is_urban, hh_urban, hh_rural)
    n_clipped = int((pop_ay / np.where(is_urban, hh_urban, hh_rural) < 1.0).sum())
    df["N_hh"]      = N_hh
    df["N_hh_2020"] = N_hh_2020

    print(f"\n  Household sizes: urban={hh_urban}, rural={hh_rural}"
          f"   (config.yaml household_size)")
    print(f"  N_hh < 1 (clipped to 1): {n_clipped:,}")
    print(f"  N_hh range: [{N_hh.min():.1f}, {N_hh.max():.1f}]")
    print(f"  N_hh urban median: {np.median(N_hh[is_urban]):.1f}   "
          f"(at 2020 population: {np.median(N_hh_2020[is_urban]):.1f})")
    print(f"  N_hh rural median: {np.median(N_hh[~is_urban]):.1f}   "
          f"(at 2020 population: {np.median(N_hh_2020[~is_urban]):.1f})")

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
