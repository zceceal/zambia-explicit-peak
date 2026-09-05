#!/usr/bin/env python3
"""
s15_run_capex_curve_sensitivity.py — how much of the headline is the cost schedule's staircase?

OnSSET prices stand-alone PV from a five-step schedule keyed on system size per household
(`Technology.capital_cost`, applied in `get_lcoe`):

      < 0.02 kW : 9620 USD/kW
   0.02-0.05 kW : 8780
   0.05-0.10 kW : 6380
   0.10-1.00 kW : 4470
      > 1.00 kW : 6950        <- note the reversal: larger systems cost MORE per kW

Explicit peak representation raises the per-household system from about 0.80 kW to about 1.21 kW
at rural Tier 3, so roughly 149,000 settlements step across that last boundary and their capital
cost jumps by a factor of 1.55 in one discrete move. Freezing the band at its R0 value puts the
headline at +21.8% rather than +45.4%, i.e. more than half of the effect is that single step.
At rural Tier 2 no settlement crosses any boundary and the effect is +1.9%.

This script re-runs the central comparison with the schedule replaced by a continuous curve, so
the discretisation can be separated from the physics with a measurement instead of an estimate.

    python scripts/s15_run_capex_curve_sensitivity.py smooth     # continuous, keeps the >1 kW premium
    python scripts/s15_run_capex_curve_sensitivity.py monotone   # continuous, premium removed
    python scripts/s15_run_capex_curve_sensitivity.py --self-test

`smooth` and `monotone` answer different questions:

  smooth    log-linear interpolation through the same anchor points, with the >1 kW premium
            reached smoothly by 3 kW. Same economics, no cliff. Isolates the DISCRETISATION.
  monotone  as smooth, but unit cost never rises with size (flat 4470 above 1 kW). Tests whether
            the economically anomalous >1 kW premium is load-bearing at all.

Nothing here touches the central case: `build_tech_objects` is wrapped for this process only, and
outputs are written under their own run label.
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
from onsset_helpers import central_headline

# Heavy imports (scipy, numba, the onsset package) are deferred into main() so that
# --self-test runs anywhere pandas is available.

OUTDIR    = REPO / "data" / "onsset_outputs"
RUN_LABEL = "2026-08-16_capex-"
CENTRAL   = OUTDIR / "2026-08_final_lcoe_R0.csv"  # self-test reference only; main() re-solves R0/R1 itself

# OnSSET's schedule, as (upper size bound in kW, USD/kW)
ONSSET_STEPS = [(0.020, 9620), (0.050, 8780), (0.100, 6380), (1.000, 4470), (float("inf"), 6950)]
PREMIUM_REACHED_AT = 3.0   # kW/household at which the >1 kW premium is fully reached ('smooth')
N_KNOTS = 400              # resolution of the dict that emulates a continuous curve


def price_at(size_kw, variant):
    """USD/kW for a stand-alone system of `size_kw` per household."""
    anchors = [(0.020, 9620.0), (0.050, 8780.0), (0.100, 6380.0), (1.000, 4470.0)]
    if variant == "step":
        for bound, p in ONSSET_STEPS:
            if size_kw < bound:
                return float(p)
        return float(ONSSET_STEPS[-1][1])
    if size_kw <= anchors[0][0]:
        return anchors[0][1]
    for (s0, p0), (s1, p1) in zip(anchors, anchors[1:]):
        if size_kw <= s1:
            w = (np.log(size_kw) - np.log(s0)) / (np.log(s1) - np.log(s0))
            return p0 + w * (p1 - p0)
    if variant == "monotone":
        return anchors[-1][1]
    s0, p0 = anchors[-1]
    if size_kw >= PREMIUM_REACHED_AT:
        return 6950.0
    w = (np.log(size_kw) - np.log(s0)) / (np.log(PREMIUM_REACHED_AT) - np.log(s0))
    return p0 + w * (6950.0 - p0)


def build_curve(variant):
    """A capital_cost dict fine enough to emulate a continuous curve.

    OnSSET assigns capital_cost[k] to every settlement whose per-household size is < k, scanning
    keys in ascending order, so a dense set of keys reproduces any f(size) to arbitrary accuracy
    without modifying onsset.py.
    """
    if variant == "step":
        return {b: p for b, p in ONSSET_STEPS}
    knots = np.exp(np.linspace(np.log(0.004), np.log(6.0), N_KNOTS))
    curve = {float(k): float(price_at(k * 0.999, variant)) for k in knots}
    curve[float("inf")] = float(price_at(10.0, variant))
    return curve


def self_test():
    """The emulated 'step' curve must reproduce OnSSET's own banding on the real run."""
    print("Self-test: emulated curve vs OnSSET's native schedule, on the central R0 output")
    df = pd.read_csv(CENTRAL, usecols=["EnergyPerSettlement2030", "AverageToPeakLoadRatio",
                                       "GHI", "Pop2030", "NumPeoplePerHH", "FinalElecCode2030"])
    hh   = np.maximum(df.Pop2030.to_numpy() / df.NumPeoplePerHH.to_numpy(), 1e-9)
    size = df.EnergyPerSettlement2030.to_numpy() / (
        df.AverageToPeakLoadRatio.to_numpy() * df.GHI.to_numpy()) / hh
    size = size[df.FinalElecCode2030.to_numpy() == 3]

    def assign(curve, s):
        out = np.zeros_like(s)
        for k in sorted(curve):
            out = np.where((s < k) & (out == 0), curve[k], out)
        return out

    native = assign({b: p for b, p in ONSSET_STEPS}, size)
    emul   = assign(build_curve("step"), size)
    agree  = 100.0 * (native == emul).mean()
    print(f"  settlements: {len(size):,}   agreement: {agree:.3f}%   "
          f"{'PASS' if agree > 99.9 else 'FAIL'}")
    for v in ("smooth", "monotone"):
        p = assign(build_curve(v), size)
        print(f"  {v:<9} median USD/kW {np.median(p):,.0f}  "
              f"(native {np.median(native):,.0f})   range {p.min():,.0f}-{p.max():,.0f}")
    return 0 if agree > 99.9 else 1


