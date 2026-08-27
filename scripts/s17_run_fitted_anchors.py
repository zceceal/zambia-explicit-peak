#!/usr/bin/env python3
"""
s17_run_fitted_anchors.py — the R1 arm under a coincidence curve calibrated to the metered Tum
mini-grid and Zambia's own national residential load-factor assumption, removing the N_mid
assumption entirely.

WHY
---
The central calibration fixes rho_inf = 1.45 (Lorenzoni's "Flat" archetype) and derives beta from
an assumed N_mid = 20. Two other reference points play no part in that calibration — which means
they can be used to fit the curve instead. Only one of them is a measurement:

    metered Ethiopian residential mini-grid       rho = 1.80    at N ~ 450   (Wassie & Ahlgren
                                                                              2024, Tum)
    Zambia's national residential load-factor     rho = 1.4587  at N ~ 1.0e6 (IRP Demand
    assumption (NOT a measurement — see below)                              Assessment and
                                                                              Forecast, Table 3.01)

The second point is not an independent observation of national peak-to-mean behaviour. The IRP
states it directly: "The load factor for demand from the residential sector is constant over the
modelled period at 68.5%." Table 3.01's two 2020 figures are both generated FROM that one assumed
load factor, not measured independently of each other: 1/0.685 = 1.4599 (the anchor value, up to
rounding), and 4,618 GWh / 8,760 h / 0.685 = 769.59 MW, which is exactly the table's stated 769 MW
peak. Dividing the table's peak by its energy therefore just returns the load-factor assumption the
table was built from. `rho = 1.4587` is correct arithmetic and a correct reading of the source — it
is simply Zambia's own planning assumption about national residential load shape, not a metered
peak-to-mean ratio. It is still worth comparing against: it shows what this model implies at
national scale next to what Zambia's own planner assumes. It is not external validation by
measurement, and should never be described as "measured" or "independently validated".

With rho_1 = 3.98 kept at N = 1, the Tum measurement and the IRP load-factor assumption pin the
remaining two parameters — but NOT by setting rho_inf equal to the raw reading at the second point's
N and deriving beta from Tum alone. That shortcut (the earlier version of this script) assumed the
decaying term (rho_1 - rho_inf)*N^-beta is negligible by N = 1e6, which held for the old, faster-
decaying fit (beta ~= 0.47, residual ~0.003) but does not hold here: fixing rho_inf = 1.4587 and
solving beta from Tum alone gives beta = 0.32733, and at that beta the curve has NOT converged by
N = 1e6 (it gives 1.4861, not 1.4587 — a 0.027 residual, 5x too large to call "negligible"). This
also would have made the paper's own description of the method (§2.4: "the two anchors determine
[rho_inf and beta] exactly") false. So both parameters are instead solved SIMULTANEOUSLY, as a 2x2
nonlinear system fitting both points exactly (scipy.optimize.fsolve, done at runtime — see
calibrate_curve() below):

    rho_inf = 1.42545        (solved, not read directly off either anchor)
    beta    = 0.31426        (solved)
    equivalent N_mid = 19.49 (inside the swept 10-50 range)

rho_inf comes out slightly below Lorenzoni's own "Flat" archetype of 1.45 — expected, not a defect:
it reflects that the IRP point at N=1e6 has not fully converged to the curve's asymptote at this
beta, which pulls the solved floor down a little to fit both points exactly.

The fitted curve reproduces both points to solver tolerance (<1e-9): 1.800 at 450, 1.4587 at 1.0e6.
The central curve gives 1.816 and 1.482 at those same two N. The fitted curve is essentially on the
central curve at the rural median (rho 3.39 vs 3.39 at N=2.3 households) and slightly below it at the
urban median (1.66 vs 1.68 at N=1925).

This is an exactly-determined alternative calibration, not a statistical fit: two reference points,
two parameters, zero residual by construction. Its value is that it is independent of the Lorenzoni
"Flat" archetype and of the N_mid assumption — the paper's one stated free parameter disappears.

    python scripts/s17_run_fitted_anchors.py             # one R1 arm; compares to final R0
    python scripts/s17_run_fitted_anchors.py --self-test
"""

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import fsolve

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(HERE))

OUTDIR    = REPO / "data" / "onsset_outputs"
RUN_LABEL = "2026-08_fittedanchor_lcoe"
R0_FINAL  = OUTDIR / "2026-08_final_lcoe_R0.csv"
YEAR      = 2030

RHO_1 = 3.98   # kept: Lorenzoni "Peak" archetype at N = 1

# The two calibration points. rho_inf and beta below are SOLVED from these, not read off either
# one directly (see WHY above for why that shortcut no longer holds). Only the first is a
# measurement; the second is Zambia's own planning assumption, not an independent observation.
ANCHOR_TUM_MEASURED         = (450.0, 1.80)      # Wassie & Ahlgren 2024, Tum mini-grid, residential
ANCHOR_ZAMBIA_LOAD_FACTOR   = (1.0e6, 1.4587)    # IRP Demand Assessment and Forecast Report,
                                                 # Table 3.01, 2020: 769 MW / 4,618 GWh, both
                                                 # generated from the IRP's stated 68.5% assumed
                                                 # national residential load factor (1/0.685 = 1.4599)
                                                 # -> NOT an independent measurement.


def calibrate_curve():
    """Solve rho_inf and beta simultaneously so the curve fits both calibration points exactly."""
    def equations(params):
        rho_inf, beta = params
        n1, r1 = ANCHOR_TUM_MEASURED
        n2, r2 = ANCHOR_ZAMBIA_LOAD_FACTOR
        return [rho_inf + (RHO_1 - rho_inf) * n1 ** (-beta) - r1,
                rho_inf + (RHO_1 - rho_inf) * n2 ** (-beta) - r2]

    (rho_inf, beta), info, ier, msg = fsolve(equations, x0=[1.0, 0.4], full_output=True)
    if ier != 1:
        raise RuntimeError(f"anchor calibration failed to converge: {msg}")
    return float(rho_inf), float(beta)


RHO_INF, BETA = calibrate_curve()


def rho_fitted(N):
    N = np.maximum(np.asarray(N, dtype=float), 1.0)
    return RHO_INF + (RHO_1 - RHO_INF) * N ** (-BETA)


def self_test():
    print("Self-test: the fitted curve must reproduce both calibration points exactly\n")
    print(f"  solved rho_inf = {RHO_INF:.5f}   solved beta = {BETA:.5f}")
    checks = [("Ethiopian residential mini-grid (measured)", *ANCHOR_TUM_MEASURED, 5e-3),
              ("Zambia IRP load-factor assumption", *ANCHOR_ZAMBIA_LOAD_FACTOR, 5e-3),
              ("Lorenzoni Peak archetype (kept)", 1.0, 3.98, 1e-9)]
    ok = True
    for name, n, expect, tol in checks:
        got = float(rho_fitted(n))
        good = abs(got - expect) < tol
        ok &= good
        print(f"  {name:<36} N={n:>9,.0f}  rho={got:.4f}  expect {expect:.2f}"
              f"  {'PASS' if good else 'FAIL'}")
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
