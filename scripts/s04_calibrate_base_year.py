"""
Stage 3 / 3.5 — GRID3 spine base-year (2020) electrification calibration.

Inputs  : data/processed/zambia_grid3_spine_stage2.csv  (270,526 settlements)
          data/onsset_inputs/specs_zambia.xlsx           (pop/urban targets)

Outputs :
  Variant A (NEAS-2023 grid access, refined OR gate):
    data/processed/zambia_grid3_calib_distgate.csv
  Variant B (WB-2020 any-access, NTL-proxy):
    data/processed/zambia_grid3_calib_wb2020.csv

Calibration targets:
  Variant A — NEAS-2023: national 34%, urban 70%, rural 7.6%
  Variant B — WB-2020:   national 44.52%, urban 82.6%, rural 14.0%

Stage 3.5 change (Variant A): gate updated from
  TransformerDist < 2 km AND NTL > 0
to:
  (TransformerDist < 2 km OR CurrentMVLineDist < 2 km) AND NTL > 0
Rationale: grid reach is MV+LV, not only mapped transformers. The transformer
  layer is incomplete relative to the ZESCO MV network. 1,186 lit settlements
  are within 2 km of MV but not a mapped transformer and were being wrongly
  excluded. 155 truly isolated lit points (>5 km from any MV) remain excluded.
Implementation: before calling onsset, replace TransformerDist with
  min(TransformerDist, CurrentMVLineDist) in the working df. The onsset
  calibrate_grid_elec_current function then uses this effective distance with
  the standard 2 km gate.

Thresholds used for Variant B (NTL proxy):
  max_transformer_dist = 999 km (unbounded — NTL is operative criterion)
  min_night_lights     = 0
  min_pop              = 50
  NOTE: GRID3 spine has only 10.1% of rural pop with NightLights > 0, so the
  14.0% rural WB-2020 target is structurally unachievable with NTL-only proxy.

Both variants share the same urban/population calibration step:
  PopStartYear = 18,383,956 (WorldPop 2020 UN-adj; from specs_zambia.xlsx)
  UrbanRatioStartYear = 0.437 (UN WPP 2024)

Do NOT run LCOE. Do NOT modify stage2 spine.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
from onsset import SettlementProcessor, SET_GRID_PENALTY, SET_WINDVEL, SET_WINDCF

SPECS_IN   = REPO / "data" / "onsset_inputs" / "specs_zambia.xlsx"
SPINE_IN   = REPO / "data" / "processed" / "zambia_grid3_spine_stage2.csv"
OUT_A      = REPO / "data" / "processed" / "zambia_grid3_calib_distgate.csv"
OUT_B      = REPO / "data" / "processed" / "zambia_grid3_calib_wb2020.csv"

# ── Calibration parameters ────────────────────────────────────────────────────

# Shared pop/urban targets
POP_ACTUAL  = 18_383_956
URBAN_RATIO = 0.437

# Variant A — NEAS-2023 grid access
A_NATIONAL = 0.34
A_URBAN    = 0.70
A_RURAL    = 0.076
A_MAX_TRANS = 2.0
A_MAX_MV    = 3.0
A_MAX_HV    = 5.0
A_MIN_NTL   = 0.0
A_MIN_POP   = 0

# Variant B — WB-2020 any-access (NTL proxy)
B_NATIONAL = 0.4452
B_URBAN    = 0.826
B_RURAL    = 0.14
B_MAX_TRANS = 999.0
B_MAX_MV    = 999.0
B_MAX_HV    = 999.0
B_MIN_NTL   = 0.0
B_MIN_POP   = 50


def read_specs():
    specs = pd.read_excel(SPECS_IN, sheet_name="SpecsData", header=1)
    return specs


def _realised_rates(df):
    """Compute national/urban/rural electrification rates from calibrated df."""
    total_pop  = df["PopStartYear"].sum()
    urban_pop  = df.loc[df["IsUrban"] > 1, "PopStartYear"].sum()
    rural_pop  = df.loc[df["IsUrban"] <= 1, "PopStartYear"].sum()
    elec_urban = df.loc[(df["ElecStart"] == 1) & (df["IsUrban"] > 1), "ElecPopCalib"].sum()
    elec_rural = df.loc[(df["ElecStart"] == 1) & (df["IsUrban"] <= 1), "ElecPopCalib"].sum()
    national_rate = (elec_urban + elec_rural) / total_pop if total_pop > 0 else 0
    urban_rate    = elec_urban / urban_pop if urban_pop > 0 else 0
    rural_rate    = elec_rural / rural_pop if rural_pop > 0 else 0
    return national_rate, urban_rate, rural_rate, total_pop, urban_pop, rural_pop


def run_variant(label, spine_path, national, urban_r, rural_r,
                max_trans, max_mv, max_hv, min_ntl, min_pop, out_path,
                mv_or_gate=False):
    """
    mv_or_gate: if True, replace TransformerDist with min(TransformerDist, CurrentMVLineDist)
    before calibration, implementing (TransformerDist<thresh OR MV<thresh) gate.
    """
    print(f"\n{'='*68}")
    print(f"  {label}")
    print(f"{'='*68}")
    print(f"  Targets: national={national:.1%}, urban={urban_r:.1%}, rural={rural_r:.1%}")
    gate_desc = "(TransformerDist OR MV)" if mv_or_gate else "TransformerDist"
    print(f"  Gate: {gate_desc} < {max_trans}km AND NTL > {min_ntl}, min_pop={min_pop}")

    # ── Coverage audit before calibration ────────────────────────────────────
    df_check = pd.read_csv(spine_path)
    if mv_or_gate:
        eff_dist = df_check[['TransformerDist', 'CurrentMVLineDist']].min(axis=1)
        n_cand = ((eff_dist < max_trans) & (df_check["NightLights"] > min_ntl)).sum()
        n_trans_only = ((df_check["TransformerDist"] < max_trans) & (df_check["NightLights"] > min_ntl)).sum()
        n_mv_added   = n_cand - n_trans_only
        print(f"\n  Pre-calibration candidate set (OR gate):")
        print(f"    Transformer<{max_trans}km AND NTL>0:            {n_trans_only:,}  (v1 gate)")
        print(f"    MV<{max_trans}km AND NTL>0, Transformer>={max_trans}km: {n_mv_added:,}  (newly added)")
        print(f"    Total candidate gate (OR):                {n_cand:,}")
        n_isolated = ((df_check["NightLights"] > min_ntl) &
                      (df_check["TransformerDist"] >= 5) &
                      (df_check["CurrentMVLineDist"] >= 5)).sum()
        print(f"    Lit settlements >5km from both (excluded): {n_isolated:,}")
    else:
        n_trans = (df_check["TransformerDist"] < max_trans).sum()
        n_mv    = (df_check["CurrentMVLineDist"] < max_mv).sum()
        n_ntl   = (df_check["NightLights"] > min_ntl).sum()
        n_cand  = ((df_check["TransformerDist"] < min(max_trans, 900)) &
                   (df_check["NightLights"] > min_ntl)).sum()
        print(f"\n  Pre-calibration coverage:")
        print(f"    Settlements within {max_trans}km of transformer: {n_trans:,}")
        print(f"    Settlements within {max_mv}km of MV line:        {n_mv:,}")
        print(f"    Settlements with NightLights > {min_ntl}:         {n_ntl:,}")
        if max_trans < 900:
            print(f"    Candidate intersection (transformer+NTL):    {n_cand:,}")

    # ── OnSSET calibration ────────────────────────────────────────────────────
    print(f"\n  Initialising SettlementProcessor from {spine_path.name} ...")
    onsseter = SettlementProcessor(str(spine_path))
    onsseter.condition_df()
    if mv_or_gate:
        # Implement (TransformerDist OR MV) < thresh by using effective min distance.
        # onsset picks TransformerDist when min < 9999; by replacing it with min(both),
        # the standard 2km gate implements the OR condition correctly.
        onsseter.df['TransformerDist'] = onsseter.df[['TransformerDist', 'CurrentMVLineDist']].min(axis=1)
        print(f"  OR-gate applied: TransformerDist ← min(TransformerDist, CurrentMVLineDist)")
    onsseter.df[SET_GRID_PENALTY] = 1
    onsseter.df[SET_WINDCF] = onsseter.calc_wind_cfs(onsseter.df[SET_WINDVEL])

    print("  Step 1: population + urban calibration ...")
    pop_mod, urban_mod = onsseter.calibrate_current_pop_and_urban(POP_ACTUAL, URBAN_RATIO)
    print(f"    Pop modelled:         {pop_mod:,.0f}  (target {POP_ACTUAL:,})")
    print(f"    Urban ratio modelled: {urban_mod:.4f}  (target {URBAN_RATIO})")

    print("  Step 2: electrification calibration ...")
    elec_results = onsseter.calibrate_grid_elec_current(
        national, urban_r, rural_r,
        2020,
        min_night_lights=min_ntl,
        min_pop=min_pop,
        max_transformer_dist=max_trans,
        max_mv_dist=max_mv,
        max_hv_dist=max_hv,
        buffer=False,
    )
    elec_mod       = elec_results[0]
    grid_dist_used = elec_results[3]
    ntl_limit      = elec_results[4]
    pop_limit      = elec_results[5]
    print(f"    ElecStart=1 cells:  {(onsseter.df['ElecStart'] == 1).sum():,}")
    print(f"    ElecPopCalib total: {onsseter.df['ElecPopCalib'].sum():,.0f}")
    print(f"    Grid dist column:   {grid_dist_used}")

    print("  Step 3: mini-grid calibration ...")
    mg_pop = onsseter.mg_elec_current(2020)

    # ── Realised rates ────────────────────────────────────────────────────────
    nat_r, urb_r, rur_r, tot_pop, urb_pop, rur_pop = _realised_rates(onsseter.df)
    elec_total = onsseter.df.loc[onsseter.df["ElecStart"] == 1, "ElecPopCalib"].sum()
    print(f"\n  Realised rates:")
    print(f"    National: {nat_r:.4f}  (target {national:.4f}, error {nat_r-national:+.4f})")
    print(f"    Urban:    {urb_r:.4f}  (target {urban_r:.4f}, error {urb_r-urban_r:+.4f})")
    print(f"    Rural:    {rur_r:.4f}  (target {rural_r:.4f}, error {rur_r-rural_r:+.4f})")
    print(f"    Electrified pop:    {elec_total:,.0f}  ({nat_r:.1%} of {tot_pop:,.0f})")
    print(f"    Urban pop:          {urb_pop:,.0f}  ({urb_pop/tot_pop:.1%})")
    print(f"    Rural pop:          {rur_pop:,.0f}  ({rur_pop/tot_pop:.1%})")

    # ElecStart settlement breakdown
    df = onsseter.df
    n_elec_settle  = (df["ElecStart"] == 1).sum()
    n_total_settle = len(df)
    print(f"\n  Electrified settlements: {n_elec_settle:,} / {n_total_settle:,} ({n_elec_settle/n_total_settle:.2%})")

    # Check FinalElecCode2020 distribution
    col = "FinalElecCode2020"
    if col in df.columns:
        counts = df[col].value_counts().sort_index()
        print(f"  FinalElecCode2020 distribution:")
        for code, cnt in counts.items():
            label_map = {1: "grid-electrified", 5: "mini-grid", 99: "unelectrified"}
            print(f"    Code {code} ({label_map.get(code, '?')}): {cnt:,}")

    # ── Write output ──────────────────────────────────────────────────────────
    onsseter.df.to_csv(str(out_path), index=False)
    print(f"\n  Written: {out_path.name}  ({out_path.stat().st_size/1e6:.1f} MB)")

    return {
        "national_target": national,
        "urban_target":    urban_r,
        "rural_target":    rural_r,
        "national_rate":   nat_r,
        "urban_rate":      urb_r,
        "rural_rate":      rur_r,
        "nat_err_pp":      (nat_r - national) * 100,
        "urb_err_pp":      (urb_r - urban_r) * 100,
        "rur_err_pp":      (rur_r - rural_r) * 100,
        "elec_pop":        elec_total,
        "total_pop":       tot_pop,
        "max_trans_km":    max_trans,
        "max_mv_km":       max_mv,
        "min_ntl":         min_ntl,
        "min_pop":         min_pop,
        "grid_dist_col":   grid_dist_used,
        "n_elec_settle":   n_elec_settle,
    }


def main():
    print("=" * 68)
    print("  GRID3 SPINE — STAGE 3.5 CALIBRATION REFINEMENT")
    print("  Variant A: refined OR gate (Transformer OR MV < 2 km)")
    print("  Variant B: unchanged (NTL-proxy, WB-2020)")
    print("=" * 68)

    # ── Verify input ──────────────────────────────────────────────────────────
    if not SPINE_IN.exists():
        raise FileNotFoundError(f"Input spine not found: {SPINE_IN}")
    df_head = pd.read_csv(SPINE_IN, nrows=1)
    pop_total = pd.read_csv(SPINE_IN, usecols=["Pop"])["Pop"].sum()
    print(f"\n  Input: {SPINE_IN.name}")
    print(f"  Settlements: 270,526  (from stage 2)")
    print(f"  Pop sum (raw): {pop_total:,.0f}  (expect ~18.38M)")

    # ── Run Variant A (refined: OR gate) ─────────────────────────────────────
    res_a = run_variant(
        label="VARIANT A — NEAS-2023 targets, refined (Transformer OR MV) < 2 km gate",
        spine_path=SPINE_IN,
        national=A_NATIONAL, urban_r=A_URBAN, rural_r=A_RURAL,
        max_trans=A_MAX_TRANS, max_mv=A_MAX_MV, max_hv=A_MAX_HV,
        min_ntl=A_MIN_NTL, min_pop=A_MIN_POP,
        out_path=OUT_A,
        mv_or_gate=True,
    )

    # ── Run Variant B ─────────────────────────────────────────────────────────
    res_b = run_variant(
        label="VARIANT B — NTL-proxy → WB-2020 any-access targets",
        spine_path=SPINE_IN,
        national=B_NATIONAL, urban_r=B_URBAN, rural_r=B_RURAL,
        max_trans=B_MAX_TRANS, max_mv=B_MAX_MV, max_hv=B_MAX_HV,
        min_ntl=B_MIN_NTL, min_pop=B_MIN_POP,
        out_path=OUT_B,
    )

    # ── D1 evidence table ─────────────────────────────────────────────────────
    print(f"\n{'='*68}")
    print(f"{'='*68}")
    hdr = f"{'Metric':<35}{'WB-2020':>12}{'NEAS-2023':>12}{'Var A (dist)':>14}{'Var B (NTL)':>14}"
    print(hdr)
    print("-" * len(hdr))
    rows = [
        ("National elec rate",    0.4452,  0.34,   res_a['national_rate'], res_b['national_rate']),
        ("Urban elec rate",       0.826,   0.70,   res_a['urban_rate'],    res_b['urban_rate']),
        ("Rural elec rate",       0.14,    0.076,  res_a['rural_rate'],    res_b['rural_rate']),
    ]
    for name, wb, neas, va, vb in rows:
        print(f"  {name:<33}{wb:>12.3f}{neas:>12.3f}{va:>14.4f}{vb:>14.4f}")

    print(f"\n  Errors vs each variant's own target (percentage points):")
    print(f"  {'':35}{'Var A err':>14}{'Var B err':>14}")
    print(f"  {'National':35}{res_a['nat_err_pp']:>+13.2f}pp{res_b['nat_err_pp']:>+13.2f}pp")
    print(f"  {'Urban':35}{res_a['urb_err_pp']:>+13.2f}pp{res_b['urb_err_pp']:>+13.2f}pp")
    print(f"  {'Rural':35}{res_a['rur_err_pp']:>+13.2f}pp{res_b['rur_err_pp']:>+13.2f}pp")

    # ── Rural shortfall warning for Variant B ─────────────────────────────────
    if abs(res_b['rural_rate'] - B_RURAL) > 0.02:
        print(f"\n  *** WARNING (Variant B): Rural target {B_RURAL:.1%} not achieved.")
        print(f"      Achieved: {res_b['rural_rate']:.4f}. This is a structural limitation:")
        print(f"      The GRID3 NTL layer covers only ~10.1% of rural population.")
        print(f"      The WB-2020 14% rural target exceeds available NTL coverage.")

    print(f"\n  Thresholds operative:")
    print(f"    Var A (dist-gate): TransformerDist < {A_MAX_TRANS}km, NTL > {A_MIN_NTL}")
    print(f"    Var B (NTL-proxy): TransformerDist < {B_MAX_TRANS}km (all), NTL > {B_MIN_NTL}")

    print(f"\n  Output files:")
    print(f"    {OUT_A.name}")
    print(f"    {OUT_B.name}")


if __name__ == "__main__":
    main()
