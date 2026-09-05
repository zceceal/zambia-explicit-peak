#!/usr/bin/env python3
"""
s18_run_hhsize_sensitivity.py — how much of the explicit-peak result rides on the census
household size?

WHY
---
Household size s enters the model on two channels, and they pull in opposite directions:

  (a) demand   — OnSSET converts people to households (Pop / s) and then to kWh/yr.  A larger s
                 means FEWER households and so LESS energy per settlement.  Affects BOTH arms.
  (b) diversity — the coincidence sub-model's connection count is N = max(1, Pop / s), and
                 rho = pe_from_n(N) falls with N.  A larger s means a smaller N and so a PEAKIER
                 settlement.  Affects the explicit-peak arm ONLY.

Because (a) is common-mode and (b) is treatment-only, s cannot be dismissed as "it just rescales
demand": it moves the R1-R0 contrast directly.  This measures that exposure.

DESIGN
------
  * rural household size perturbed to 4.5 and 5.5 against the ZamStats 2022 central 5.0.
    Urban is left at 4.6 — only 176 settlements are urban, so perturbing it measures nothing.
  * N_mid = 20 (the central case) only.
  * Both arms at each perturbed value: four arms.  The s = 5.0 row is NOT re-run; it is read from
    the canonical 2026-08_final_lcoe outputs.
  * config.yaml is NEVER edited.  The dict is overridden in memory, and the SAME overridden value
    is used for the demand calculation (cfg -> run_arm -> calculate_demand) and for the connection
    count (N_hh -> pe_from_n).  s05.household_sizes() enforces that the two config keys that carry
    the household size cannot disagree.

    python scripts/s18_run_hhsize_sensitivity.py --self-test   # plumbing only, runs no arm
    python scripts/s18_run_hhsize_sensitivity.py
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

from pe_diversity import pe_from_n, compute_beta

OUTDIR     = REPO / "data" / "onsset_outputs"
SUMDIR     = REPO / "results" / "summary"
RUN_LABEL  = "2026-08-21_hhsize"
SUMMARY_CSV = SUMDIR / "2026-08-21_hhsize_sensitivity.csv"

YEAR       = 2030
N_MID      = 20
HH_RURAL_CENTRAL = 5.0
HH_RURAL_SWEEP   = [4.5, 5.5]          # census central 5.0 is the canonical run, not repeated

# canonical pair for the s = 5.0 row
R0_CENTRAL = OUTDIR / "2026-08_final_lcoe_R0.csv"
R1_CENTRAL = OUTDIR / f"2026-08_final_lcoe_R1_n{N_MID}.csv"



def tag(s: float) -> str:
    """Filename-safe tag for a household size (4.5 -> '4p5')."""
    return f"{s:g}".replace(".", "p")


def arm_paths(s: float) -> dict:
    return {"R0": OUTDIR / f"{RUN_LABEL}_R0_rural{tag(s)}.csv",
            "R1": OUTDIR / f"{RUN_LABEL}_R1_n{N_MID}_rural{tag(s)}.csv"}


def override_cfg(cfg: dict, hh_rural: float) -> dict:
    """
    Copy of cfg with the rural household size replaced, in memory only.

    Both keys that carry it are set: household_size.rural drives OnSSET's demand calculation via
    run_arm, and pe_model.hh_size_rural is the duplicate s05 asserts against.  Setting one and not
    the other is exactly the silent divergence this experiment exists to rule out.
    """
    import copy
    from s05_compute_peak_ratios import household_sizes

    cfg = copy.deepcopy(cfg)
    cfg["household_size"]["rural"] = float(hh_rural)
    if "pe_model" in cfg and "hh_size_rural" in cfg["pe_model"]:
        cfg["pe_model"]["hh_size_rural"] = float(hh_rural)
    hh_u, hh_r = household_sizes(cfg)          # asserts the two keys agree
    assert hh_r == float(hh_rural), (hh_r, hh_rural)
    return cfg


def recompute_pe(df: pd.DataFrame, hh_urban: float, hh_rural: float) -> tuple:
    """
    N_hh and PE_ratio for a given household size, computed exactly as s05 does:
        N_hh     = max(1, Pop2030 / s)      s by urban/rural, IsUrban > 1 is urban; Pop2030 is
                                            the engine's projection that s05 wrote to the spine
        PE_ratio = pe_from_n(N_hh, N_mid)
    Returns (N_hh, PE_ratio, is_urban_mask).
    """
    is_urban = (df["IsUrban"] > 1).to_numpy()
    hh_size  = np.where(is_urban, hh_urban, hh_rural)
    N_hh     = np.maximum(df["Pop2030"].to_numpy() / hh_size, 1.0)
    return N_hh, pe_from_n(N_hh, N_mid=N_MID), is_urban


def metrics(r0: pd.DataFrame, r1: pd.DataFrame) -> dict:
    """
    Headline contrast for one arm pair, using the SAME energy-weighted formula as
    s14_paper_numbers.py: both arms' LCOEs are weighted by the R0 energy column.
    """
    lc, ec = f"MinimumOverallLCOE{YEAR}", f"EnergyPerSettlement{YEAR}"
    code, inv, cap = f"FinalElecCode{YEAR}", f"InvestmentCost{YEAR}", f"NewCapacity{YEAR}"

    e  = r0[ec].to_numpy()
    c0 = (r0[lc].to_numpy() * e).sum()
    c1 = (r1[lc].to_numpy() * e).sum()
    f0, f1 = r0[code].to_numpy(), r1[code].to_numpy()
    i0, i1 = r0[inv].sum(), r1[inv].sum()
    k0, k1 = r0[cap].sum(), r1[cap].sum()
    return {"dlcoe_pct":     (c1 - c0) / c0 * 100.0,
            "switches_sapv_grid": int(((f0 == 3) & (f1 == 1)).sum()),
            "switches_total":     int((f0 != f1).sum()),
            "d_investment_pct":   (i1 / i0 - 1.0) * 100.0,
            "d_capacity_pct":     (k1 / k0 - 1.0) * 100.0,
            "investment_r0_bn":   i0 / 1e9,
            "investment_r1_bn":   i1 / 1e9}


METRIC_COLS = [f"MinimumOverallLCOE{YEAR}", f"EnergyPerSettlement{YEAR}",
               f"FinalElecCode{YEAR}", f"InvestmentCost{YEAR}", f"NewCapacity{YEAR}"]


def preflight() -> int:
    """Refuse to start if any per-settlement solve output already exists — those are large,
    unique per run, and nothing here may silently overwrite one. SUMMARY_CSV is exempt: it is
    committed to the repository (so it exists on every fresh clone) and rewriting it with a
    freshly-solved, identical-or-corrected value is this script's own job, run to run."""
    intended = []
    for s in HH_RURAL_SWEEP:
        intended += list(arm_paths(s).values())
    clash = [p for p in intended if p.exists()]
    if clash:
        print("REFUSING TO RUN — these output paths already exist:")
        for p in clash:
            print(f"    {p}")
        return 1
    print(f"  output collision check: {len(intended)} intended paths, none exist — PASS")
    if SUMMARY_CSV.exists():
        print(f"  {SUMMARY_CSV.name} already exists (committed reference) — will be overwritten")
    for p in (R0_CENTRAL, R1_CENTRAL):
        if not p.exists():
            print(f"  missing canonical reference {p.name} — run s06 first")
            return 1
    print(f"  canonical s=5.0 reference present: {R0_CENTRAL.name}, {R1_CENTRAL.name}")
    return 0


