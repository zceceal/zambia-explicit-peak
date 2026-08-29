#!/usr/bin/env python3
"""Extract every headline number the paper quotes, from a pair of arm outputs.

Written 2026-08-16 to read the post-index-fix run; PUBLISHED updated 2026-08-23 to the
canonical 2026-08_final_lcoe values (the 2026-08-16 index-misalignment repair that produced
them changed the headline from +36.87% to +49.92% and settled the switch count at 34,461).
Compares against the as-published values so the size of every change is visible at a glance.

Writes every number it prints to results/summary/<run_label>_paper_numbers.csv (long format:
n_mid, quantity, value), so an assessor checking a number in the paper against results/summary/
alone does not have to re-run this script or read per-settlement outputs. The technology-split
and switching-population figures use Pop<YEAR> (the projected 2030 population), not the static
base-year Pop column that results/summary/<run_label>_tech_split.csv carries instead — that
distinction is why this script's own population figures should be preferred over that file's for
anything the paper states as a share of the 2030 population.

    python scripts/s14_paper_numbers.py 2026-08_final_lcoe
"""
import sys
import pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "onsset_outputs"
SUM = REPO / "results" / "summary"
YEAR = 2030

PUBLISHED = {
    "dlcoe": 49.923139, "switches": 34461, "sw_total": 34461,
    "r0_grid": 32058, "r0_sapv": 236843, "r0_hyb": 1625,
    "r1_grid": 66519, "r1_sapv": 202382, "r1_hyb": 1625,
    "d_inv": 45.591, "d_cap": 2.946,
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

    rows = [{"n_mid": "", "quantity": "index_alignment_r0_pct", "value": a0}]

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
        a1 = alignment_check(r1)
        print(f"  index alignment (R1): {a1:.3f}%")

        e = r0[ec].to_numpy()
        c0 = (r0[lc].to_numpy() * e).sum()
        c1 = (r1[lc].to_numpy() * e).sum()
        d = (c1 - c0) / c0 * 100.0
        lcoe0, lcoe1 = c0 / e.sum(), c1 / e.sum()
        print(f"\n  DeltaLCOE%  {d:+.4f}" + (f"      published +{PUBLISHED['dlcoe']:.4f}" if central else ""))
        print(f"  Energy-weighted LCOE, R0 {lcoe0:.4f} -> R1 {lcoe1:.4f} USD/kWh")
        rows.append({"n_mid": n_mid, "quantity": "index_alignment_r1_pct", "value": a1})
        rows.append({"n_mid": n_mid, "quantity": "delta_lcoe_pct", "value": d})
        rows.append({"n_mid": n_mid, "quantity": "energy_weighted_lcoe_r0_usd_per_kwh", "value": lcoe0})
        rows.append({"n_mid": n_mid, "quantity": "energy_weighted_lcoe_r1_usd_per_kwh", "value": lcoe1})

        f0, f1 = r0[code].to_numpy(), r1[code].to_numpy()
        pop_col = f"Pop{YEAR}"
        print(f"\n  {'Technology':<16}{'R0 sett':>11}{'R1 sett':>11}{'R0 pop':>14}{'R1 pop':>14}")
        for k in (1, 3, 5, 6, 7, 99):
            m0, m1 = f0 == k, f1 == k
            if not (m0.any() or m1.any()):
                continue
            print(f"  {LABELS[k]:<16}{int(m0.sum()):>11,}{int(m1.sum()):>11,}"
                  f"{r0.loc[m0,pop_col].sum():>14,.0f}{r1.loc[m1,pop_col].sum():>14,.0f}")
            rows.append({"n_mid": n_mid, "quantity": f"r0_settlements_{LABELS[k]}", "value": int(m0.sum())})
            rows.append({"n_mid": n_mid, "quantity": f"r1_settlements_{LABELS[k]}", "value": int(m1.sum())})
            rows.append({"n_mid": n_mid, "quantity": f"r0_pop{YEAR}_{LABELS[k]}", "value": r0.loc[m0,pop_col].sum()})
            rows.append({"n_mid": n_mid, "quantity": f"r1_pop{YEAR}_{LABELS[k]}", "value": r1.loc[m1,pop_col].sum()})

        moved = f0 != f1
        sw = (f0 == 3) & (f1 == 1)
        print(f"\n  settlements changing technology : {int(moved.sum()):,}"
              + (f"   published {PUBLISHED['sw_total']:,}" if central else ""))
        print(f"  SA_PV -> Grid                   : {int(sw.sum()):,}"
              + (f"   published {PUBLISHED['switches']:,}" if central else ""))
        rows.append({"n_mid": n_mid, "quantity": "settlements_changing_technology", "value": int(moved.sum())})
        rows.append({"n_mid": n_mid, "quantity": "sa_pv_to_grid_switches", "value": int(sw.sum())})
        if moved.any():
            print("  full switching matrix (R0 row -> R1 col):")
            print(pd.crosstab(pd.Series(f0[moved], name="R0"),
                              pd.Series(f1[moved], name="R1")).rename(index=LABELS, columns=LABELS)
                  .to_string().replace("\n", "\n    "))
        pop_sw = r0.loc[sw, pop_col].sum()
        pop_sw_pct = 100*pop_sw/r0[pop_col].sum()
        print(f"\n  population on switching settlements: {pop_sw/1e6:.2f} M "
              f"({pop_sw_pct:.1f}% of national)")
        rows.append({"n_mid": n_mid, "quantity": f"population_switching_pop{YEAR}", "value": pop_sw})
        rows.append({"n_mid": n_mid, "quantity": "population_switching_pct", "value": pop_sw_pct})

        i0, i1 = r0[inv].sum(), r1[inv].sum()
        k0, k1 = r0[cap].sum(), r1[cap].sum()
        d_inv, d_cap = 100*(i1/i0-1), 100*(k1/k0-1)
        print(f"\n  investment  {i0/1e9:8.2f} -> {i1/1e9:8.2f} bn USD   "
              + delta(d_inv, PUBLISHED["d_inv"] if central else None))
        print(f"  capacity    {k0/1e3:8.0f} -> {k1/1e3:8.0f} MW        "
              + delta(d_cap, PUBLISHED["d_cap"] if central else None))
        rows.append({"n_mid": n_mid, "quantity": "investment_r0_bn_usd", "value": i0/1e9})
        rows.append({"n_mid": n_mid, "quantity": "investment_r1_bn_usd", "value": i1/1e9})
        rows.append({"n_mid": n_mid, "quantity": "d_investment_pct", "value": d_inv})
        rows.append({"n_mid": n_mid, "quantity": "capacity_r0_mw", "value": k0/1e3})
        rows.append({"n_mid": n_mid, "quantity": "capacity_r1_mw", "value": k1/1e3})
        rows.append({"n_mid": n_mid, "quantity": "d_capacity_pct", "value": d_cap})

        print("\n  by technology (R0 arm):")
        print(f"  {'Technology':<16}{'invest bn':>12}{'capacity MW':>14}")
        for k in (1, 3, 5):
            m = f0 == k
            if m.any():
                print(f"  {LABELS[k]:<16}{r0.loc[m,inv].sum()/1e9:>12.2f}{r0.loc[m,cap].sum()/1e3:>14,.0f}")
                rows.append({"n_mid": n_mid, "quantity": f"r0_investment_bn_usd_{LABELS[k]}", "value": r0.loc[m,inv].sum()/1e9})
                rows.append({"n_mid": n_mid, "quantity": f"r0_capacity_mw_{LABELS[k]}", "value": r0.loc[m,cap].sum()/1e3})

        print("\n  by technology (R1 arm):")
        print(f"  {'Technology':<16}{'invest bn':>12}{'capacity MW':>14}")
        for k in (1, 3, 5):
            m = f1 == k
            if m.any():
                print(f"  {LABELS[k]:<16}{r1.loc[m,inv].sum()/1e9:>12.2f}{r1.loc[m,cap].sum()/1e3:>14,.0f}")
                rows.append({"n_mid": n_mid, "quantity": f"r1_investment_bn_usd_{LABELS[k]}", "value": r1.loc[m,inv].sum()/1e9})
                rows.append({"n_mid": n_mid, "quantity": f"r1_capacity_mw_{LABELS[k]}", "value": r1.loc[m,cap].sum()/1e3})

        s0 = r0[f"SA_PV{YEAR}"].to_numpy(); s1 = r1[f"SA_PV{YEAR}"].to_numpy()
        v = (s0 < 90) & (s1 < 90)
        med_sapv0, med_sapv1 = np.median(s0[v]), np.median(s1[v])
        print(f"\n  median SA_PV LCOE   R0 {med_sapv0:.4f} -> R1 {med_sapv1:.4f}"
              f"   ({100*(med_sapv1/med_sapv0-1):+.1f}%)")
        g = r0[f"Grid{YEAR}"].to_numpy() < 90
        med_grid0 = np.median(r0.loc[g, f"Grid{YEAR}"])
        med_grid1 = np.median(r1.loc[g, f"Grid{YEAR}"])
        print(f"  median Grid  LCOE   R0 {med_grid0:.4f} -> "
              f"R1 {med_grid1:.4f}")
        rows.append({"n_mid": n_mid, "quantity": "median_sa_pv_lcoe_r0", "value": med_sapv0})
        rows.append({"n_mid": n_mid, "quantity": "median_sa_pv_lcoe_r1", "value": med_sapv1})
        rows.append({"n_mid": n_mid, "quantity": "median_grid_lcoe_r0", "value": med_grid0})
        rows.append({"n_mid": n_mid, "quantity": "median_grid_lcoe_r1", "value": med_grid1})

    SUM.mkdir(parents=True, exist_ok=True)
    out_path = SUM / f"{run_label}_paper_numbers.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"\nSaved: {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-08_final_lcoe"))
