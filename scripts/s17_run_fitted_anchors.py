#!/usr/bin/env python3
"""
s17_run_fitted_anchors.py — the R1 arm under a coincidence curve FITTED to the study's own
independent validation anchors, removing the N_mid assumption entirely.

WHY
---
The central calibration fixes rho_inf = 1.45 (Lorenzoni's "Flat" archetype) and derives beta from
an assumed N_mid = 20. The paper's two external validation anchors play no part in that
calibration — which means they can be used to FIT the curve instead:

    metered Ethiopian residential mini-grid   rho = 1.80  at N ~ 450   (Wassie & Ahlgren 2024)
    Zambian national residential aggregate    rho ~ 1.67  at N ~ 1.3e6 (ERB 2021 / IRP demand)

With rho_1 = 3.98 kept at N = 1, two anchors determine the two remaining parameters exactly:

    rho_inf = 1.670          (the national aggregate pins the floor; the decaying term is
                              negligible at N = 1.3 million for any plausible beta)
    beta    = 0.47096        (from the Ethiopian anchor)
    equivalent N_mid = 10.6  (inside the swept 10-50 range)

The fitted curve reproduces both anchors exactly (1.800 at 450; 1.673 at 1.3e6) where the central
curve gives 1.816 and 1.479. It is flatter at small N (rho 3.23 vs 3.39 at the rural median of
2.3 households) but has a higher floor, so the large grid-served settlements that carry ~72% of
national energy become PEAKIER relative to the central curve (1.74 vs 1.68 at the urban median).

This is an exactly-determined alternative calibration, not a statistical fit: two anchors, two
parameters, no residual. Its value is that it is independent of the Lorenzoni "Flat" archetype and
of the N_mid assumption — the paper's one stated free parameter disappears.

    python scripts/s17_run_fitted_anchors.py             # one R1 arm; compares to final R0
    python scripts/s17_run_fitted_anchors.py --self-test
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(HERE))

OUTDIR    = REPO / "data" / "onsset_outputs"
RUN_LABEL = "2026-08_fittedanchor_lcoe"
R0_FINAL  = OUTDIR / "2026-08_final_lcoe_R0.csv"
YEAR      = 2030

RHO_1   = 3.98       # kept: Lorenzoni "Peak" archetype at N = 1
RHO_INF = 1.670      # fitted: Zambian national residential aggregate at N ~ 1.3e6
BETA    = 0.47096    # fitted: metered Ethiopian residential anchor, rho = 1.80 at N = 450


def rho_fitted(N):
    N = np.maximum(np.asarray(N, dtype=float), 1.0)
    return RHO_INF + (RHO_1 - RHO_INF) * N ** (-BETA)


def self_test():
    print("Self-test: the fitted curve must reproduce the two independent anchors exactly\n")
    checks = [("Ethiopian residential mini-grid", 450.0, 1.80, 5e-3),
              ("Zambian national aggregate", 1.3e6, 1.67, 5e-3),
              ("Lorenzoni Peak archetype (kept)", 1.0, 3.98, 1e-9)]
    ok = True
    for name, n, expect, tol in checks:
        got = float(rho_fitted(n))
        good = abs(got - expect) < tol
        ok &= good
        print(f"  {name:<36} N={n:>9,.0f}  rho={got:.4f}  expect {expect:.2f}"
              f"  {'PASS' if good else 'FAIL'}")
    import math
    n_mid_eq = math.exp(-math.log((2.43 - RHO_INF) / (RHO_1 - RHO_INF)) / BETA)
    print(f"\n  equivalent N_mid = {n_mid_eq:.2f}  (central assumption: 20; swept 10-50)")
    print(f"  rho at rural median N=2.3 : {float(rho_fitted(2.3)):.3f}  (central curve: 3.394)")
    print(f"  rho at urban median N=1925: {float(rho_fitted(1925)):.3f}  (central curve: 1.681)")
    print("  PASS" if ok else "  FAIL")
    return 0 if ok else 1


def main():
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        print("self-test failed; refusing to run")
        return 1
    if not R0_FINAL.exists():
        print(f"missing {R0_FINAL.name} — run s06 first")
        return 1

    from onsset_helpers import load_solar_profile, load_wind_profile, load_config
    from s06_run_arms import run_arm, PE_N20, TX_SHP, SOLAR_PROFILE, WIND_PROFILE
    from onsset import SettlementProcessor

    cfg = load_config()
    np.random.seed(42)
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))

    base = pd.read_csv(PE_N20)
    assert "N_hh" in base.columns, "spine lacks N_hh; cannot recompute the curve"
    base["PE_ratio"] = rho_fitted(base["N_hh"].to_numpy())
    print(f"\n  PE_ratio recomputed from fitted anchors: "
          f"median {base['PE_ratio'].median():.3f}  (central-curve spine median 3.38)")
    df_r1 = base.drop(columns=["N_hh"], errors="ignore")

    t0 = time.time()
    proc, _, _ = run_arm("R1_fitted", df_r1, cfg, x_tx, y_tx,
                         ghi_profile, temp_profile, wind_profile, n_mid=20)
    proc.df.sort_values("id", inplace=True)
    out = OUTDIR / f"{RUN_LABEL}_R1.csv"
    proc.df.to_csv(out, index=False)
    print(f"  R1_fitted -> {out.name}")

    r0 = pd.read_csv(R0_FINAL, usecols=[f"MinimumOverallLCOE{YEAR}",
                                        f"EnergyPerSettlement{YEAR}", f"FinalElecCode{YEAR}"])
    r1 = proc.df
    e = r0[f"EnergyPerSettlement{YEAR}"].to_numpy()
    c0 = (r0[f"MinimumOverallLCOE{YEAR}"].to_numpy() * e).sum()
    c1 = (r1[f"MinimumOverallLCOE{YEAR}"].to_numpy() * e).sum()
    sw = int(((r0[f"FinalElecCode{YEAR}"].to_numpy() == 3)
              & (r1[f"FinalElecCode{YEAR}"].to_numpy() == 1)).sum())
    print("\n" + "=" * 68)
    print(f"  FITTED-ANCHOR CURVE:  DeltaLCOE% = {(c1 - c0) / c0 * 100:+.2f}%   "
          f"switches = {sw:,}")
    print(f"  central (N_mid=20):   +49.92%,  34,461")
    print(f"  sweep band:           +34.1% (n10)  ...  +70.6% (n50)")
    print(f"  elapsed {(time.time() - t0) / 60:.1f} min")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
