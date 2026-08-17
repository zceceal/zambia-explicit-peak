"""
s12_run_2050_horizon.py — 2050 endpoint, two-arm (R0 / R1) driver.

Reuses run_arm() from run_grid3_lcoe_stage4.py (the harness that produced the published
2026-07-01_grid3 outputs) unchanged. Two modes:

  python run_2050_arms.py validate2035   # re-runs 2035 R0 + R1_n20 with the untouched config;
                                         # headline must reproduce +49.9% / 34,461
  python run_2050_arms.py 2050           # same harness, only the 2050_RUN_INPUTS.md §A changes:
                                         #   end_year 2050, PopEndYear 38,083,385, urban 0.672,
                                         #   years_of_analysis [2030, 2050],
                                         #   R1 spine = zambia_grid3_spine_pe_2050_n20.csv
  python run_2050_arms.py 2050only      # single analysis year [2050] — the clean endpoint read:
                                         #   everyone connected at 2050 demand, full lifetime LCOEs.
                                         #   (The [2030,2050] run reaches 100% electrification at the
                                         #   2030 stage, so its 2050 columns are incremental-only:
                                         #   LCOE = marginal generation, median energy 0. The headline
                                         #   must NOT be read from that run — diagnosed 2026-07-16.)
  python run_2050_arms.py sweep          # 2050 R1 arms for N_mid=10 and 50 (R0 already run)
  python run_2050_arms.py ruralT2        # 2050 rural Tier-2 sensitivity: rural_tier_large/small
                                         # 3 -> 2 (as stage 4b did at 2035); R0 + R1 n10/n20/n50
  python run_2050_arms.py 2050only_sweep    # N_mid=10/50 sweep in the single-year [2050] convention
  python run_2050_arms.py 2050only_ruralT2  # rural Tier-2 in the single-year [2050] convention

Everything else (costs, tiers, discount rates, calibration, seed 42) comes byte-identical from
config/config.yaml — never edited here.

Outputs go to results/ (2035 originals untouched):
  validate2035: revalidate_2035_R0.csv, revalidate_2035_R1_n20.csv
  2050:         2050_grid3_lcoe_R0.csv, 2050_grid3_lcoe_R1_n20.csv
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / "scripts"

sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(SCRIPTS))

from onsset_helpers import load_solar_profile, load_wind_profile, load_config
from s06_run_arms import (
    run_arm, PE_N20, TX_SHP, SOLAR_PROFILE, WIND_PROFILE,
)
from onsset import SettlementProcessor

PE_2050_N20 = REPO / "data" / "processed" / "zambia_grid3_spine_pe_2050_n20.csv"
PE_2050 = {n: REPO / "data" / "processed" / f"zambia_grid3_spine_pe_2050_n{n}.csv"
           for n in (10, 20, 50)}
OUTDIR = HERE / "outputs"

WPP_2050 = {"end_year": 2050, "pop_end_year": 38_083_385,
            "urban_ratio_end_year": 0.672, "years_of_analysis": [2030, 2050]}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "2050"
    assert mode in ("validate2035", "2050", "2050only", "sweep", "ruralT2",
                    "2050only_sweep", "2050only_ruralT2"), f"unknown mode {mode}"

    cfg = load_config()
    if mode != "validate2035":
        cfg["scenario"].update(WPP_2050)
    if mode.startswith("2050only"):
        # Single analysis year: the whole plan is decided at 2050 demand with full lifetime
        # LCOEs (time_step = 30) — the clean analogue of the published 2030-column read.
        cfg["scenario"]["years_of_analysis"] = [2050]

    # (arm_label, spine_path or None for R0, n_mid, output path)
    if mode == "validate2035":
        spine_n20 = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"
        runs = [("R0", None, None, OUTDIR / "revalidate_2035_R0.csv"),
                ("R1_n20", spine_n20, 20, OUTDIR / "revalidate_2035_R1_n20.csv")]
    elif mode == "2050":
        runs = [("R0", None, None, OUTDIR / "2050_grid3_lcoe_R0.csv"),
                ("R1_n20", PE_2050[20], 20, OUTDIR / "2050_grid3_lcoe_R1_n20.csv")]
    elif mode == "2050only":
        runs = [("R0", None, None, OUTDIR / "2050only_grid3_lcoe_R0.csv"),
                ("R1_n20", PE_2050[20], 20, OUTDIR / "2050only_grid3_lcoe_R1_n20.csv")]
    elif mode == "sweep":
        runs = [(f"R1_n{n}", PE_2050[n], n, OUTDIR / f"2050_grid3_lcoe_R1_n{n}.csv")
                for n in (10, 50)]
    elif mode == "2050only_sweep":
        runs = [(f"R1_n{n}", PE_2050[n], n, OUTDIR / f"2050only_grid3_lcoe_R1_n{n}.csv")
                for n in (10, 50)]
    else:  # ruralT2 variants — one change, exactly as stage 4b did at 2035
        cfg["demand_tiers"]["rural_tier_large"] = 2
        cfg["demand_tiers"]["rural_tier_small"] = 2
        prefix = "2050only" if mode.startswith("2050only") else "2050"
        runs = [("R0_ruralT2", None, None,
                 OUTDIR / f"{prefix}_grid3_lcoe_R0_ruralT2.csv")]
        runs += [(f"R1_ruralT2_n{n}", PE_2050[n], n,
                  OUTDIR / f"{prefix}_grid3_lcoe_R1_ruralT2_n{n}.csv") for n in (10, 20, 50)]

    sc = cfg["scenario"]
    print("=" * 65)
    print(f"  2050-horizon driver — mode {mode}")
    print(f"  end_year={sc['end_year']}  pop_end={sc['pop_end_year']:,}  "
          f"urban_end={sc['urban_ratio_end_year']}  years={sc['years_of_analysis']}")
    print(f"  rural tiers: large={cfg['demand_tiers']['rural_tier_large']} "
          f"small={cfg['demand_tiers']['rural_tier_small']}  "
          f"urban={cfg['demand_tiers']['urban_tier']}")
    print(f"  arms: {[r[0] for r in runs]}")
    print("=" * 65)

    OUTDIR.mkdir(exist_ok=True)
    np.random.seed(42)

    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    print(f"  Profiles + TX network loaded ({len(x_tx):,} start points)")

    df_r0_base = pd.read_csv(PE_N20).drop(columns=["PE_ratio", "N_hh"], errors="ignore")

    t0 = time.time()
    for label, spine_path, n_mid, out_path in runs:
        if spine_path is None:
            df_arm = df_r0_base
        else:
            df_arm = pd.read_csv(spine_path).drop(columns=["N_hh"], errors="ignore")
            base_cols = [c for c in df_arm.columns if c != "PE_ratio"]
            diff = [c for c in base_cols if not df_r0_base[c].equals(df_arm[c])]
            assert not diff, f"{label}: base columns differ from R0: {diff}"
            print(f"  {label}: base columns byte-identical to R0 (only PE_ratio differs) — PASS")
        proc, _, _ = run_arm(label, df_arm, cfg, x_tx, y_tx,
                             ghi_profile, temp_profile, wind_profile, n_mid=n_mid)
        proc.df.sort_values("id", inplace=True)  # labels are lat/lon order after condition_df; restore id order on disk
        proc.df.to_csv(out_path, index=False)
        print(f"  {label} output → {out_path}")

    print(f"\n  All {len(runs)} arm(s) done in {(time.time()-t0)/60:.1f} min")
    if mode == "2050only":
        print("  Headline: python headline_from_outputs.py "
              "outputs/2050only_grid3_lcoe_R0.csv outputs/2050only_grid3_lcoe_R1_n20.csv 2050")


if __name__ == "__main__":
    main()
