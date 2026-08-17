#!/usr/bin/env python3
"""Extract every headline number the paper quotes, from a pair of arm outputs.

Written 2026-08-16 to read the post-index-fix run. Compares against the
as-published values so the size of every change is visible at a glance.

    python scripts/s14_paper_numbers.py 2026-08_final_lcoe
"""
import sys
import pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "onsset_outputs"
YEAR = 2030

PUBLISHED = {
    "dlcoe": 36.872520, "switches": 17787, "sw_total": 18224,
    "r0_grid": 39058, "r0_sapv": 230581, "r0_hyb": 887,
    "r1_grid": 56831, "r1_sapv": 212452, "r1_hyb": 1243,
    "d_inv": -9.80, "d_cap": -9.96,
}
LABELS = {1: "Grid", 3: "SA_PV", 5: "MG_PVHybrid", 6: "MG_Wind", 7: "MG_Hydro", 99: "Unelectrified"}


def alignment_check(df):
    """Share of stand-alone PV settlements whose capacity matches E/(ATR*GHI)."""
    pred = df[f"EnergyPerSettlement{YEAR}"].to_numpy() / (
        df["AverageToPeakLoadRatio"].to_numpy() * df["GHI"].to_numpy())
    sa = df[f"FinalElecCode{YEAR}"].to_numpy() == 3
    return 100.0 * np.isclose(pred[sa], df[f"NewCapacity{YEAR}"].to_numpy()[sa], rtol=1e-6).mean()


def delta(new, old):
    return f"{new:+.2f}%" if old is None else f"{new:+.2f}%  (was {old:+.2f}%)"


def main(run_label):
    r0 = pd.read_csv(OUT / f"{run_label}_R0.csv")
    code, inv, cap = f"FinalElecCode{YEAR}", f"InvestmentCost{YEAR}", f"NewCapacity{YEAR}"
    lc, ec = f"MinimumOverallLCOE{YEAR}", f"EnergyPerSettlement{YEAR}"

    print("=" * 72)
    print(f"  PAPER NUMBERS — {run_label}")
    print("=" * 72)

    a0 = alignment_check(r0)
    print(f"\n  INDEX ALIGNMENT (R0): {a0:.3f}%   "
          f"{'PASS' if a0 > 99 else 'FAIL — do not use these outputs'}")
    if a0 <= 99:
        return 1

    for n_mid in (20, 10, 50):
        path = OUT / f"{run_label}_R1_n{n_mid}.csv"
        if not path.exists():
            print(f"\n  (R1 n{n_mid} not found — skipping)")
            continue
        r1 = pd.read_csv(path)
        central = n_mid == 20
        print("\n" + "-" * 72)
        print(f"  R0  vs  R1 (N_mid = {n_mid}){'   <- CENTRAL CASE' if central else ''}")
        print("-" * 72)
        print(f"  index alignment (R1): {alignment_check(r1):.3f}%")

        e = r0[ec].to_numpy()
        c0 = (r0[lc].to_numpy() * e).sum()
        c1 = (r1[lc].to_numpy() * e).sum()
        d = (c1 - c0) / c0 * 100.0
        print(f"\n  DeltaLCOE%  {d:+.4f}" + (f"      published +{PUBLISHED['dlcoe']:.4f}" if central else ""))

        f0, f1 = r0[code].to_numpy(), r1[code].to_numpy()
        print(f"\n  {'Technology':<16}{'R0 sett':>11}{'R1 sett':>11}{'R0 pop':>14}{'R1 pop':>14}")
        for k in (1, 3, 5, 6, 7, 99):
            m0, m1 = f0 == k, f1 == k
            if not (m0.any() or m1.any()):
                continue
            print(f"  {LABELS[k]:<16}{int(m0.sum()):>11,}{int(m1.sum()):>11,}"
                  f"{r0.loc[m0,'Pop'].sum():>14,.0f}{r1.loc[m1,'Pop'].sum():>14,.0f}")

        moved = f0 != f1
        sw = (f0 == 3) & (f1 == 1)
        print(f"\n  settlements changing technology : {int(moved.sum()):,}"
              + (f"   published {PUBLISHED['sw_total']:,}" if central else ""))
        print(f"  SA_PV -> Grid                   : {int(sw.sum()):,}"
              + (f"   published {PUBLISHED['switches']:,}" if central else ""))
        if moved.any():
            print("  full switching matrix (R0 row -> R1 col):")
            print(pd.crosstab(pd.Series(f0[moved], name="R0"),
                              pd.Series(f1[moved], name="R1")).rename(index=LABELS, columns=LABELS)
                  .to_string().replace("\n", "\n    "))
        pop_sw = r0.loc[sw, "Pop"].sum()
        print(f"\n  population on switching settlements: {pop_sw/1e6:.2f} M "
              f"({100*pop_sw/r0['Pop'].sum():.1f}% of national)")

        i0, i1 = r0[inv].sum(), r1[inv].sum()
        k0, k1 = r0[cap].sum(), r1[cap].sum()
        print(f"\n  investment  {i0/1e9:8.2f} -> {i1/1e9:8.2f} bn USD   "
              + delta(100*(i1/i0-1), PUBLISHED["d_inv"] if central else None))
        print(f"  capacity    {k0/1e3:8.0f} -> {k1/1e3:8.0f} MW        "
              + delta(100*(k1/k0-1), PUBLISHED["d_cap"] if central else None))

        print("\n  by technology (R1 arm):")
        print(f"  {'Technology':<16}{'invest bn':>12}{'capacity MW':>14}")
        for k in (1, 3, 5):
            m = f1 == k
            if m.any():
                print(f"  {LABELS[k]:<16}{r1.loc[m,inv].sum()/1e9:>12.2f}{r1.loc[m,cap].sum()/1e3:>14,.0f}")

        s0 = r0[f"SA_PV{YEAR}"].to_numpy(); s1 = r1[f"SA_PV{YEAR}"].to_numpy()
        v = (s0 < 90) & (s1 < 90)
        print(f"\n  median SA_PV LCOE   R0 {np.median(s0[v]):.4f} -> R1 {np.median(s1[v]):.4f}"
              f"   ({100*(np.median(s1[v])/np.median(s0[v])-1):+.1f}%)")
        g = r0[f"Grid{YEAR}"].to_numpy() < 90
        print(f"  median Grid  LCOE   R0 {np.median(r0.loc[g, f'Grid{YEAR}']):.4f} -> "
              f"R1 {np.median(r1.loc[g, f'Grid{YEAR}']):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-08_final_lcoe"))
