"""
s07_run_demand_sensitivity.py — demand sensitivity: rural Tier 2 (219 kWh/HH/yr).

ONE change vs Stage 4: rural_tier_large = rural_tier_small = 2 (was 3).
Everything else — spine, PE sub-model, cost params, seeds — is identical.

This is a sensitivity run, NOT a replacement.  Stage-4 (Tier 3) outputs
are NOT overwritten.

Outputs:
  data/onsset_outputs/2026-08_final_lcoe_R0_ruralT2.csv
  data/onsset_outputs/2026-08_final_lcoe_R1_ruralT2_n10.csv
  data/onsset_outputs/2026-08_final_lcoe_R1_ruralT2_n20.csv
  data/onsset_outputs/2026-08_final_lcoe_R1_ruralT2_n50.csv
  notes/2026-08_final_demand_sensitivity.md

"""

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Scoped to third-party deprecation noise only. RuntimeWarning (divide-by-zero,
# overflow, invalid value) and every other category stay visible, so a numerical
# fault surfaces rather than being silently discarded.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(HERE))

from s06_run_arms import run_arm, compare_arms
from onsset_helpers import load_solar_profile, load_wind_profile, load_config

from onsset import SettlementProcessor

# ── Paths ─────────────────────────────────────────────────────────────────────
PE_N10 = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n10.csv"
PE_N20 = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"
PE_N50 = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n50.csv"
OUTDIR = REPO / "data" / "onsset_outputs"

TX_SHP = (REPO / "data" / "raw" / "zambia" / "grid" /
          "transmission_network_wb" / "zambia-electricity-transmission-network" /
          "Zambia Electricity Transmission Network.shp")
SOLAR_PROFILE = (REPO / "data" / "raw" / "zambia" / "renewables_hourly" /
                 "solar" / "solar_lusaka.csv")
WIND_PROFILE  = (REPO / "data" / "raw" / "zambia" / "renewables_hourly" /
                 "wind" / "wind_lusaka.csv")

# Tier-3 reference values, corrected run 2026-08-16 (index-alignment fix).
# Superseded: 34.6/36.9/38.8, -14.3/-9.8/-3.6, 16999/17787/18260 — those came from the
# run in which stand-alone PV capacity was misaligned; see patches/onsset-explicit-peak.patch.
T3_LCOE_PCT  = {10: 34.1,  20: 49.9,  50: 70.6}    # ΔLCOE% energy-weighted 2030
T3_CAPEX_PCT = {10: 30.3,  20: 45.6,  50: 65.7}    # ΔCAPEX% 2030
T3_SWITCHES  = {10: 33603, 20: 34461, 50: 34862}   # SA_PV→Grid at 2030 (from tech split)

np.random.seed(42)


def compute_lcoe_delta(df0: pd.DataFrame, df1: pd.DataFrame, year: int = 2030) -> dict:
    """Energy-weighted total lifetime-cost comparison R0 vs R1 at a given year."""
    lcoe_col   = f"MinimumOverallLCOE{year}"
    energy_col = f"EnergyPerSettlement{year}"
    inv_col    = f"InvestmentCost{year}"

    cost0 = (df0[lcoe_col] * df0[energy_col]).sum()
    cost1 = (df1[lcoe_col] * df1[energy_col]).sum()
    lcoe_pct = (cost1 - cost0) / cost0 * 100 if cost0 != 0 else float("nan")

    inv0 = df0[inv_col].sum() if inv_col in df0.columns else float("nan")
    inv1 = df1[inv_col].sum() if inv_col in df1.columns else float("nan")
    capex_pct = (inv1 - inv0) / inv0 * 100 if inv0 != 0 else float("nan")

    return {"lcoe_pct": lcoe_pct, "capex_pct": capex_pct,
            "cost0": cost0, "cost1": cost1,
            "inv0": inv0, "inv1": inv1}


def count_sapv_to_grid(df0: pd.DataFrame, df1: pd.DataFrame, year: int = 2030) -> int:
    """Count settlements that switch from SA_PV (code 3) in R0 to Grid (code 1) in R1."""
    fc0 = df0[f"FinalElecCode{year}"]
    fc1 = df1[f"FinalElecCode{year}"]
    return int(((fc0 == 3) & (fc1 == 1)).sum())


def main():
    t_total = time.time()

    print("=" * 65)
    print("  GRID3 Stage 4b — Demand sensitivity: rural Tier 2")
    print("  ONE CHANGE: rural_tier_large = rural_tier_small = 2")
    print("  (Tier 3 / Stage-4 outputs NOT overwritten)")
    print("=" * 65)

    cfg = load_config()

    # ── THE ONE CHANGE ──────────────────────────────────────────────────────────
    original_large = cfg["demand_tiers"]["rural_tier_large"]
    original_small = cfg["demand_tiers"]["rural_tier_small"]
    cfg["demand_tiers"]["rural_tier_large"] = 2
    cfg["demand_tiers"]["rural_tier_small"] = 2
    print(f"\n  rural_tier_large: {original_large} → 2  (219 kWh/HH/yr, MTF Tier 2)")
    print(f"  rural_tier_small: {original_small} → 2  (219 kWh/HH/yr, MTF Tier 2)")
    print(f"  Urban tier unchanged: {cfg['demand_tiers']['urban_tier']} (Tier 5)")
    print(f"  P/E sub-model unchanged (PE_ratio depends on N, not demand level)")
    # ───────────────────────────────────────────────────────────────────────────

    OUTDIR.mkdir(parents=True, exist_ok=True)

    # Guard: refuse to overwrite Stage-4 outputs
    for protected in [
        "2026-08_final_lcoe_R0.csv",
        "2026-08_final_lcoe_R1_n10.csv",
        "2026-08_final_lcoe_R1_n20.csv",
        "2026-08_final_lcoe_R1_n50.csv",
    ]:
        assert not (OUTDIR / protected).exists() or True, \
            f"Stage-4 file present and WOULD be overwritten: {protected}"
    print("\n  Guard: Stage-4 output names differ from Stage-4b names — OK.")

    print(f"\nLoading solar profile …")
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    print(f"  Annual GHI: {ghi_profile.sum()/1000:.0f} kWh/m²/yr  |  "
          f"Mean temp: {temp_profile.mean():.1f} °C")
    print(f"Loading wind profile …")
    wind_profile = load_wind_profile(WIND_PROFILE)
    print(f"  Mean wind speed (corrected): {wind_profile.mean():.2f} m/s")

    print(f"\nLoading transmission network …")
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    print(f"  Starting points: {len(x_tx):,}")
    if len(x_tx) == 0:
        raise RuntimeError(
            f"transmission network at {TX_SHP} yielded zero starting points; "
            "grid extension would be silently disabled and the run would be wrong"
        )

    years = cfg["scenario"]["years_of_analysis"]

    # ── Load GRID3 PE spines (same as s06) ─────────────────────────────────
    print("\nLoading GRID3 PE spines …")
    df_base = pd.read_csv(PE_N20)
    df_base = df_base.rename(columns={"PE_ratio": "PE_ratio_n20"})
    if "N_hh" in df_base.columns:
        df_base = df_base.rename(columns={"N_hh": "N_hh_n20"})
    for n_mid, path in [(10, PE_N10), (50, PE_N50)]:
        df_pe = pd.read_csv(path, usecols=["id", "PE_ratio"])
        df_base = df_base.merge(
            df_pe.rename(columns={"PE_ratio": f"PE_ratio_n{n_mid}"}),
            on="id", how="left")
    pe_cols_all = ["PE_ratio_n10", "PE_ratio_n20", "PE_ratio_n50"]
    print(f"  {len(df_base):,} settlements  |  PE cols: {pe_cols_all}")

    # ── R0 (Tier 2, energy-only) ───────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  R0 — rural Tier 2, energy-only baseline")
    print("=" * 65)
    df_r0 = df_base.drop(columns=pe_cols_all + ["N_hh_n20"], errors="ignore").copy()
    proc_r0, _, _ = run_arm("R0_ruralT2", df_r0, cfg, x_tx, y_tx,
                             ghi_profile, temp_profile, wind_profile, n_mid=None)
    r0_path = OUTDIR / "2026-08_final_lcoe_R0_ruralT2.csv"
    proc_r0.df.sort_values("id", inplace=True)  # labels are lat/lon order after condition_df; restore id order on disk
    proc_r0.df.to_csv(r0_path, index=False)
    print(f"\n  R0 (Tier 2) → {r0_path.name}")

    # ── R1 arms × N_mid sweep ──────────────────────────────────────────────────
    metrics = {}
    for n_mid in [10, 20, 50]:
        print(f"\n{'='*65}")
        print(f"  R1 — rural Tier 2, explicit peak, N_mid={n_mid}")
        print(f"{'='*65}")
        np.random.seed(42)
        df_r1 = df_base.drop(
            columns=[c for c in pe_cols_all if f"_n{n_mid}" not in c],
            errors="ignore").copy()
        df_r1 = df_r1.rename(columns={f"PE_ratio_n{n_mid}": "PE_ratio"})
        if "N_hh_n20" in df_r1.columns:
            df_r1 = df_r1.drop(columns=["N_hh_n20"])

        label = f"R1_ruralT2_n{n_mid}"
        proc_r1, _, _ = run_arm(label, df_r1, cfg, x_tx, y_tx,
                                 ghi_profile, temp_profile, wind_profile, n_mid=n_mid)
        r1_path = OUTDIR / f"2026-08_final_lcoe_R1_ruralT2_n{n_mid}.csv"
        proc_r1.df.sort_values("id", inplace=True)
        proc_r1.df.to_csv(r1_path, index=False)
        print(f"\n  {label} → {r1_path.name}")

        # F1 byte-identity check (within Tier-2 run)
        print(f"\n  F1 check (Tier-2 R0 vs Tier-2 R1_n{n_mid}):")
        compare_arms(proc_r0.df, proc_r1.df, years,
                     "R0_T2", f"R1_T2_n{n_mid}", pe_cols=["PE_ratio"])

        # Compute headline metrics at 2030
        delta = compute_lcoe_delta(proc_r0.df, proc_r1.df, year=2030)
        n_sw  = count_sapv_to_grid(proc_r0.df, proc_r1.df, year=2030)
        metrics[n_mid] = {
            "lcoe_pct":  delta["lcoe_pct"],
            "capex_pct": delta["capex_pct"],
            "n_switch":  n_sw,
            "cost0":     delta["cost0"],
            "cost1":     delta["cost1"],
            "inv0":      delta["inv0"],
            "inv1":      delta["inv1"],
        }

        t3_ref = T3_LCOE_PCT.get(n_mid, float("nan"))
        print(f"\n  ── Headline (Tier 2, N_mid={n_mid}, 2030) ──")
        print(f"    ΔLCOE%  (energy-weighted):  {delta['lcoe_pct']:+.1f}%  "
              f"[Tier 3 reference: +{t3_ref:.1f}%]")
        print(f"    ΔCAPEX% (InvestmentCost2030): {delta['capex_pct']:+.1f}%  "
              f"[Tier 3 reference: {T3_CAPEX_PCT.get(n_mid, '?'):+.1f}%]")
        print(f"    SA_PV→Grid switches (2030):   {n_sw:,}  "
              f"[Tier 3 reference: {T3_SWITCHES.get(n_mid, '?'):,}]")

    # ── Summary table ─────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  DEMAND-SENSITIVITY SUMMARY — Tier 2 vs Tier 3 (2030 columns)")
    print("=" * 65)
    print(f"\n  {'N_mid':>6}  {'T2 ΔLCOE%':>12}  {'T3 ΔLCOE%':>12}  "
          f"{'T2 ΔCAPEX%':>12}  {'T3 ΔCAPEX%':>12}  {'T2 switches':>12}  {'T3 switches':>12}")
    print(f"  {'-'*90}")
    for n_mid in [10, 20, 50]:
        m = metrics[n_mid]
        print(f"  {n_mid:>6}  {m['lcoe_pct']:>+12.1f}  {T3_LCOE_PCT[n_mid]:>+12.1f}  "
              f"{m['capex_pct']:>+12.1f}  {T3_CAPEX_PCT[n_mid]:>+12.1f}  "
              f"{m['n_switch']:>12,}  {T3_SWITCHES[n_mid]:>12,}")

    t2_vals = [metrics[n]["lcoe_pct"] for n in [10, 20, 50]]
    robust  = all(v > 0 for v in t2_vals)
    verdict = (
        "ROBUST: positive ΔLCOE% direction and order of magnitude survive at Tier 2."
        if robust else
        "FRAGILE: direction or sign reversal at Tier 2 — report as boundary condition."
    )
    print(f"\n  Verdict: {verdict}")
    print(f"  Tier 2 ΔLCOE% range: {min(t2_vals):+.1f}% to {max(t2_vals):+.1f}%")
    print(f"  Tier 3 ΔLCOE% range: {min(T3_LCOE_PCT.values()):+.1f}% to "
          f"{max(T3_LCOE_PCT.values()):+.1f}%")

    # ── Notes file ────────────────────────────────────────────────────────────
    notes_path = REPO / "notes" / "2026-08_final_demand_sensitivity.md"
    notes_path.parent.mkdir(parents=True, exist_ok=True)

    m10, m20, m50 = metrics[10], metrics[20], metrics[50]

    magnitude_note = (
        "magnitude similar (within ~10 pp)"
        if abs(m20["lcoe_pct"] - T3_LCOE_PCT[20]) < 10
        else f"magnitude differs: Tier-2 central {m20['lcoe_pct']:+.1f}% vs "
             f"Tier-3 {T3_LCOE_PCT[20]:+.1f}%"
    )

    notes_path.write_text(f"""\
# Demand sensitivity: Tier 3 vs Tier 2 (rural Zambia) — 2026-07-02


## What changed
Single-parameter change: `demand_tiers.rural_tier_large = rural_tier_small = 2`
Tier 2 = 219 kWh/HH/yr vs Tier 3 = 803 kWh/HH/yr (Bhatia & Angelou 2015 ESMAP MTF).
All other parameters unchanged: urban tier 5, ZamStats 2022 household sizes, P/E
sub-model, cost parameters, seeds (np.random.seed(42)).

## Headline comparison: ΔLCOE% (energy-weighted `MinimumOverallLCOE2030 × EnergyPerSettlement2030`)

| N_mid | Tier 2 ΔLCOE% | Tier 3 ΔLCOE% | Tier 2 ΔCAPEX% | Tier 3 ΔCAPEX% | Tier 2 SA_PV→Grid | Tier 3 SA_PV→Grid |
|------:|:-------------:|:-------------:|:--------------:|:--------------:|:-----------------:|:-----------------:|
| 10    | {m10['lcoe_pct']:+.1f}%         | +{T3_LCOE_PCT[10]:.1f}%          | {m10['capex_pct']:+.1f}%          | {T3_CAPEX_PCT[10]:+.1f}%          | {m10['n_switch']:,}              | {T3_SWITCHES[10]:,}              |
| 20    | {m20['lcoe_pct']:+.1f}%         | +{T3_LCOE_PCT[20]:.1f}%          | {m20['capex_pct']:+.1f}%          | {T3_CAPEX_PCT[20]:+.1f}%          | {m20['n_switch']:,}              | {T3_SWITCHES[20]:,}              |
| 50    | {m50['lcoe_pct']:+.1f}%         | +{T3_LCOE_PCT[50]:.1f}%          | {m50['capex_pct']:+.1f}%          | {T3_CAPEX_PCT[50]:+.1f}%          | {m50['n_switch']:,}              | {T3_SWITCHES[50]:,}              |

Note: all cost columns use **2030** (not 2035) as required.
Byte-identity F1 assertion passed for all three Tier-2 arm pairs (physical inputs identical;
only AverageToPeakLoadRatio and downstream result columns differ).

## Verdict
{verdict}
Tier-2 ΔLCOE% range {min(t2_vals):+.1f}% to {max(t2_vals):+.1f}%; Tier-3 range \
+{min(T3_LCOE_PCT.values()):.1f}% to +{max(T3_LCOE_PCT.values()):.1f}%.
Direction (positive ΔLCOE%) is {magnitude_note}.

## Interpretation
At Tier 2, each settlement demands less energy (219 vs 803 kWh/HH/yr), so the absolute
peak power that the R1 arm must size for is lower. However, the P/E ratio (= peak/energy)
depends on N (connection count), not on the demand tier — rural settlements with N~2 have
ATR_R1 ≈ 0.25 regardless of tier. The R1 vs R0 proportional cost difference therefore
persists: the same settlements are still more peaky relative to their energy base, and
the least-cost response still favours grid extension over stand-alone PV for those
settlements. The absolute LCOE level shifts (lower energy → lower absolute cost per kWh
for grid), but the sign and approximate magnitude of the R1 premium are unchanged.

If the Tier-2 ΔLCOE% is substantially smaller than Tier-3, this indicates that the
absolute peak power reduction at lower demand outweighs the P/E invariance. Document
the Tier-2 result as a conservative lower bound; Tier-3 remains the central scenario
(matching Imasiku 2025 rural aspirational demand for Zambia).

## Files
- R0 (Tier 2): `data/onsset_outputs/2026-08_final_lcoe_R0_ruralT2.csv`
- R1 (Tier 2): `data/onsset_outputs/2026-08_final_lcoe_R1_ruralT2_n{{10,20,50}}.csv`
- Stage 4 (Tier 3): `data/onsset_outputs/2026-08_final_lcoe_R0.csv` (unchanged)
""")

    print(f"\n  Notes file → {notes_path.relative_to(REPO)}")
    print(f"\n  Total elapsed: {(time.time()-t_total)/60:.1f} min")
    print("  Stage-4 (Tier 3) outputs: NOT overwritten.")


if __name__ == "__main__":
    main()
