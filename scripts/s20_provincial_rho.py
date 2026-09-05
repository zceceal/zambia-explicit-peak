"""
s20_provincial_rho.py

Post-hoc provincial peak-to-mean comparison, computed from the canonical 2026-08_final R1_n20
output. NO model re-solve: every quantity below is derived from the already-written per-settlement
result file.

WHY
---
Section 4.4 makes a provincial argument against Zambia's Rural Electrification Master Plan (REMP):
the Plan assigns essentially the same peak per connection to every province, whereas this model's
per-settlement coincidence curve separates them sharply. Three numbers carry that argument — the
modelled provincial range, its spread, and the Plan's own spread — and this script is where all
three are computed. The REMP figures below (§ "REMP TABLE 9") are transcribed by hand from the
Rural Electrification Master Plan for Zambia 2025-2030 (Rural Electrification Authority), Table 9
(page 33) and Table 1 (pages 9-10), not machine-read from the PDF; both tables were checked
digit-for-digit against the source before being embedded here.

WHAT THIS COMPUTES
-------------------
  (1) Provincial peak-to-mean ratios, population-weighted at 2030:
          rho_province = sum_i(PE_ratio_i * Pop2030_i) / sum_i(Pop2030_i)      grouped by Admin_1
  (2) The same, household-weighted, with households = Pop2030 / NumPeoplePerHH.
  (3) The spread, against the AGGREGATE weighted mean over all settlements (rho_national), not
      the unweighted mean of the ten provincial values:
          spread_pct = 100 * ((rho_max - rho_min) / 2) / rho_national
      The two bases differ by about 1.1 pp here, and only the aggregate basis is comparable with
      the Master Plan's own spread. Both are emitted, labelled.
  (4) The Master Plan's own spread, on that same aggregate-mean basis, from the embedded REMP Table
      9 figures (watts per connection = Demand_kW * 1000 / Connections).
  (5) The ratio of the two spreads.

Isolation: reads data/onsset_outputs/2026-08_final_lcoe_R1_n20.csv only. Writes only into
results/summary/. Never touches data/processed/ or data/onsset_outputs/. No re-solve, no model
call, no network access.

Usage:  python scripts/s20_provincial_rho.py
"""

from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "data" / "onsset_outputs"
SUM = REPO / "results" / "summary"
R1_PATH = OUT / "2026-08_final_lcoe_R1_n20.csv"
OUT_CSV = SUM / "2026-08_final_provincial_rho.csv"

# Rural-median rho at two horizons, quoted directly in the paper (§4.4) but not printed by any
# other committed script. IsUrban == 0 is rural on this spine (== 2 is urban, 176 settlements;
# see check_spine_integrity.py's "urban classification plausible" check).
RURAL_2050_SPINE = REPO / "data" / "processed" / "zambia_grid3_spine_pe_2050_n20.csv"

# ── REMP Table 9: grid development results by province ──────────────────────────────────────────
# Source: Rural Electrification Master Plan for Zambia 2025-2030, Table 9 "Grid development
# project results summarized by province", p.33. Transcribed by hand; checked against the PDF
# digit-for-digit before being embedded here (all twenty figures matched).
REMP_TABLE9 = {
    #                connections  demand_kW
    "Central":       (56_212,     11_136),
    "Copperbelt":    (65_998,     12_645),
    "Eastern":       (218_793,    41_929),
    "Luapula":       (67_925,     13_110),
    "Lusaka":        (25_627,     5_041),
    "Muchinga":      (67_357,     12_663),
    "Northern":      (52_443,     10_253),
    "North-Western": (93_608,     17_885),
    "Southern":      (48_987,     9_654),
    "Western":       (42_610,     8_328),
}

# REMP Table 1 "Population Density by Province", 2022 column, people per sq.km, p.9-10. Quoted in
# §4.4 alongside the 10.1-140.1 range. Not used in any calculation below; carried for reference.
REMP_TABLE1_DENSITY_2022 = {
    "Central":       23.9,
    "Copperbelt":    88.0,
    "Eastern":       35.6,
    "Luapula":       29.9,
    "Lusaka":        140.1,
    "Muchinga":      13.1,
    "Northern":      20.8,
    "North-Western": 10.1,
    "Southern":      27.7,
    "Western":       10.8,
}