def main():
    if "--self-test" in sys.argv:
        return self_test()
    variant = sys.argv[1] if len(sys.argv) > 1 else "smooth"
    assert variant in ("smooth", "monotone", "step"), f"unknown variant {variant}"

    curve = build_curve(variant)

    print("=" * 68)
    print(f"  Stand-alone PV capital-cost curve sensitivity — variant '{variant}'")
    for s in (0.05, 0.3, 0.8, 1.0, 1.24, 2.0):
        print(f"    {s:>5.2f} kW/household -> ${price_at(s, variant):,.0f}/kW "
              f"(OnSSET: ${price_at(s, 'step'):,.0f}/kW)")
    print("=" * 68)

    from onsset_helpers import load_solar_profile, load_wind_profile, load_config
    import s06_run_arms as S6
    from s06_run_arms import run_arm, PE_N20, TX_SHP, SOLAR_PROFILE, WIND_PROFILE
    from onsset import SettlementProcessor

    _orig = S6.build_tech_objects

    def patched(cfg, start_year, end_year):
        techs = _orig(cfg, start_year, end_year)
        techs["sa_pv"].capital_cost = curve
        return techs

    S6.build_tech_objects = patched   # this process only

    cfg = load_config()
    np.random.seed(42)
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))

    base = pd.read_csv(PE_N20)
    df_r0 = base.drop(columns=["PE_ratio", "N_hh"], errors="ignore")
    df_r1 = base.drop(columns=["N_hh"], errors="ignore")

    t0 = time.time()
    out = {}
    for label, df_arm, n_mid in [("R0", df_r0, None), ("R1_n20", df_r1, 20)]:
        proc, _, _ = run_arm(label, df_arm, cfg, x_tx, y_tx,
                             ghi_profile, temp_profile, wind_profile, n_mid=n_mid)
        proc.df.sort_values("id", inplace=True)
        path = OUTDIR / f"{RUN_LABEL}{variant}_lcoe_{label}.csv"
        proc.df.to_csv(path, index=False)
        out[label] = proc.df
        print(f"  {label} -> {path.name}")

    r0, r1 = out["R0"], out["R1_n20"]
    e  = r0["EnergyPerSettlement2030"].to_numpy()
    c0 = (r0["MinimumOverallLCOE2030"].to_numpy() * e).sum()
    c1 = (r1["MinimumOverallLCOE2030"].to_numpy() * e).sum()
    sw = int(((r0["FinalElecCode2030"].to_numpy() == 3) &
              (r1["FinalElecCode2030"].to_numpy() == 1)).sum())
    print("\n" + "=" * 68)
    print(f"  variant '{variant}':  DeltaLCOE% = {(c1 - c0) / c0 * 100:+.2f}%   "
          f"SA_PV->grid switches = {sw:,}")
    hd, hs = central_headline()
    print(f"  central case (OnSSET step schedule): {hd:+.2f}%, {hs:,}")
    print(f"  band frozen at R0 (analytic estimate): +23.63%")
    print(f"  elapsed {(time.time() - t0) / 60:.1f} min")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
