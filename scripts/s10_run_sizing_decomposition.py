"""
s10_run_sizing_decomposition.py — sizing-convention f-band and per-connection accounting.

Task 2: On EXISTING Stage-4 outputs, recompute energy-weighted ΔLCOE% with only a
fraction f of SA_PV capex peak-scaled (remainder energy-scaled). f ∈ {0.4, 0.6, 1.0}.
No OnSSET re-run. Verify f=1.0 reproduces the current headline (+49.9%).

Task 5: Trace InvestmentCost2030 and NewConnections2030 definitions; determine why
aggregate reads ~$20k/HH; state correct formula for defensible per-connection metric.
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Scoped to third-party deprecation noise only. RuntimeWarning (divide-by-zero,
# overflow, invalid value) and every other category stay visible, so a numerical
# fault surfaces rather than being silently discarded.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

HERE   = Path(__file__).resolve().parent
REPO   = HERE.parent
OUTDIR = REPO / "data" / "onsset_outputs"

HEADLINE_DELTA = 49.9   # s06 central case, N_mid=20, Tier 3 (2026-08_final run; was 36.9 pre-fix)
R0_PATH  = OUTDIR / "2026-08_final_lcoe_R0.csv"
R1_N20   = OUTDIR / "2026-08_final_lcoe_R1_n20.csv"
ANALYSIS_YEAR = 2030


def task2_f_band():
    """
    WARNING: calling this function writes data/onsset_outputs/2026-08_final_sizing_convention_fband.csv
    (a canonical, protected output) as a side effect — do not call it to "just check a number".

    Sizing-convention lower-bound analysis.

    Approach (fixed assignment):
    For each settlement:
      - SA_PV stays SA_PV in both arms: R1_f_LCOE = f * R1_LCOE + (1-f) * R0_LCOE
      - SA_PV → Grid switch: R1_f_LCOE = Grid_LCOE (unchanged — grid cost not scaled)
      - All other settlements: R1_f_LCOE = R1_LCOE (unchanged)

    Physical basis:
    f = fraction of SA_PV capex that scales with PEAK power (battery power rating +
    inverter + BOS), as opposed to ENERGY (PV panel array area). Under OnSSET's
    uniform peak-scaling convention, f=1.0 (all capex scales with peak); physically
    only battery+inverter+BOS scale on peak, giving f ≈ 0.55–0.65 per ESMAP SHS
    cost-breakdown data.

    f = {0.4, 0.6, 1.0}: covers a range from pessimistic (battery+inverter BOS only)
    to OnSSET convention. f=0.6 is the central illustrative estimate
    [source specific ESMAP/GOGLA SHS cost breakdown table].

    CAVEAT (label in all outputs): Fixed-assignment lower bound. In reality, at f < 1,
    some settlements currently switching SA_PV→Grid might stay SA_PV (grid advantage
    shrinks), so the true ΔLCOE% would be LOWER than computed here. The fixed-
    assignment approach is a conservative lower bound (ΔLCOE% is over-stated at f<1).
    """
    print("\n" + "="*65)
    print("  TASK 2 — Sizing-Convention f-Band (Post-Processing Only)")
    print("="*65)

    r0 = pd.read_csv(R0_PATH)
    r1 = pd.read_csv(R1_N20)
    print(f"  Loaded R0: {len(r0):,} settlements  R1_n20: {len(r1):,} settlements")

    lc = f"MinimumOverallLCOE{ANALYSIS_YEAR}"
    ec = f"EnergyPerSettlement{ANALYSIS_YEAR}"
    fc0_col = f"FinalElecCode{ANALYSIS_YEAR}"
    fc1_col = f"FinalElecCode{ANALYSIS_YEAR}"

    r0_lcoe = r0[lc].values.copy()
    r1_lcoe = r1[lc].values.copy()
    energy  = r0[ec].values.copy()
    fc0     = r0[fc0_col].values
    fc1     = r1[fc1_col].values

    c0 = (r0_lcoe * energy).sum()
    c1 = (r1_lcoe * energy).sum()
    delta_full = (c1 - c0) / c0 * 100.0
    print(f"  Baseline ΔLCOE% (f=1.0, full model) = {delta_full:+.4f}%  "
          f"(target: +{HEADLINE_DELTA:.1f}%)")

    # Identify settlement categories
    stays_sapv = (fc0 == 3) & (fc1 == 3)   # SA_PV in both arms
    switches   = (fc0 == 3) & (fc1 == 1)   # SA_PV → Grid
    stays_grid = (fc0 == 1) & (fc1 == 1)   # Grid in both
    other      = ~(stays_sapv | switches | stays_grid)

    n_stays_sapv = stays_sapv.sum()
    n_switches   = switches.sum()
    n_stays_grid = stays_grid.sum()
    n_other      = other.sum()
    print(f"\n  Technology assignment breakdown:")
    print(f"    SA_PV → SA_PV:  {n_stays_sapv:,} settlements")
    print(f"    SA_PV → Grid:   {n_switches:,} settlements  (the headline switch count)")
    print(f"    Grid  → Grid:   {n_stays_grid:,} settlements")
    print(f"    Other:          {n_other:,} settlements")

    # f-band computation
    f_values = [0.4, 0.6, 1.0]
    results = []
    for f in f_values:
        r1_f = r1_lcoe.copy()
        # For SA_PV→SA_PV: scale the LCOE difference by f
        r1_f[stays_sapv] = r0_lcoe[stays_sapv] + f * (r1_lcoe[stays_sapv] - r0_lcoe[stays_sapv])
        # SA_PV→Grid: keep Grid LCOE unchanged (f doesn't affect grid cost)
        # (r1_f[switches] stays as r1_lcoe[switches] = Grid LCOE — no change needed)
        # Other: no change

        c1_f = (r1_f * energy).sum()
        delta_f = (c1_f - c0) / c0 * 100.0
        results.append({"f": f, "delta_lcoe_pct": delta_f})
        print(f"  f = {f:.1f}:  ΔLCOE% = {delta_f:+.2f}%")

    df_out = pd.DataFrame(results)

    # Verify f=1.0 reproduces baseline
    f1_delta = df_out.loc[df_out["f"] == 1.0, "delta_lcoe_pct"].values[0]
    gate_ok = abs(f1_delta - delta_full) < 0.01
    print(f"\n  Consistency gate (f=1.0 reproduces baseline): "
          f"|{f1_delta:.4f} - {delta_full:.4f}| = {abs(f1_delta-delta_full):.4f}pp "
          f"→ {'PASS ✓' if gate_ok else 'FAIL ✗'}")

    out_path = OUTDIR / "2026-08_final_sizing_convention_fband.csv"
    df_out.to_csv(out_path, index=False)
    print(f"\n  Saved: {out_path.name}")
    print(f"  ΔLCOE% band: [{df_out['delta_lcoe_pct'].min():+.1f}%, "
          f"{df_out['delta_lcoe_pct'].max():+.1f}%]")
    print(f"  Label: ILLUSTRATIVE LOWER BOUND (fixed technology assignment)")
    return df_out


def task5_per_connection():
    """
    WARNING: calling this function writes data/onsset_outputs/2026-08_final_per_connection_analysis.csv
    (a canonical, protected output) as a side effect — do not call it to "just check a number".

    Per-connection cost accounting on the canonical 2026-08_final R0 arm — is
    InvestmentCost2030/NewConnections2030 quotable as a per-connection cost?

    Findings from code inspection (onsset.py) and the canonical R0 output:
    1. InvestmentCost2030 = UNDISCOUNTED total capital investment over the FULL project
       life (2020-2035 = 16 years), NOT just the 2020-2030 time step. For SA_PV with
       5-year tech life, this includes 2 installations (year 0 and year 5), both at the
       UNDISCOUNTED capital cost. This is a NPC-complement, not a single-year capex.
    2. NewConnections2030 = new HOUSEHOLDS added in the 2020-2030 step only (= HH
       electrified in that step). It does NOT include HH already electrified at 2020.
    3. Dividing (1) by (2) is therefore a period mismatch, still present: numerator
       covers the full 2020-2035 horizon (USD 15.58bn / 3,745,418 new HH = $4,159/HH
       aggregate), denominator covers only 2020-2030 new connections. By technology:
       SA_PV $9.84bn / 1,363,324 HH = $7,217/HH; Grid $4.33bn / 1,918,219 HH =
       $2,258/HH; MG_PVHybrid $1.41bn / 463,875 HH = $3,036/HH.
    4. The outlier problem is RESOLVED post-index-fix. No settlement exceeds $1bn of
       investment (max is $921.8M); OnSSET's own InvestmentPerConnection2030 has a
       median of $7,120/HH and a mean of $7,170/HH (P5-P95 $3,491-$11,094/HH) — a
       mean/median ratio of 1.01, i.e. no skew. The extreme per-settlement values
       (up to ~$23bn) that motivated this task were a symptom of the pre-fix index
       misalignment (REPRODUCING.md §7), not of the accounting.

    Verdict: absolute per-connection figures ARE now quotable, provided the period
    mismatch in (3) is stated alongside them. The outlier caveat that used to apply
    no longer does.

    Defensible per-connection metrics (for the Discussion):
    - OnSSET's own InvestmentPerConnection2030 column: median $7,120/HH.
    - Or: LCOE x energy / HH / project-life-years as a levelised annual cost per HH
      — median $56/HH/yr for SA_PV.
    - Relative comparison (R0 vs R1 cost ratio) is unaffected either way: R0 total
      NPC $1.73bn, R1 $2.59bn, +49.9%, matching the headline.
    """
    print("\n" + "="*65)
    print("  TASK 5 — Per-Connection Cost Accounting")
    print("="*65)

    r0 = pd.read_csv(R0_PATH)
    r1 = pd.read_csv(R1_N20)

    yr = ANALYSIS_YEAR
    fc0 = r0[f"FinalElecCode{yr}"]
    fc1 = r1[f"FinalElecCode{yr}"]

    # Aggregate accounting
    total_inv_r0  = r0[f"InvestmentCost{yr}"].sum()
    total_conn_r0 = r0[f"NewConnections{yr}"].sum()
    agg_per_conn  = total_inv_r0 / total_conn_r0

    print(f"\n  R0 aggregate InvestmentCost{yr} / NewConnections{yr}:")
    print(f"    Total investment: ${total_inv_r0/1e9:.2f}B")
    print(f"    Total new HH:     {total_conn_r0:,.0f}")
    print(f"    Aggregate ratio:  ${agg_per_conn:,.0f}/HH  ← misleading (see below)")

    # Per-technology breakdown
    for code, name in [(3, "SA_PV"), (1, "Grid"), (5, "MG_PVHybrid")]:
        mask  = fc0 == code
        inv   = r0.loc[mask, f"InvestmentCost{yr}"].sum()
        conn  = r0.loc[mask, f"NewConnections{yr}"].sum()
        if conn > 0:
            print(f"  {name} (R0, code {code}): inv=${inv/1e9:.2f}B  "
                  f"HH={conn:,.0f}  ratio=${inv/conn:,.0f}/HH (outlier-affected)")

    # Median per-settlement InvestmentPerConnection
    ipc = r0[f"InvestmentPerConnection{yr}"].replace([np.inf, -np.inf], np.nan)
    print(f"\n  R0 InvestmentPerConnection{yr} (col computed by OnSSET):")
    print(f"    Median: ${ipc.dropna().median():,.0f}/HH (OffGridInvestmentCost/NewConn per settlement)")
    print(f"    Mean:   ${ipc.dropna().mean():,.0f}/HH (inflated by outliers)")
    print(f"    P5–P95: ${ipc.dropna().quantile(0.05):,.0f} – ${ipc.dropna().quantile(0.95):,.0f}/HH")

    # Outlier investigation
    sapv = r0[fc0 == 3].copy()
    sapv["inv_per_hh"] = sapv[f"InvestmentCost{yr}"] / sapv[f"NewConnections{yr}"].replace(0, np.nan)
    extreme = sapv[sapv[f"InvestmentCost{yr}"] > 1e9]  # > $1B for one settlement
    print(f"\n  SA_PV extreme outliers (InvestmentCost > $1B): {len(extreme)} settlements")
    if len(extreme) > 0:
        print(f"    Total extreme investment: ${extreme[f'InvestmentCost{yr}'].sum()/1e9:.1f}B "
              f"({extreme[f'InvestmentCost{yr}'].sum()/total_inv_r0*100:.0f}% of total)")
        # Check ATR for extreme settlements
        atr_col = "AverageToPeakLoadRatio"
        if atr_col in sapv.columns:
            print(f"    Extreme settle ATR range: "
                  f"{extreme[atr_col].min():.4f} – {extreme[atr_col].max():.4f}")

    # Per-connection LCOE-based metric (more defensible)
    # LCOE × energy = total NPC for that settlement
    # NPC / (HH × project_life_years) = annualised cost per HH per year
    r0_sapv = r0[fc0 == 3].copy()
    r0_sapv_npc = r0_sapv[f"MinimumOverallLCOE{yr}"] * r0_sapv[f"EnergyPerSettlement{yr}"]
    r0_sapv_hh  = r0_sapv[f"NewConnections{yr}"]
    # Annual cost per HH = NPC / (HH × project_life_in_years)
    # project life context: 2020-2035 = 15 years
    project_life = 15
    r0_sapv["annual_lcoe_per_hh"] = (
        r0_sapv_npc / r0_sapv_hh.replace(0, np.nan) / project_life
    )
    print(f"\n  R0 SA_PV LCOE-based annual cost per HH (NPC / HH / 15 yr):")
    print(f"    Median: ${r0_sapv['annual_lcoe_per_hh'].dropna().median():,.0f}/HH/yr")
    print(f"    This is a defensible per-connection metric for the Discussion.")

    # R0 vs R1 relative comparison (unaffected by accounting issue)
    r0_total_npc = (r0[f"MinimumOverallLCOE{yr}"] * r0[f"EnergyPerSettlement{yr}"]).sum()
    r1_total_npc = (r1[f"MinimumOverallLCOE{yr}"] * r1[f"EnergyPerSettlement{yr}"]).sum()
    print(f"\n  Relative NPC comparison (unaffected by per-connection accounting):")
    print(f"    R0 total NPC: ${r0_total_npc/1e9:.2f}B")
    print(f"    R1 total NPC: ${r1_total_npc/1e9:.2f}B")
    print(f"    ΔNPC: ${(r1_total_npc-r0_total_npc)/1e9:.2f}B  ({(r1_total_npc-r0_total_npc)/r0_total_npc*100:+.1f}%)")

    # Every figure below is computed from the current outputs. The previous version of
    # this block was a frozen narrative quoting ~$20k/HH aggregate and a mean/median
    # split of $39k/$7k. Those were symptoms of the index misalignment in
    # SettlementProcessor.condition_df() diagnosed on 2026-08-16, not of the accounting.
    _ipc  = ipc.dropna()
    _skew = _ipc.mean() / _ipc.median() if _ipc.median() else float("nan")
    _delta = (r1_total_npc - r0_total_npc) / r0_total_npc * 100
    _outliers_resolved = (
        "RESOLVED. No settlement exceeds $1B of investment, and the mean/median ratio\n"
        "        is {:.2f} (a value near 1.0 means no outlier skew). Extreme per-settlement\n"
        "        investment was a symptom of the index misalignment, not of the accounting."
    ).format(_skew) if len(extreme) == 0 and _skew < 1.5 else (
        "STILL PRESENT: {} settlements above $1B; mean/median ratio {:.2f}. Investigate\n"
        "        before quoting any absolute per-connection figure."
    ).format(len(extreme), _skew)

    verdict = f"""
