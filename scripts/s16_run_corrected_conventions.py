#!/usr/bin/env python3
"""
s16_run_corrected_conventions.py — the R0/R1 comparison under a corrected reinvestment schedule.

WHY THIS EXISTS
---------------
OnSSET books at most ONE reinvestment, at year `tech_life`, however long the analysis horizon, and
then applies a salvage term that turns NEGATIVE to compensate (`onsset.py`, `Technology.get_lcoe`).
Over the 16-year horizon used here a 5-year asset is installed at years 0 and 5 only, while its
generation is credited for all 16 years. Discounted at 8% the capital multiplier is

    OnSSET as written   2.0589      (installs at 0, 5;  salvage factor 1 - 11/5 = -1.2)
    full schedule       2.2068      (installs at 0, 5, 10, 15;  unused life of the last credited)

so stand-alone PV capital is understated by 7.19%.

The reason it matters here rather than being a general level effect is that it is
TECHNOLOGY-ASYMMETRIC. Grid has tech_life 30, longer than the horizon, so it reinvests under
neither convention and is understated by only 1.25% (an off-by-one in `used_life`). Stand-alone PV
is understated by 7.19%. The relative penalty on stand-alone against grid is therefore about 5.9%,
and stand-alone PV is the channel through which this study's entire measured effect travels:
scaling only part of stand-alone capital with peak collapses the headline from +45.4% at f = 1.0
to +19.1% at f = 0.4 (`s10`).

WHAT THIS SCRIPT DOES NOT DO
----------------------------
It changes the reinvestment schedule only. The central case deliberately keeps unmodified OnSSET
conventions so that it stays comparable with the GEP and Imasiku benchmarks the paper is measured
against. Other known upstream issues are disclosed rather than altered: the mini-grid hour-of-day
dispatch conflation (affects mini-grid levels only, and mini-grid LCOE is invariant between arms),
the three different investment-cost conventions summed into one total, and the inert grid-penalty
layer. See docs/01_pipeline.md.

    python scripts/s16_run_corrected_conventions.py            # R0 + R1_n20
    python scripts/s16_run_corrected_conventions.py --self-test
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

OUTDIR    = REPO / "data" / "onsset_outputs"
RUN_LABEL = "2026-08-16_reinvest_lcoe"
YEAR      = 2030


def capital_multiplier(tech_life, project_life, discount_rate, full):
    """Reproduce get_lcoe's investment/salvage arithmetic for one technology."""
    step = 0
    reinvest_year = tech_life + step if tech_life + step < project_life else 0
    inv = np.zeros(project_life)
    if full and tech_life > 0:
        years = list(range(step, project_life, int(tech_life)))
        for k in years:
            inv[k] = 1
        used_life = project_life - years[-1]
    else:
        inv[step] = 1
        if reinvest_year:
            inv[reinvest_year] = 1
        used_life = ((project_life - step) - tech_life) if reinvest_year > 0 \
            else (project_life - step - 1)
    salvage = np.zeros(project_life)
    salvage[-1] = 1
    factor = (1 + discount_rate) ** np.arange(project_life)
    return ((inv - salvage * (1 - used_life / tech_life)) / factor).sum()


def self_test():
    """Confirm the switch changes what it should and leaves the rest alone."""
    print("Self-test: capital multipliers over a 16-year horizon at 8%\n")
    ok = True
    rows = [("stand-alone PV", 5, 2.0589, 2.2068),
            ("mini-grid PV hybrid", 20, 0.9212, 0.9370),
            ("grid", 30, 0.8424, 0.8529)]
    print(f"  {'technology':<22}{'OnSSET':>10}{'corrected':>12}{'change':>10}")
    for name, tl, exp_off, exp_on in rows:
        a = capital_multiplier(tl, 16, 0.08, False)
        b = capital_multiplier(tl, 16, 0.08, True)
        good = abs(a - exp_off) < 5e-4 and abs(b - exp_on) < 5e-4
        ok &= good
        print(f"  {name:<22}{a:>10.4f}{b:>12.4f}{100*(b/a-1):>9.2f}%"
              f"{'' if good else '   <-- MISMATCH'}")
    rel = (capital_multiplier(5, 16, 0.08, True) / capital_multiplier(5, 16, 0.08, False)) / \
          (capital_multiplier(30, 16, 0.08, True) / capital_multiplier(30, 16, 0.08, False))
    print(f"\n  relative penalty on stand-alone PV against grid: {100*(rel-1):.2f}%")
    print("  PASS" if ok else "  FAIL")
    return 0 if ok else 1


def main():
    if "--self-test" in sys.argv:
        return self_test()

    import onsset
    from onsset_helpers import load_solar_profile, load_wind_profile, load_config
    from s06_run_arms import run_arm, PE_N20, TX_SHP, SOLAR_PROFILE, WIND_PROFILE
    from onsset import SettlementProcessor

    onsset.CORRECTED_CONVENTIONS["full_reinvestment"] = True
    assert onsset.CORRECTED_CONVENTIONS["full_reinvestment"] is True

    print("=" * 70)
    print("  Corrected-conventions variant — full reinvestment schedule")
    print("  stand-alone PV capital multiplier 2.0589 -> 2.2068  (+7.19%)")
    print("  grid                              0.8424 -> 0.8529  (+1.25%)")
    print("=" * 70)

    cfg = load_config()
    np.random.seed(42)
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))

    base = pd.read_csv(PE_N20)
    arms = [("R0", base.drop(columns=["PE_ratio", "N_hh"], errors="ignore"), None),
            ("R1_n20", base.drop(columns=["N_hh"], errors="ignore"), 20)]

    t0 = time.time()
    out = {}
    for label, df_arm, n_mid in arms:
        proc, _, _ = run_arm(label, df_arm, cfg, x_tx, y_tx,
                             ghi_profile, temp_profile, wind_profile, n_mid=n_mid)
        proc.df.sort_values("id", inplace=True)
        path = OUTDIR / f"{RUN_LABEL}_{label}.csv"
        proc.df.to_csv(path, index=False)
        out[label] = proc.df
        print(f"  {label} -> {path.name}")

    r0, r1 = out["R0"], out["R1_n20"]
    e = r0[f"EnergyPerSettlement{YEAR}"].to_numpy()
    c0 = (r0[f"MinimumOverallLCOE{YEAR}"].to_numpy() * e).sum()
    c1 = (r1[f"MinimumOverallLCOE{YEAR}"].to_numpy() * e).sum()
    f0, f1 = r0[f"FinalElecCode{YEAR}"].to_numpy(), r1[f"FinalElecCode{YEAR}"].to_numpy()
    hd, hs = central_headline()
    print("\n" + "=" * 70)
    print(f"  DeltaLCOE%              {(c1 - c0) / c0 * 100:+.2f}%      central case {hd:+.2f}%")
    print(f"  SA_PV -> grid switches  {int(((f0 == 3) & (f1 == 1)).sum()):,}"
          f"          central case {hs:,}")
    print(f"  investment  {r0[f'InvestmentCost{YEAR}'].sum()/1e9:.2f} -> "
          f"{r1[f'InvestmentCost{YEAR}'].sum()/1e9:.2f} bn")
    print(f"  R0 grid / SA_PV settlements  {int((f0==1).sum()):,} / {int((f0==3).sum()):,}"
          f"")
    print(f"  elapsed {(time.time() - t0)/60:.1f} min")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
