#!/usr/bin/env python3
"""
s23_summarise_variants.py — machine-readable summary of the variants whose per-settlement outputs
are not committed: rural Tier 2, the 2050 horizon, the anchor-fitted curve, the capital-cost
schedule variants, the corrected replacement schedule and the single-household exclusion.

No re-solve: reads the per-settlement CSVs the earlier scripts wrote and applies s14's
energy-weighted formula (both arms weighted by the R0 energy column; 2050 uses s12c's finite mask).

    python scripts/s23_summarise_variants.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

REPO   = Path(__file__).resolve().parents[1]
OUT    = REPO / "data" / "onsset_outputs"
OUT50  = REPO / "scripts" / "outputs"
SPINE  = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"
SUMMARY = REPO / "results" / "summary" / "2026-09-02_variant_summaries.csv"

R0 = OUT / "2026-08_final_lcoe_R0.csv"
R1 = OUT / "2026-08_final_lcoe_R1_n20.csv"


def cols(year):
    return (f"MinimumOverallLCOE{year}", f"EnergyPerSettlement{year}",
            f"FinalElecCode{year}", f"InvestmentCost{year}", f"Technology{year}")


def load(path, year):
    lc, ec, code, inv, tech = cols(year)
    use = ["id", lc, ec, code, inv] + ([tech] if year == 2050 else [])
    return pd.read_csv(path, usecols=use)


def contrast(r0, r1, year, mask=None, finite_mask=False):
    lc, ec, code, inv, tech = cols(year)
    e, l0, l1 = r0[ec].to_numpy(), r0[lc].to_numpy(), r1[lc].to_numpy()
    m = np.ones(len(e), dtype=bool) if mask is None else mask.copy()
    if finite_mask:                       # s12c convention for the 2050 endpoint
        m &= np.isfinite(l0) & np.isfinite(l1) & np.isfinite(e) & (e > 0)
    d = (np.average(l1[m], weights=e[m]) / np.average(l0[m], weights=e[m]) - 1) * 100
    f0, f1 = r0[code].to_numpy(), r1[code].to_numpy()
    out = {"dlcoe_pct": d,
           "switches_sapv_grid": int(((f0 == 3) & (f1 == 1) & m).sum()),
           "switches_total": int(((f0 != f1) & m).sum())}
    if year == 2050:
        out["switches_total"] = int((r0[tech].to_numpy() != r1[tech].to_numpy()).sum())
    if inv in r0 and inv in r1:
        out["d_investment_pct"] = (r1[inv].to_numpy()[m].sum() / r0[inv].to_numpy()[m].sum() - 1) * 100
    return out


def main():
    rows = []
    r0, r1 = load(R0, 2030), load(R1, 2030)
    assert (r0["id"].to_numpy() == r1["id"].to_numpy()).all()

    # Rural Tier 2 (s07): both arms re-solved
    r0t2 = load(OUT / "2026-08_final_lcoe_R0_ruralT2.csv", 2030)
    for n in (10, 20, 50):
        r1t2 = load(OUT / f"2026-08_final_lcoe_R1_ruralT2_n{n}.csv", 2030)
        rows.append({"variant": "rural_tier2", "n_mid": n, **contrast(r0t2, r1t2, 2030)})

    # 2050 endpoint (s12): Tier 3 sweep and Tier 2 central
    r0_50 = load(OUT50 / "2050only_grid3_lcoe_R0.csv", 2050)
    for n in (10, 20, 50):
        r1_50 = load(OUT50 / f"2050only_grid3_lcoe_R1_n{n}.csv", 2050)
        rows.append({"variant": "horizon_2050_tier3", "n_mid": n,
                     **contrast(r0_50, r1_50, 2050, finite_mask=True)})
    r0_50t2 = load(OUT50 / "2050only_grid3_lcoe_R0_ruralT2.csv", 2050)
    r1_50t2 = load(OUT50 / "2050only_grid3_lcoe_R1_ruralT2_n20.csv", 2050)
    rows.append({"variant": "horizon_2050_tier2", "n_mid": 20,
                 **contrast(r0_50t2, r1_50t2, 2050, finite_mask=True)})

    # Anchor-fitted curve (s17): R1 only, against the canonical R0
    r1f = load(OUT / "2026-08_fittedanchor_lcoe_R1.csv", 2030)
    m = contrast(r0, r1f, 2030)
    sw_c = (r0[cols(2030)[2]].to_numpy() == 3) & (r1[cols(2030)[2]].to_numpy() == 1)
    sw_f = (r0[cols(2030)[2]].to_numpy() == 3) & (r1f[cols(2030)[2]].to_numpy() == 1)
    m["switchers_shared_with_central"] = int((sw_c & sw_f).sum())
    rows.append({"variant": "anchor_fitted", "n_mid": "fitted", **m})

    # Capital-cost schedule (s15) and corrected replacement schedule (s16): both arms re-solved
    for label, tag in [("capex_smooth", "capex-smooth"), ("capex_monotone", "capex-monotone"),
                       ("full_reinvestment", "reinvest")]:
        a = load(OUT / f"2026-08-16_{tag}_lcoe_R0.csv", 2030)
        b = load(OUT / f"2026-08-16_{tag}_lcoe_R1_n20.csv", 2030)
        rows.append({"variant": label, "n_mid": 20, **contrast(a, b, 2030)})

    # Single-household exclusion: central arms, settlements at the N = 1 floor removed post hoc
    nhh = pd.read_csv(SPINE, usecols=["id", "N_hh"]).set_index("id").loc[r0["id"], "N_hh"].to_numpy()
    keep = nhh > 1.0
    m = contrast(r0, r1, 2030, mask=keep)
    m["settlements_excluded"] = int((~keep).sum())
    rows.append({"variant": "single_household_excluded", "n_mid": 20, **m})

    rows.append({"variant": "central (published)", "n_mid": 20, **contrast(r0, r1, 2030)})

    df = pd.DataFrame(rows)
    df.to_csv(SUMMARY, index=False)
    print(df.to_string(index=False))
    print(f"\nwrote {SUMMARY.relative_to(REPO)}")


if __name__ == "__main__":
    main()