def weighted_mean(values, weights):
    return (values * weights).sum() / weights.sum()


def spread_pct(rho_max, rho_min, rho_basis):
    """Half-range as a percentage of rho_basis. rho_basis must be the AGGREGATE weighted mean —
    see WHY above for why the unweighted mean of provincial values is not a valid basis here."""
    return 100.0 * ((rho_max - rho_min) / 2.0) / rho_basis


def main():
    print("=" * 72)
    print("  s20 — provincial peak-to-mean comparison vs REMP Table 9")
    print("=" * 72)

    if not R1_PATH.exists():
        print(f"  missing {R1_PATH.name} — run s06 first")
        return 1

    df = pd.read_csv(R1_PATH, usecols=["Admin_1", "PE_ratio", "Pop2030", "NumPeoplePerHH"])
    df["HH2030"] = df["Pop2030"] / df["NumPeoplePerHH"]
    print(f"\n  Loaded {len(df):,} settlements, {df['Admin_1'].nunique()} provinces, from "
          f"{R1_PATH.name} (no re-solve)")

    # ── (1) + (2) provincial rho, both weightings ────────────────────────────────────────────
    rows = []
    for prov, g in df.groupby("Admin_1"):
        rho_pop = weighted_mean(g["PE_ratio"].values, g["Pop2030"].values)
        rho_hh = weighted_mean(g["PE_ratio"].values, g["HH2030"].values)
        conn, demand_kw = REMP_TABLE9[prov]
        rows.append({
            "Admin_1": prov,
            "rho_pop_weighted_2030": rho_pop,
            "rho_hh_weighted_2030": rho_hh,
            "population_density_2022_per_km2": REMP_TABLE1_DENSITY_2022[prov],
            "remp_connections": conn,
            "remp_demand_kW": demand_kw,
            "remp_watts_per_connection": demand_kw * 1000.0 / conn,
        })
    prov_df = pd.DataFrame(rows).sort_values("rho_pop_weighted_2030").reset_index(drop=True)

    # ── national aggregate means (over ALL settlements, not the unweighted mean of provinces) ──
    rho_national_pop = weighted_mean(df["PE_ratio"].values, df["Pop2030"].values)
    rho_national_hh = weighted_mean(df["PE_ratio"].values, df["HH2030"].values)

    rho_max_pop, rho_min_pop = prov_df["rho_pop_weighted_2030"].max(), prov_df["rho_pop_weighted_2030"].min()
    rho_max_hh, rho_min_hh = prov_df["rho_hh_weighted_2030"].max(), prov_df["rho_hh_weighted_2030"].min()

    spread_pop_aggregate = spread_pct(rho_max_pop, rho_min_pop, rho_national_pop)
    spread_pop_unweighted_provinces = spread_pct(
        rho_max_pop, rho_min_pop, prov_df["rho_pop_weighted_2030"].mean())
    spread_hh_aggregate = spread_pct(rho_max_hh, rho_min_hh, rho_national_hh)

    # ── (4) REMP's own spread, same basis ────────────────────────────────────────────────────
    remp_total_conn = prov_df["remp_connections"].sum()
    remp_total_demand_kw = prov_df["remp_demand_kW"].sum()
    remp_national_wpc = remp_total_demand_kw * 1000.0 / remp_total_conn
    remp_max_wpc = prov_df["remp_watts_per_connection"].max()
    remp_min_wpc = prov_df["remp_watts_per_connection"].min()
    remp_spread = spread_pct(remp_max_wpc, remp_min_wpc, remp_national_wpc)

    # ── (5) ratio of spreads ─────────────────────────────────────────────────────────────────
    ratio = spread_pop_aggregate / remp_spread

    # ── rural median rho, 2030 and 2050 ──────────────────────────────────────────────────────
    rural_2030 = pd.read_csv(R1_PATH, usecols=["IsUrban", "PE_ratio"])
    rural_median_2030 = rural_2030.loc[rural_2030["IsUrban"] == 0, "PE_ratio"].median()
    rural_median_2050 = None
    if RURAL_2050_SPINE.exists():
        rural_2050 = pd.read_csv(RURAL_2050_SPINE, usecols=["IsUrban", "PE_ratio"])
        rural_median_2050 = rural_2050.loc[rural_2050["IsUrban"] == 0, "PE_ratio"].median()

    # ── print, in the style of the other s-scripts ───────────────────────────────────────────
    print(f"\n  Population-weighted rho, by province (2030):")
    for _, r in prov_df.iterrows():
        print(f"    {r['Admin_1']:<15} rho_pop={r['rho_pop_weighted_2030']:.4f}  "
              f"rho_hh={r['rho_hh_weighted_2030']:.4f}  "
              f"density_2022={r['population_density_2022_per_km2']:.1f}/km2")

    print(f"\n  National aggregate mean (pop-weighted):  {rho_national_pop:.4f}")
    print(f"  National aggregate mean (hh-weighted):   {rho_national_hh:.4f}")
    print(f"  Range (pop-weighted): {rho_min_pop:.4f} ({prov_df.iloc[0]['Admin_1']}) to "
          f"{rho_max_pop:.4f} ({prov_df.iloc[-1]['Admin_1']})")
    print(f"  Half-range: {(rho_max_pop - rho_min_pop) / 2:.4f}")
    print(f"\n  spread_pct, pop-weighted, AGGREGATE-MEAN basis:      {spread_pop_aggregate:+.2f}%")
    print(f"  spread_pct, pop-weighted, unweighted-provinces basis: {spread_pop_unweighted_provinces:+.2f}%"
          f"   (differs by {spread_pop_aggregate - spread_pop_unweighted_provinces:+.2f} pp — "
          f"NOT the basis used for the headline claim)")
    print(f"  spread_pct, hh-weighted, AGGREGATE-MEAN basis:       {spread_hh_aggregate:+.2f}%")

    remp_min_prov = prov_df.loc[prov_df["remp_watts_per_connection"].idxmin(), "Admin_1"]
    remp_max_prov = prov_df.loc[prov_df["remp_watts_per_connection"].idxmax(), "Admin_1"]
    print(f"\n  REMP Table 9: {remp_min_wpc:.1f} W ({remp_min_prov}) to "
          f"{remp_max_wpc:.1f} W ({remp_max_prov}), aggregate mean {remp_national_wpc:.1f} W")
    print(f"  REMP spread_pct (aggregate-mean basis): {remp_spread:+.2f}%")
    print(f"\n  Ratio of spreads (model / REMP): {ratio:.2f}")

    print(f"\n  Rural median rho, IsUrban==0:")
    print(f"    2030 (R1_n20): {rural_median_2030:.4f}")
    if rural_median_2050 is not None:
        print(f"    2050 (pe_2050_n20 spine): {rural_median_2050:.4f}")
    else:
        print(f"    2050: SKIPPED — {RURAL_2050_SPINE.name} not found")

    # ── write output ──────────────────────────────────────────────────────────────────────────
    SUM.mkdir(parents=True, exist_ok=True)
    prov_df.to_csv(OUT_CSV, index=False)

    summary_rows = [
        {"quantity": "rho_national_pop_weighted_2030", "value": rho_national_pop},
        {"quantity": "rho_national_hh_weighted_2030", "value": rho_national_hh},
        {"quantity": "spread_pct_pop_weighted_aggregate_basis", "value": spread_pop_aggregate},
        {"quantity": "spread_pct_pop_weighted_unweighted_provinces_basis", "value": spread_pop_unweighted_provinces},
        {"quantity": "spread_pct_hh_weighted_aggregate_basis", "value": spread_hh_aggregate},
        {"quantity": "remp_national_watts_per_connection", "value": remp_national_wpc},
        {"quantity": "remp_spread_pct", "value": remp_spread},
        {"quantity": "ratio_of_spreads_model_over_remp", "value": ratio},
        {"quantity": "rural_median_rho_2030", "value": rural_median_2030},
        {"quantity": "rural_median_rho_2050", "value": rural_median_2050},
    ]
    summary_path = SUM / "2026-08_final_provincial_rho_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)

    print(f"\n  Saved: {OUT_CSV.name}")
    print(f"  Saved: {summary_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