def self_test(cfg=None) -> int:
    """
    Plumbing check, runs no arm:
      1. the in-memory override moves both config keys and survives s05's consistency assertion;
      2. at s = 5.0 the recomputed N_hh and PE_ratio reproduce the canonical spine columns
         — proof that this script's pre-processor is the same one that built the published spine.
         Compared to a tolerance, not bit-exactly: the spine's columns have been through a CSV
         write/read round trip, which is only exact when the reading pandas formats floats the same
         way the writing one did.  The tolerance below is ~1e9 times tighter than any household-size
         error could be (getting s wrong moves N_hh by ~10%), so it still catches a real mistake;
      3. the rural rho the sweep will actually apply.
    """
    from onsset_helpers import load_config
    from s06_run_arms import PE_N20

    print("=" * 72)
    print("  s18 self-test — household-size plumbing (no arm is run)")
    print("=" * 72)
    cfg = cfg or load_config()
    print(f"\n  config household_size: {cfg['household_size']}")
    print(f"  config pe_model hh:    urban={cfg['pe_model'].get('hh_size_urban')} "
          f"rural={cfg['pe_model'].get('hh_size_rural')}")

    ok = True
    for s in [HH_RURAL_CENTRAL] + HH_RURAL_SWEEP:
        c = override_cfg(cfg, s)
        good = (c["household_size"]["rural"] == s
                and c["pe_model"]["hh_size_rural"] == s
                and cfg["household_size"]["rural"] == HH_RURAL_CENTRAL)   # original untouched
        ok &= good
        print(f"  override rural={s}: household_size.rural={c['household_size']['rural']}, "
              f"pe_model.hh_size_rural={c['pe_model']['hh_size_rural']}, "
              f"source cfg unchanged={cfg['household_size']['rural']==HH_RURAL_CENTRAL}  "
              f"{'PASS' if good else 'FAIL'}")

    spine = pd.read_csv(PE_N20)
    hh_u = float(cfg["household_size"]["urban"])
    N_hh, pe, is_urban = recompute_pe(spine, hh_u, HH_RURAL_CENTRAL)
    RTOL = 1e-9
    print(f"\n  at s = {HH_RURAL_CENTRAL} the recomputed columns must reproduce the published spine")
    print(f"  (rtol {RTOL:g}; bit-exact only when the reading pandas matches the writing one):")
    both_ok = True
    for name, got in (("N_hh", N_hh), ("PE_ratio", pe)):
        ref  = spine[name].to_numpy()
        rel  = float(np.max(np.abs(got - ref) / np.maximum(np.abs(ref), 1e-30)))
        good = bool(np.allclose(got, ref, rtol=RTOL, atol=0.0))
        both_ok &= good
        print(f"    {name:<9} max rel diff {rel:.3g}   bit-exact={np.array_equal(got, ref)}   "
              f"{'PASS' if good else 'FAIL'}")
    ok &= both_ok

    print(f"\n  beta(N_mid={N_MID}) = {compute_beta(N_MID):.4f}")
    print(f"  {'rural s':>8}  {'median N_hh':>12}  {'median rho':>11}  {'pop-wtd rho':>12}")
    for s in [HH_RURAL_CENTRAL] + sorted(HH_RURAL_SWEEP):
        N, p, urb = recompute_pe(spine, hh_u, s)
        rural = ~urb
        print(f"  {s:>8.1f}  {np.median(N[rural]):>12.3f}  {np.median(p[rural]):>11.4f}  "
              f"{np.average(p, weights=spine['Pop2030'].to_numpy()):>12.4f}")

    print("\n  " + ("SELF-TEST PASS" if ok else "SELF-TEST FAIL"))
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    from onsset_helpers import load_solar_profile, load_wind_profile, load_config
    from s06_run_arms import (run_arm, assert_base_cols_match,
                              PE_N20, TX_SHP, SOLAR_PROFILE, WIND_PROFILE)
    from onsset import SettlementProcessor

    print("=" * 72)
    print(f"  s18 — rural household-size sensitivity   (N_mid={N_MID}, {RUN_LABEL})")
    print("=" * 72)

    cfg = load_config()
    if preflight() != 0:
        return 1
    if self_test(cfg) != 0:
        print("self-test failed; refusing to run")
        return 1

    OUTDIR.mkdir(parents=True, exist_ok=True)
    SUMDIR.mkdir(parents=True, exist_ok=True)

    np.random.seed(42)
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    print(f"\n  profiles + TX network loaded ({len(x_tx):,} start points)")

    # One base frame for every arm, exactly as s06 does: the spine's own N_hh / PE_ratio are
    # dropped because this script recomputes both for each household size.
    spine  = pd.read_csv(PE_N20)
    hh_u   = float(cfg["household_size"]["urban"])
    df_r0  = spine.drop(columns=["PE_ratio", "N_hh"], errors="ignore")
    print(f"  base frame: {len(df_r0):,} rows x {len(df_r0.columns)} columns "
          f"(urban household size held at {hh_u})")

    rows, t_all = [], time.time()
    for s in HH_RURAL_SWEEP:
        cfg_s = override_cfg(cfg, s)
        N_hh, pe, is_urban = recompute_pe(spine, hh_u, s)
        rural_median_rho = float(np.median(pe[~is_urban]))
        paths = arm_paths(s)

        print("\n" + "=" * 72)
        print(f"  RURAL HOUSEHOLD SIZE s = {s}   (urban {hh_u}, N_mid {N_MID})")
        print(f"  median rural N_hh {np.median(N_hh[~is_urban]):.3f}  ->  "
              f"median rural rho {rural_median_rho:.4f}")
        print("=" * 72)

        df_r1 = df_r0.copy()
        df_r1["PE_ratio"] = pe

        # Task B guard: the arms may differ in PE_ratio and in nothing else.
        assert_base_cols_match(df_r0, df_r1, f"R1_n{N_MID}_rural{tag(s)}")

        pair = {}
        for arm, frame, n_mid in (("R0", df_r0, None), ("R1", df_r1, N_MID)):
            label = f"{arm}_rural{tag(s)}"
            proc, _, _ = run_arm(label, frame, cfg_s, x_tx, y_tx,
                                 ghi_profile, temp_profile, wind_profile, n_mid=n_mid)
            proc.df.sort_values("id", inplace=True)   # restore id order on disk
            proc.df.to_csv(paths[arm], index=False)
            print(f"  {label} -> {paths[arm].name}")
            pair[arm] = proc.df[METRIC_COLS].reset_index(drop=True).copy()
            del proc

        m = metrics(pair["R0"], pair["R1"])
        m.update({"hh_rural": s, "hh_urban": hh_u, "n_mid": N_MID,
                  "rural_median_rho": rural_median_rho,
                  "source": RUN_LABEL})
        rows.append(m)
        print(f"\n  s={s}:  DeltaLCOE {m['dlcoe_pct']:+.4f}%   "
              f"SA_PV->Grid {m['switches_sapv_grid']:,}   "
              f"DeltaInv {m['d_investment_pct']:+.2f}%   rural rho {rural_median_rho:.4f}")

    # ── the census-central row, read from the canonical outputs (never re-run) ────────────
    print("\n" + "=" * 72)
    print(f"  s = {HH_RURAL_CENTRAL} (census central) — from canonical {R0_CENTRAL.name}")
    print("=" * 72)
    r0c = pd.read_csv(R0_CENTRAL, usecols=METRIC_COLS)
    r1c = pd.read_csv(R1_CENTRAL, usecols=METRIC_COLS)
    _, pe_c, urb_c = recompute_pe(spine, hh_u, HH_RURAL_CENTRAL)
    m = metrics(r0c, r1c)
    m.update({"hh_rural": HH_RURAL_CENTRAL, "hh_urban": hh_u, "n_mid": N_MID,
              "rural_median_rho": float(np.median(pe_c[~urb_c])),
              "source": "2026-08_final_lcoe (canonical)"})
    rows.append(m)
    del r0c, r1c

    out = pd.DataFrame(rows).sort_values("hh_rural")
    cols = ["hh_rural", "hh_urban", "n_mid", "rural_median_rho", "dlcoe_pct",
            "switches_sapv_grid", "switches_total", "d_investment_pct", "d_capacity_pct",
            "investment_r0_bn", "investment_r1_bn", "source"]
    out = out[cols]
    out.to_csv(SUMMARY_CSV, index=False)

    print("\n" + "=" * 72)
    print("  RURAL HOUSEHOLD-SIZE SENSITIVITY — N_mid = 20, 2030 columns")
    print("=" * 72)
    print(f"  {'rural s':>8}  {'rural rho':>10}  {'DeltaLCOE%':>11}  "
          f"{'SA_PV->Grid':>12}  {'DeltaInv%':>10}")
    for _, r in out.iterrows():
        print(f"  {r['hh_rural']:>8.1f}  {r['rural_median_rho']:>10.4f}  "
              f"{r['dlcoe_pct']:>+11.4f}  "
              f"{int(r['switches_sapv_grid']):>12,}  "
              f"{r['d_investment_pct']:>+10.2f}")
    print(f"\n  summary -> {SUMMARY_CSV}")
    print(f"  all arms done in {(time.time() - t_all) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
