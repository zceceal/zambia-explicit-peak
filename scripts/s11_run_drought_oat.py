"""
s11_run_drought_oat.py — grid generation cost at 2024 drought import prices.

Extends the grid-generation-cost OAT beyond the 0.05 USD/kWh upper bound tested in
s09 to the Moobola (2024) drought-year prices of 0.17 (Eskom import), 0.22 (EDM
Mozambique import) and 0.26 USD/kWh (local emergency diesel), reported in the paper
§3.5. Same full-spine OAT, same harness, three additional prices.

Rules:
- DOES NOT overwrite any canonical 2026-08_final_* outputs.
- All new outputs go to data/onsset_outputs/, named 2026-08_final_oat_*.
- Seed 42 for OAT arms. Gate: central variant must reproduce the s06 central headline
  (±1.0 pp tolerance) before the drought variants are trusted.
- PV-hybrid lookup cache is built at the central diesel price and reused; grid
  generation cost does not enter the MG_PVHybrid sizing, so reuse is exact here
  (unlike the diesel-price case documented in the the s08 global sensitivity analysis).
"""

import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent

from s09_run_oat_checks import (
    run_arm_full, make_full_pair,
    compute_delta_lcoe_pct, count_sapv_to_grid,
    GRID_CAP_COST_CENTRAL, GRID_GEN_COST_CENTRAL,
    STAGE4_DELTA, STAGE4_SWITCHES, OAT_TOL_PP,
    PE_N20, PE_N10, PE_N50, TX_SHP, SOLAR_PROFILE, WIND_PROFILE,
    OUTDIR,
)
from onsset_helpers import load_solar_profile, load_wind_profile, load_config
from onsset import SettlementProcessor

import copy

# (label, grid_gen_cost USD/kWh, note)
VARIANTS = [
    ("central",    GRID_GEN_COST_CENTRAL,
     "Gate check — must reproduce the s06 central headline"),
    ("gen-0.17",   0.17,
     "Eskom drought-year import price 2024 (Moobola 2024)"),
    ("gen-0.22",   0.22,
     "EDM Mozambique drought-year import price 2024 (Moobola 2024)"),
    ("gen-0.26",   0.26,
     "Local emergency diesel generation price 2024 (Moobola 2024)"),
]

GRID_CODE = 1  # SET_ELEC_FINAL_CODE for grid


def tech_mix(df: pd.DataFrame) -> dict:
    """Population-weighted and count technology shares for one arm."""
    col = "FinalElecCode2030" if "FinalElecCode2030" in df.columns else None
    if col is None:
        cands = [c for c in df.columns if c.startswith("FinalElecCode")]
        col = sorted(cands)[-1] if cands else None
    if col is None:
        return {}
    counts = df[col].value_counts().to_dict()
    return {f"n_code{int(k)}": int(v) for k, v in counts.items()}


def main():
    t_total = time.time()
    print("=" * 70)
    print("  Drought-Price OAT — grid generation cost at 2024 drought prices")
    print("  Variants: 0.013 (gate) / 0.17 / 0.22 / 0.26 USD/kWh")
    print("=" * 70)

    print("\n[1/3] Loading profiles, TX network, config …")
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    print(f"  TX start points: {len(x_tx):,}")
    cfg_base = load_config()

    print("\n[2/3] Loading full GRID3 spine …")
    spine_n20 = pd.read_csv(PE_N20)
    if "PE_ratio" in spine_n20.columns:
        spine_n20 = spine_n20.rename(columns={"PE_ratio": "PE_ratio_n20"})
    if "N_hh" in spine_n20.columns:
        spine_n20 = spine_n20.rename(columns={"N_hh": "N_hh_val"})
    for nm, path in [(10, PE_N10), (50, PE_N50)]:
        if path.exists():
            tmp = pd.read_csv(path, usecols=["id", "PE_ratio"])
            spine_n20 = spine_n20.merge(
                tmp.rename(columns={"PE_ratio": f"PE_ratio_n{nm}"}),
                on="id", how="left")
    print(f"  Loaded: {len(spine_n20):,} settlements")

    spine_r0, spine_r1_n20 = make_full_pair(spine_n20, n_mid=20)
    pv_lut_cache = {}

    print("\n[3/3] Running variants …")
    results = []
    gate_ok = None
    for label, gen_cost, note in VARIANTS:
        print(f"\n  Variant: {label}  gen_cost={gen_cost:.3f} USD/kWh")
        print(f"    {note}")
        cfg_v = copy.deepcopy(cfg_base)
        cfg_v["grid"]["capacity_investment_cost_usd_kw"] = GRID_CAP_COST_CENTRAL
        cfg_v["grid"]["generation_cost_usd_kwh"] = gen_cost

        t0 = time.time()
        df_r0 = run_arm_full("DP_R0", spine_r0, cfg_v, x_tx, y_tx,
                             ghi_profile, temp_profile, wind_profile,
                             n_mid=None, pv_lut_cache=pv_lut_cache, silent=True)
        df_r1 = run_arm_full("DP_R1", spine_r1_n20, cfg_v, x_tx, y_tx,
                             ghi_profile, temp_profile, wind_profile,
                             n_mid=20, pv_lut_cache=pv_lut_cache, silent=True)

        delta = compute_delta_lcoe_pct(df_r0, df_r1)
        sw = count_sapv_to_grid(df_r0, df_r1)
        elapsed = time.time() - t0
        print(f"    ΔLCOE% = {delta:+.2f}%  SA_PV→Grid switches = {sw:,}"
              f"  ({elapsed:.0f}s)")

        if label == "central":
            gate_ok = abs(delta - STAGE4_DELTA) <= OAT_TOL_PP
            print(f"    GATE: |{delta:.2f} − {STAGE4_DELTA}| ≤ {OAT_TOL_PP}pp "
                  f"→ {'PASS' if gate_ok else 'FAIL'}")
            if not gate_ok:
                print("    WARNING: gate failed; drought variants not trusted.")

        row = {"variant": label, "grid_gen_cost": gen_cost,
               "delta_lcoe_pct": delta, "switch_count": sw,
               "elapsed_s": elapsed, "note": note}
        for arm, df_arm in (("R0", df_r0), ("R1", df_r1)):
            for k, v in tech_mix(df_arm).items():
                row[f"{arm}_{k}"] = v
        results.append(row)

        if label != "central":
            tag = label.replace(".", "")
            df_r0.to_csv(OUTDIR / f"2026-08_final_oat_{tag}_R0.csv",
                         index=False)
            df_r1.to_csv(OUTDIR / f"2026-08_final_oat_{tag}_R1_n20.csv",
                         index=False)

        # incremental save so partial results survive interruption
        pd.DataFrame(results).to_csv(
            OUTDIR / "2026-08_final_oat_drought_price.csv", index=False)

    df_out = pd.DataFrame(results)
    print("\n" + "=" * 70)
    print(f"  COMPLETE — {(time.time() - t_total) / 60:.1f} min")
    print("=" * 70)
    print(df_out[["variant", "grid_gen_cost", "delta_lcoe_pct",
                  "switch_count"]].to_string(index=False))
    print(f"\n  Gate: {'PASSED' if gate_ok else 'FAILED'}")
    print(f"  Outputs in: {OUTDIR}")


if __name__ == "__main__":
    main()