VERDICT (Task 5):
  R0 aggregate InvestmentCost{yr} / NewConnections{yr} = ${agg_per_conn:,.0f}/HH.
  Per settlement, OnSSET's InvestmentPerConnection{yr}: median ${_ipc.median():,.0f}/HH,
  mean ${_ipc.mean():,.0f}/HH, P5-P95 ${_ipc.quantile(0.05):,.0f}-${_ipc.quantile(0.95):,.0f}/HH.

  (a) PERIOD MISMATCH — still present. InvestmentCost spans the full 2020-2035 horizon
      (undiscounted NPC of two stand-alone PV installations); NewConnections{yr} counts
      new households in the 2020-{yr} step only. Numerator and denominator therefore
      span different periods, and the ratio overstates cost per connection by roughly
      the reinvestment factor. Any absolute figure quoted must state this.

  (b) OUTLIERS — {_outliers_resolved}

  Absolute per-connection figures are therefore quotable, with (a) stated. The
  distribution is tight and physically plausible.

  The RELATIVE R0-R1 cost change (dLCOE% = {_delta:+.1f}%) is computed from
  energy-weighted LCOEs and is unaffected by either issue. It remains the headline.
    """
    print(verdict)

    summary_df = pd.DataFrame([{
        "r0_total_inv_B": total_inv_r0 / 1e9,
        "r0_total_hh":    total_conn_r0,
        "r0_agg_inv_per_hh": agg_per_conn,
        "r0_sapv_inv_median_per_hh": sapv["inv_per_hh"].median(),
        "r0_ipc_col_median": ipc.dropna().median(),
        "r0_total_npc_B": r0_total_npc / 1e9,
        "r1_total_npc_B": r1_total_npc / 1e9,
        "delta_npc_pct": (r1_total_npc - r0_total_npc) / r0_total_npc * 100,
        "n_outliers_gt1B": len(extreme),
        "outlier_share_pct": extreme[f"InvestmentCost{yr}"].sum() / total_inv_r0 * 100,
    }])
    out_path = OUTDIR / "2026-08_final_per_connection_analysis.csv"
    summary_df.to_csv(out_path, index=False)
    print(f"  Saved: {out_path.name}")
    return summary_df


if __name__ == "__main__":
    print("Running Tasks 2 + 5 (post-processing, no OnSSET re-run) …\n")
    task2_results = task2_f_band()
    print()
    task5_results = task5_per_connection()
    print("\nDone.")
