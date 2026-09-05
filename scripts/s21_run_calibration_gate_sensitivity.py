#!/usr/bin/env python3
"""
s21_run_calibration_gate_sensitivity.py — the explicit-peak result under the wider base-year gate.

WHY
---
The published calibration admits a settlement as grid-electrified in 2020 if it lies within 2 km
of a mapped transformer and is lit, the procedure OnSSET applies when a transformer layer is
supplied. A wider gate, transformer OR medium-voltage line within 2 km, admits 1,186 further lit
settlements. This solves both arms on the wider gate so its effect on the headline is a number.

DESIGN
------
  * s04 Variant A re-run with mv_or_gate=True on the s03 spine; targets and thresholds
    unchanged.
  * N_hh and PE_ratio recomputed as s05 does (they depend on population only).
  * Both arms at N_mid = 20, config.yaml untouched. The published row is read from the canonical
    2026-08_final_lcoe outputs, not re-run.

    python scripts/s21_run_calibration_gate_sensitivity.py --self-test   # runs no arm
    python scripts/s21_run_calibration_gate_sensitivity.py
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

from pe_diversity import pe_from_n

PROC        = REPO / "data" / "processed"
OUTDIR      = REPO / "data" / "onsset_outputs"
SUMDIR      = REPO / "results" / "summary"
RUN_LABEL   = "2026-09-02_txormv"
SUMMARY_CSV = SUMDIR / "2026-09-02_calibration_gate_sensitivity.csv"

STAGE2_SPINE = PROC / "zambia_grid3_spine_stage2.csv"
CALIB_AS_RUN = PROC / "zambia_grid3_calib_distgate.csv"
CALIB_ORGATE = PROC / "zambia_grid3_calib_distgate_txormv.csv"
CALIB_CHECK  = PROC / "zambia_grid3_calib_distgate_selftest.csv"

YEAR  = 2030
N_MID = 20
R0_CENTRAL = OUTDIR / "2026-08_final_lcoe_R0.csv"
R1_CENTRAL = OUTDIR / f"2026-08_final_lcoe_R1_n{N_MID}.csv"

METRIC_COLS = [f"MinimumOverallLCOE{YEAR}", f"EnergyPerSettlement{YEAR}",
               f"FinalElecCode{YEAR}", f"InvestmentCost{YEAR}", f"NewCapacity{YEAR}", f"Pop{YEAR}"]


def arm_paths() -> dict:
    return {"R0": OUTDIR / f"{RUN_LABEL}_R0.csv",
            "R1": OUTDIR / f"{RUN_LABEL}_R1_n{N_MID}.csv"}


def calibrate(out_path: Path, label: str, mv_or_gate: bool) -> dict:
    """s04 Variant A, unchanged targets and thresholds, with the chosen gate."""
    import s04_calibrate_base_year as s04
    return s04.run_variant(label, spine_path=STAGE2_SPINE,
                           national=s04.A_NATIONAL, urban_r=s04.A_URBAN, rural_r=s04.A_RURAL,
                           max_trans=s04.A_MAX_TRANS, max_mv=s04.A_MAX_MV, max_hv=s04.A_MAX_HV,
                           min_ntl=s04.A_MIN_NTL, min_pop=s04.A_MIN_POP,
                           out_path=out_path, mv_or_gate=mv_or_gate)


def pe_frame(calib_path: Path, cfg: dict) -> pd.DataFrame:
    """s05 for N_mid = 20: sliver reassignment, N_hh, PE_ratio."""
    from s05_compute_peak_ratios import (household_sizes, reassign_border_slivers,
                                         project_pop_2030, n_hh_from_pop)
    hh_urban, hh_rural = household_sizes(cfg)
    df = pd.read_csv(calib_path)
    df = df.drop(columns=["IsUrban_type"], errors="ignore")
    df = reassign_border_slivers(df)
    is_urban = (df["IsUrban"] > 1).to_numpy()
    analysis_year = int(cfg["scenario"]["years_of_analysis"][0])
    pop_ay = project_pop_2030(df, cfg)           # the engine's projection, as s05 does
    df[f"Pop{analysis_year}"] = pop_ay
    N_hh = n_hh_from_pop(pop_ay, is_urban, hh_urban, hh_rural)
    df["N_hh"] = N_hh
    df["PE_ratio"] = pe_from_n(N_hh, N_mid=N_MID)
    return df


def metrics(r0: pd.DataFrame, r1: pd.DataFrame) -> dict:
    """Same energy-weighted formula as s14/s18: both arms weighted by the R0 energy column."""
    lc, ec = f"MinimumOverallLCOE{YEAR}", f"EnergyPerSettlement{YEAR}"
    code, inv, cap, pop = (f"FinalElecCode{YEAR}", f"InvestmentCost{YEAR}",
                           f"NewCapacity{YEAR}", f"Pop{YEAR}")
    e = r0[ec].to_numpy()
    c0, c1 = (r0[lc].to_numpy() * e).sum(), (r1[lc].to_numpy() * e).sum()
    f0, f1 = r0[code].to_numpy(), r1[code].to_numpy()
    p = r0[pop].to_numpy()
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
            "r1_grid_pop_share":   p[f1 == 1].sum() / p.sum()}


def preflight() -> int:
    clash = [p for p in list(arm_paths().values()) + [CALIB_ORGATE] if p.exists()]
    if clash:
        print("REFUSING TO RUN — these output paths already exist:")
        for p in clash:
            print(f"    {p}")
        return 1
    for p in (STAGE2_SPINE, CALIB_AS_RUN, R0_CENTRAL, R1_CENTRAL):
        if not p.exists():
            print(f"  missing input {p.name}")
            return 1
    print("  output collision check: PASS; inputs present")
    return 0


def self_test() -> int:
    """
    Runs no arm. s04 Variant A re-run with the published gate must reproduce the published
    calibration file (ElecStart and ElecPopCalib on every settlement).
    """
    print("=" * 72)
    print("  s21 self-test — published gate reproduces the published calibration (no arm is run)")
    print("=" * 72)
    if CALIB_CHECK.exists():
        CALIB_CHECK.unlink()
    calibrate(CALIB_CHECK, "self-test: Variant A, 2 km transformer gate", mv_or_gate=False)
    a = pd.read_csv(CALIB_AS_RUN, usecols=["id", "ElecStart", "ElecPopCalib"]).sort_values("id")
    b = pd.read_csv(CALIB_CHECK,  usecols=["id", "ElecStart", "ElecPopCalib"]).sort_values("id")
    es = bool(np.array_equal(a["ElecStart"].to_numpy(), b["ElecStart"].to_numpy()))
    ep = bool(np.allclose(a["ElecPopCalib"].to_numpy(), b["ElecPopCalib"].to_numpy(), rtol=1e-9))
    n_a, n_b = int(a["ElecStart"].sum()), int(b["ElecStart"].sum())
    print(f"\n  ElecStart=1: published {n_a:,}   re-run {n_b:,}   identical rows: {es}")
    print(f"  ElecPopCalib identical: {ep}")
    CALIB_CHECK.unlink()
    ok = es and ep
    print("\n  " + ("SELF-TEST PASS" if ok else "SELF-TEST FAIL"))
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    from onsset_helpers import load_solar_profile, load_wind_profile, load_config
    from s06_run_arms import run_arm, assert_base_cols_match, TX_SHP, SOLAR_PROFILE, WIND_PROFILE
    from onsset import SettlementProcessor
    print("=" * 72)
    print(f"  s21 — calibration-gate sensitivity: transformer OR MV within 2 km   ({RUN_LABEL})")
    print("=" * 72)
    if preflight() != 0:
        return 1
    if self_test() != 0:
        print("self-test failed; refusing to run")
        return 1
    cfg = load_config()
    t_all = time.time()

    cal = calibrate(CALIB_ORGATE, "Variant A targets, transformer OR MV gate", mv_or_gate=True)
    df_pe = pe_frame(CALIB_ORGATE, cfg)
    df_r0 = df_pe.drop(columns=["PE_ratio", "N_hh"])
    df_r1 = df_r0.copy()
    df_r1["PE_ratio"] = df_pe["PE_ratio"].to_numpy()
    assert_base_cols_match(df_r0, df_r1, f"R1_n{N_MID}_txormv")

    np.random.seed(42)
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    paths, pair = arm_paths(), {}
    for arm, frame, n_mid in (("R0", df_r0, None), ("R1", df_r1, N_MID)):
        proc, _, _ = run_arm(f"{arm}_txormv", frame, cfg, x_tx, y_tx,
                             ghi_profile, temp_profile, wind_profile, n_mid=n_mid)
        proc.df.sort_values("id", inplace=True)
        proc.df.to_csv(paths[arm], index=False)
        pair[arm] = proc.df[METRIC_COLS].reset_index(drop=True).copy()
        del proc

    rows = []
    m = metrics(pair["R0"], pair["R1"])
    m.update({"gate": "transformer OR MV < 2 km", "elec_settlements_2020": cal["n_elec_settle"],
              "calib_national": cal["national_rate"], "calib_urban": cal["urban_rate"],
              "calib_rural": cal["rural_rate"], "source": RUN_LABEL})
    rows.append(m)

    r0c = pd.read_csv(R0_CENTRAL, usecols=METRIC_COLS)
    r1c = pd.read_csv(R1_CENTRAL, usecols=METRIC_COLS)
    calib = pd.read_csv(CALIB_AS_RUN, usecols=["ElecStart"])
    m = metrics(r0c, r1c)
    m.update({"gate": "transformer < 2 km (published)",
              "elec_settlements_2020": int(calib["ElecStart"].sum()),
              "calib_national": np.nan, "calib_urban": np.nan, "calib_rural": np.nan,
              "source": "2026-08_final_lcoe (canonical)"})
    rows.append(m)

    out = pd.DataFrame(rows)
    out.to_csv(SUMMARY_CSV, index=False)
    print("\n" + "=" * 72)
    print("  CALIBRATION-GATE SENSITIVITY — N_mid = 20, 2030 columns")
    print("=" * 72)
    print(out.set_index("gate").T.to_string())
    print(f"\n  summary -> {SUMMARY_CSV}")
    print(f"  done in {(time.time() - t_all) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
