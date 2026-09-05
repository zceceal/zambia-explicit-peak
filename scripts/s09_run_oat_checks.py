"""
s09_run_oat_checks.py — grid-side one-at-a-time checks and full-spine validation.

LHS full-spine validation: re-run 3 LHS samples on the FULL spine (270,526 settlements) and
compare against their bias-corrected subsample values. This validates whether the
bias-correction factor transfers across the parameter space.

Grid-side OAT at the central case — grid capacity cost ±30% and generation cost
drought proxy. Reports ΔLCOE% AND SA_PV→Grid switch count per variant.

Rules:
- DOES NOT overwrite any s06, s07 or s08 outputs.
- All new outputs go to data/onsset_outputs/, named 2026-08_final_oat_*.
- Seeds: LHS_VAL seed inherited from the s08 LHS CSV (seed=43 for LHS design);
         OAT arms use np.random.seed(42).
- Gate: central OAT variant must reproduce the s06 central headline before variants are trusted.
"""

import copy
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Third-party deprecation noise only; see onsset_helpers.py for the filter's scope.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

HERE    = Path(__file__).resolve().parent
REPO    = HERE.parent
OUTDIR  = REPO / "data" / "onsset_outputs"
NOTEDIR = REPO / "notes"

sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(HERE))

from onsset_helpers import (
    load_solar_profile, load_wind_profile,
    build_pv_hybrid_lookup, apply_pv_hybrid_lookup,
    compute_offgrid_min,
    build_tech_objects, build_mg_pv_hybrid_params, build_mg_wind_hybrid_params,
    load_config, central_headline,
    TIERS, CONN_COST_PER_HH,
    _PHYSICAL_INPUT_COLS,
)
from peak_preprocessor.pe_diversity import (
    pe_from_n, compute_beta,
    P_1_DEFAULT, P_INF_DEFAULT, P_STEP_DEFAULT,
    SD_P_1, SD_P_INF, SD_P_STEP, N_MID_CENTRAL,
)
from onsset import (
    SettlementProcessor, Technology,
    SET_GRID_PENALTY, SET_WINDVEL, SET_WINDCF, SET_AVERAGE_TO_PEAK,
    SET_GHI, SET_TIER, SET_ENERGY_PER_CELL, SET_MG_DIESEL_FUEL,
    SET_POP, SET_ELEC_FINAL_CODE,
    SET_MV_DIST_PLANNED, SET_HV_DIST_PLANNED,
    SET_MV_DIST_CURRENT, SET_HV_DIST_CURRENT,
)

# ── Constants ─────────────────────────────────────────────────────────────────
ANALYSIS_YEAR   = 2030
# Central headline (dLCOE %, SA_PV->Grid switches) read from the s06 outputs on disk, so the
# gate below always refers to the headline the current settlement dataset produced.
STAGE4_DELTA, STAGE4_SWITCHES = central_headline()
OAT_TOL_PP      = 1.0       # pp tolerance for gate check (allow rounding in re-run)
OAT_SWITCH_TOL  = 0         # exact: the LUT is rebuilt per arm, matching s06

# Grid cost central values (from config / Egli 2023 Table S8)
GRID_CAP_COST_CENTRAL = 1441.1   # USD/kW
GRID_GEN_COST_CENTRAL = 0.013    # USD/kWh

# ── Paths ─────────────────────────────────────────────────────────────────────
PE_N20 = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"
PE_N10 = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n10.csv"
PE_N50 = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n50.csv"
TX_SHP = (REPO / "data" / "raw" / "zambia" / "grid" /
           "transmission_network_wb" / "zambia-electricity-transmission-network" /
           "Zambia Electricity Transmission Network.shp")
SOLAR_PROFILE = (REPO / "data" / "raw" / "zambia" / "renewables_hourly" /
                 "solar" / "solar_lusaka.csv")
WIND_PROFILE  = (REPO / "data" / "raw" / "zambia" / "renewables_hourly" /
                 "wind" / "wind_lusaka.csv")
LHS_CSV = OUTDIR / "2026-08_final_lhs_uncertainty.csv"

# ── s06 output guard ──────────────────────────────────────────────────────
PROTECTED = [
    OUTDIR / "2026-08_final_lcoe_R0.csv",
    OUTDIR / "2026-08_final_lcoe_R1_n20.csv",
    OUTDIR / "2026-08_final_morris_delta_lcoe.csv",
    OUTDIR / "2026-08_final_lhs_uncertainty.csv",
]


# ── §1  FULL-SPINE ARM RUNNER  (the full-spine counterpart of s08's subsample runner) ───
def run_arm_full(
    arm_label: str,
    spine_df: pd.DataFrame,
    cfg: dict,
    x_tx_orig: np.ndarray,
    y_tx_orig: np.ndarray,
    ghi_profile: np.ndarray,
    temp_profile: np.ndarray,
    wind_profile: np.ndarray,
    n_mid: int,                        # None → R0; int → R1
    sa_pv_capex_mult: float = 1.0,
    pv_lut_cache: dict = None,
    silent: bool = False,
) -> pd.DataFrame:
    """Run one R0 or R1 arm on the full spine."""
    np.random.seed(42)

    def _p(msg):
        if not silent:
            print(msg)

    hh_u         = float(cfg["household_size"]["urban"])
    hh_r         = float(cfg["household_size"]["rural"])
    urban_tier   = int(cfg["demand_tiers"]["urban_tier"])
    rural_tier_l = int(cfg["demand_tiers"]["rural_tier_large"])
    rural_tier_s = int(cfg["demand_tiers"]["rural_tier_small"])
    rural_cutoff = int(cfg["demand_tiers"]["rural_cutoff_size"])
    diesel_price = float(cfg["diesel_price_usd_per_l"])
    max_grid_ext = float(cfg["grid"]["max_extension_dist_km"])
    start_year   = int(cfg["scenario"]["start_year"])
    end_year     = int(cfg["scenario"]["end_year"])
    years        = cfg["scenario"]["years_of_analysis"]
    pop_future   = float(cfg["scenario"]["pop_end_year"])
    urb_future   = float(cfg["scenario"]["urban_ratio_end_year"])
    elec_target  = float(cfg["scenario"]["elec_target"])

    sa_diesel_cost = {"diesel_price": diesel_price, "efficiency": 0.28,
                      "diesel_truck_consumption": 14, "diesel_truck_volume": 300}
    mg_diesel_cost = {"diesel_price": diesel_price, "efficiency": 0.33,
                      "diesel_truck_consumption": 33.7, "diesel_truck_volume": 15000}

    # Mini-grid size threshold, in households; read from config (see technology_options).
    min_mg_size = int(cfg.get("technology_options", {}).get("min_mg_size", 100))
    techs       = ["Grid", "SA_PV", "MG_PVHybrid", "MG_Wind", "MG_Hydro"]
    tech_codes  = [1, 3, 5, 6, 7]
    all_off_grid = ["SA_PV", "MG_PVHybrid", "MG_Wind", "MG_Hydro"]

    mg_pv_hybrid_params = build_mg_pv_hybrid_params(cfg, min_mg_size)

    onsseter = SettlementProcessor.__new__(SettlementProcessor)
    onsseter.df = spine_df.copy()

    onsseter.condition_df()
    onsseter.df[SET_GRID_PENALTY] = 1
    onsseter.df[SET_WINDCF] = onsseter.calc_wind_cfs(onsseter.df[SET_WINDVEL])
    onsseter.add_xy_3395()
    onsseter.df["PerHouseholdDemand"] = 0
    if "ElectrificationOrder" not in onsseter.df.columns:
        onsseter.df["ElectrificationOrder"] = 0
    onsseter.df[SET_MV_DIST_PLANNED] = onsseter.df[SET_MV_DIST_CURRENT]
    onsseter.df[SET_HV_DIST_PLANNED] = onsseter.df[SET_HV_DIST_CURRENT]

    onsseter.project_pop_and_urban(pop_future, urb_future, start_year, years)
    onsseter.current_mv_line_dist()
    onsseter.prepare_wtf_tier_columns(*[TIERS[i] for i in range(1, 6)])

    x_coords = x_tx_orig.copy()
    y_coords = y_tx_orig.copy()
    new_lines = {}
    grid_cap_gen_limit = 9999 * 1000 * 10
    grid_connect_limit = 9999 * 1000 * 10

    for i_yr, year in enumerate(years):
        time_step  = year - (years[i_yr - 1] if i_yr > 0 else start_year)
        start_yr_t = year - time_step

        grid_cap_gen_limit = 9999 * 1000 * time_step
        grid_connect_limit = 9999 * 1000 * time_step

        techs_obj = build_tech_objects(cfg, start_yr_t, end_year)
        grid_calc         = techs_obj["grid"]
        mg_hydro_calc     = techs_obj["mg_hydro"]
        sa_pv_calc        = techs_obj["sa_pv"]
        mg_pv_hybrid_calc = techs_obj["mg_pv_hybrid"]
        sa_diesel_calc    = techs_obj["sa_diesel"]

        if sa_pv_capex_mult != 1.0:
            sa_pv_calc.capital_cost = {
                k: v * sa_pv_capex_mult
                for k, v in sa_pv_calc.capital_cost.items()
            }

        onsseter.calculate_demand(year, hh_r, hh_u, time_step,
                                  urban_tier, rural_tier_l, rural_tier_s,
                                  rural_cutoff, TIERS)

        if n_mid is not None and "PE_ratio" in onsseter.df.columns:
            pe = onsseter.df["PE_ratio"].clip(lower=0.1)
            onsseter.df[SET_AVERAGE_TO_PEAK] = (1.0 / pe).clip(upper=1.0)

        onsseter.calculate_unmet_demand(year, reliability=0.963)
        onsseter.diesel_cost_columns(sa_diesel_cost, mg_diesel_cost, year)

        if pv_lut_cache is not None and year in pv_lut_cache:
            lut = pv_lut_cache[year]
            lcoe_pv_lut = lut["lcoe"]; inv_pv_lut = lut["inv"]; cap_pv_lut = lut["cap"]
            ghi_min = lut["ghi_min"]; ghi_max = lut["ghi_max"]
            diesel_min = lut["diesel_min"]; diesel_max = lut["diesel_max"]
        else:
            _p(f"    [{arm_label}] Building PV-hybrid lookup year={year} …")
            t0_lut = time.time()
            (lcoe_pv_lut, inv_pv_lut, cap_pv_lut, _,
             ghi_min, ghi_max, diesel_min, diesel_max) = build_pv_hybrid_lookup(
                onsseter, ghi_profile, temp_profile,
                year, time_step, end_year, mg_pv_hybrid_params, start_yr_t,
            )
            _p(f"    PV-hybrid lookup done in {time.time()-t0_lut:.0f}s")
            if pv_lut_cache is not None:
                pv_lut_cache[year] = {
                    "lcoe": lcoe_pv_lut, "inv": inv_pv_lut, "cap": cap_pv_lut,
                    "ghi_min": ghi_min, "ghi_max": ghi_max,
                    "diesel_min": diesel_min, "diesel_max": diesel_max,
                }

        hybrid_lcoe_pv, hybrid_inv_pv, hybrid_cap_pv = apply_pv_hybrid_lookup(
            onsseter, lcoe_pv_lut, inv_pv_lut, cap_pv_lut,
            year, time_step, mg_pv_hybrid_params,
            ghi_min, ghi_max, diesel_min, diesel_max,
        )
        mg_pv_hybrid_calc.hybrid_fuel      = hybrid_lcoe_pv
        mg_pv_hybrid_calc.hybrid_investment = hybrid_inv_pv
        mg_pv_hybrid_calc.hybrid_capacity   = hybrid_cap_pv

        mg_wind_calc = techs_obj["mg_wind_hybrid"]
        n = len(onsseter.df)
        mg_wind_calc.hybrid_fuel       = pd.Series(np.full(n, 99.0))
        mg_wind_calc.hybrid_investment = pd.Series(np.zeros(n))
        mg_wind_calc.hybrid_capacity   = pd.Series(np.zeros(n))

        (sa_pv_inv, sa_pv_cap, mg_pv_h_inv, mg_pv_h_cap,
         mg_wind_inv, mg_wind_cap, mg_hydro_inv, mg_hydro_cap) = \
            onsseter.calculate_off_grid_lcoes(
                mg_hydro_calc, mg_wind_calc, sa_pv_calc, mg_pv_hybrid_calc,
                year, end_year, time_step, techs, tech_codes, min_mg_size, 0,
            )
        compute_offgrid_min(onsseter, year, all_off_grid)

        grid_inv, grid_cap, grid_cap_gen_limit, grid_conn_limit = \
            onsseter.pre_electrification(
                float(cfg["grid"]["generation_cost_usd_kwh"]),
                year, time_step, end_year, grid_calc, sa_diesel_calc,
                "None", grid_cap_gen_limit, grid_connect_limit,
            )
        onsseter.max_extension_dist(
            year, time_step, end_year, start_yr_t, grid_calc, sa_diesel_calc,
            "None", 0, 0,
        )
        onsseter.pre_selection(elec_target, year, time_step, 2, 5)

        (onsseter.df["Grid" + str(year)],
         onsseter.df["MinGridDist" + str(year)],
         grid_inv, grid_cap, x_coords, y_coords,
         new_lines[year]) = \
            onsseter.elec_extension_numba(
                grid_calc, sa_diesel_calc, "None",
                max_grid_ext, year, end_year, time_step,
                grid_cap_gen_limit, grid_connect_limit,
                x_coords, y_coords, mg_interconnection=False,
            )

        onsseter.results_columns(techs, tech_codes, year, time_step, 0, False)
        onsseter.calculate_investments_and_capacity(
            sa_pv_inv, sa_pv_cap, mg_pv_h_inv, mg_pv_h_cap,
            mg_wind_inv, mg_wind_cap, mg_hydro_inv, mg_hydro_cap,
            grid_inv, grid_cap, year,
        )
        final_step = (i_yr == len(years) - 1)
        onsseter.check_grid_limitations(grid_conn_limit, grid_cap_gen_limit,
                                         year, time_step, final_step)
        onsseter.apply_limitations(elec_target, year, time_step, 2)

    return onsseter.df


def compute_delta_lcoe_pct(df_r0: pd.DataFrame, df_r1: pd.DataFrame,
                            year: int = ANALYSIS_YEAR) -> float:
    lc = f"MinimumOverallLCOE{year}"
    ec = f"EnergyPerSettlement{year}"
    c0 = (df_r0[lc] * df_r0[ec]).sum()
    c1 = (df_r1[lc] * df_r1[ec]).sum()
    return (c1 - c0) / c0 * 100.0 if c0 != 0 else float("nan")


def count_sapv_to_grid(df_r0: pd.DataFrame, df_r1: pd.DataFrame,
                        year: int = ANALYSIS_YEAR) -> int:
    fc0 = df_r0[f"FinalElecCode{year}"]
    fc1 = df_r1[f"FinalElecCode{year}"]
    return int(((fc0 == 3) & (fc1 == 1)).sum())


def make_full_pair(spine_n20: pd.DataFrame, n_mid: int,
                   p1: float = None, p_inf: float = None, p_step: float = None
                   ) -> tuple:
    """Return (spine_r0, spine_r1) with optional custom Lorenzoni anchors."""
    pe_cols = [c for c in spine_n20.columns if c.startswith("PE_ratio")]
    extra   = ["N_hh_val"] if "N_hh_val" in spine_n20.columns else []

    spine_r0 = spine_n20.drop(columns=pe_cols + extra, errors="ignore").copy()

    if p1 is not None:
        # Recompute PE_ratio from sampled Lorenzoni anchors
        is_u = (spine_n20["IsUrban"] > 1).values
        if "N_hh_val" in spine_n20.columns:
            N_hh = np.maximum(1, spine_n20["N_hh_val"].values)
        elif "N_hh" in spine_n20.columns:
            N_hh = np.maximum(1, spine_n20["N_hh"].values)   # s05's value, at the analysis-year population
        else:
            raise RuntimeError("spine carries no N_hh column; re-run s05 (2026-09-04 or later)")
        spine_r1 = spine_r0.copy()
        spine_r1["PE_ratio"] = pe_from_n(N_hh, N_mid=float(n_mid),
                                          P_1=p1, P_inf=p_inf, P_step=p_step)
    else:
        pe_tag = f"PE_ratio_n{n_mid}"
        if pe_tag in spine_n20.columns:
            spine_r1 = spine_n20.drop(
                columns=[c for c in pe_cols if c != pe_tag] + extra,
                errors="ignore"
            ).copy().rename(columns={pe_tag: "PE_ratio"})
        else:
            is_u = (spine_n20["IsUrban"] > 1).values
            N_hh = np.maximum(1, spine_n20["Pop"].values / np.where(is_u, 4.6, 5.0))
            spine_r1 = spine_r0.copy()
            spine_r1["PE_ratio"] = pe_from_n(N_hh, N_mid=float(n_mid))

    return spine_r0, spine_r1


# ── §2  LHS VALIDATION ON THE FULL SPINE ─────────────────────────────────────
def task0_lhs_validation(spine_n20, cfg_base, x_tx, y_tx,
                          ghi_profile, temp_profile, wind_profile, pv_lut_cache):
    """
    Pick 3 LHS samples (P5, P50, P95 of corrected ΔLCOE% distribution) from the
    the s08 LHS CSV and re-run on the FULL spine, at each sample's own N_mid. Compare against the
    bias-corrected subsample values.
    """
    print("\n" + "="*70)
    print("  LHS Full-Spine Validation (3 samples)")
    print("="*70)

    lhs_df = pd.read_csv(LHS_CSV)
    corrected = lhs_df["delta_lcoe_pct_corrected"].sort_values()
    # Pick indices closest to P5, P50, P95 of corrected distribution
    targets = corrected.quantile([0.05, 0.50, 0.95]).values
    sample_idxs = []
    for t in targets:
        closest = (corrected - t).abs().idxmin()
        sample_idxs.append(closest)
    print(f"  Selected LHS sample indices (P5/P50/P95): {sample_idxs}")

    results = []
    for i, idx in enumerate(sample_idxs):
        row = lhs_df.loc[idx]
        p1_s    = row["P1"];   p_inf_s = row["Pinf"]; p_step_s = row["Pstep"]
        dr_s    = row["discount_rate"]
        dp_s    = row["diesel_price"]
        nm_s    = row["N_mid"]
        sub_raw = row["delta_lcoe_pct_raw"]
        sub_cor = row["delta_lcoe_pct_corrected"]
        sub_sw  = row["switch_count"]

        label = ["P5", "P50", "P95"][i]
        print(f"\n  [{i+1}/3] Sample {int(row['sample'])} ({label}):")
        print(f"    P1={p1_s:.3f}  Pinf={p_inf_s:.3f}  Pstep={p_step_s:.3f}")
        print(f"    discount_rate={dr_s:.3f}  diesel={dp_s:.2f}  N_mid={nm_s:.1f}")
        print(f"    Subsample: raw={sub_raw:+.2f}%  corrected={sub_cor:+.2f}%  sw={sub_sw:.0f}")

        cfg_s = copy.deepcopy(cfg_base)
        for k in ("grid", "mini_grid", "standalone"):
            cfg_s["discount_rates"][k] = float(dr_s)
        cfg_s["diesel_price_usd_per_l"] = float(dp_s)

        nm = max(10.0, min(50.0, float(nm_s)))      # the sampled value, as s08 solved it

        spine_r0, spine_r1 = make_full_pair(
            spine_n20, n_mid=nm,
            p1=p1_s, p_inf=p_inf_s, p_step=p_step_s
        )

        t0 = time.time()
        print(f"    Running R0 on full spine …")
        df_r0 = run_arm_full("LHS_val_R0", spine_r0, cfg_s, x_tx, y_tx,
                              ghi_profile, temp_profile, wind_profile,
                              n_mid=None, pv_lut_cache=None, silent=True)
        print(f"    Running R1 on full spine …")
        df_r1 = run_arm_full("LHS_val_R1", spine_r1, cfg_s, x_tx, y_tx,
                              ghi_profile, temp_profile, wind_profile,
                              n_mid=nm, pv_lut_cache=None, silent=True)

        full_delta = compute_delta_lcoe_pct(df_r0, df_r1)
        full_sw    = count_sapv_to_grid(df_r0, df_r1)
        elapsed    = time.time() - t0

        diff_from_corrected = full_delta - sub_cor
        print(f"    Full-spine ΔLCOE% = {full_delta:+.2f}%  "
              f"(corrected subsample = {sub_cor:+.2f}%  "
              f"diff = {diff_from_corrected:+.2f}pp)")
        print(f"    Full-spine switches = {full_sw:,}  "
              f"(subsample = {sub_sw:.0f})")
        print(f"    Elapsed: {elapsed:.0f}s")

        results.append({
            "label":            label,
            "sample":           int(row["sample"]),
            "P1":               p1_s, "Pinf": p_inf_s, "Pstep": p_step_s,
            "discount_rate":    dr_s, "diesel_price": dp_s, "N_mid": nm_s,
            "subsample_raw":    sub_raw,
            "subsample_corrected": sub_cor,
            "subsample_switch": sub_sw,
            "fullspine_delta":  full_delta,
            "fullspine_switch": full_sw,
            "diff_corrected_pp": diff_from_corrected,
            "elapsed_s":        elapsed,
        })

    df_out = pd.DataFrame(results)
    out_path = OUTDIR / "2026-09-02_lhs_fullspine_validation.csv"
    df_out.to_csv(out_path, index=False)
    print(f"\n  Saved: {out_path.name}")
    return df_out


# ── §3  GRID-SIDE OAT ────────────────────────────────────────────────────────
def task1_grid_oat(spine_n20, cfg_base, x_tx, y_tx,
                    ghi_profile, temp_profile, wind_profile, pv_lut_cache):
    """
    OAT at central case (N_mid=20, Tier 3) varying:
    (a) Grid capacity cost: ±30% of 1,441.1 USD/kW (Egli 2023 Table S8 cross-country range)
    (b) Grid generation cost: {0.013 central, 0.05 drought/new-build proxy}

    Gate: central variant must reproduce the s06 central headline (within OAT_TOL_PP pp).
    Reports ΔLCOE% AND SA_PV→Grid switch count per variant.
    """
    print("\n" + "="*70)
    print("  Grid-Side OAT Sensitivity")
    print("="*70)

    # Load the standard R1_n20 PE spine
    spine_r0, spine_r1_n20 = make_full_pair(spine_n20, n_mid=20)

    # OAT variants: (label, grid_cap_cost, grid_gen_cost, note)
    oat_variants = [
        ("central",   GRID_CAP_COST_CENTRAL,        GRID_GEN_COST_CENTRAL, f"Gate check — must reproduce the s06 central headline (+{STAGE4_DELTA:.1f}%/{STAGE4_SWITCHES:,})"),
        ("cap-30pct", GRID_CAP_COST_CENTRAL * 0.70, GRID_GEN_COST_CENTRAL, "Grid cap cost −30% (lower bound Egli 2023 cross-country range)"),
        ("cap+30pct", GRID_CAP_COST_CENTRAL * 1.30, GRID_GEN_COST_CENTRAL, "Grid cap cost +30% (upper bound Egli 2023 cross-country range)"),
        ("gen-drought",GRID_CAP_COST_CENTRAL,        0.05,                  "Grid gen cost 0.05 USD/kWh (drought / new-build proxy)"),
    ]

    results = []
    gate_passed = False

    for variant, cap_cost, gen_cost, note in oat_variants:
        print(f"\n  Variant: {variant}")
        print(f"    cap_cost={cap_cost:.1f} USD/kW  gen_cost={gen_cost:.4f} USD/kWh")
        print(f"    Note: {note}")

        cfg_v = copy.deepcopy(cfg_base)
        cfg_v["grid"]["capacity_investment_cost_usd_kw"] = cap_cost
        cfg_v["grid"]["generation_cost_usd_kwh"]         = gen_cost

        t0 = time.time()
        # pv_lut_cache is deliberately NOT used here: reusing a cache built earlier in this script
        # draws from the random stream at a different point and shifts mini-grid costs enough to move
        # a settlement at the grid-extension margin. Rebuilding per arm, as s06 does, makes the
        # central variant reproduce s06 exactly. Costs ~2 min per arm. See REPRODUCING.md §9.
        print(f"    Running R0 on full spine …")
        df_r0 = run_arm_full("OAT_R0", spine_r0, cfg_v, x_tx, y_tx,
                              ghi_profile, temp_profile, wind_profile,
                              n_mid=None, pv_lut_cache=None, silent=True)
        print(f"    Running R1 on full spine …")
        df_r1 = run_arm_full("OAT_R1", spine_r1_n20, cfg_v, x_tx, y_tx,
                              ghi_profile, temp_profile, wind_profile,
                              n_mid=20, pv_lut_cache=None, silent=True)

        delta  = compute_delta_lcoe_pct(df_r0, df_r1)
        sw     = count_sapv_to_grid(df_r0, df_r1)
        elapsed = time.time() - t0

        print(f"    ΔLCOE% = {delta:+.2f}%  switches = {sw:,}  ({elapsed:.0f}s)")

        if variant == "central":
            gate_delta = abs(delta - STAGE4_DELTA) <= OAT_TOL_PP
            # Switch count is gated exactly: the hybrid LUT is now rebuilt per arm (as in s06),
            # so the central variant must reproduce the headline 33,665 with no residual.
            sw_resid  = abs(sw - STAGE4_SWITCHES)
            gate_sw   = sw_resid <= OAT_SWITCH_TOL
            print(f"    GATE dLCOE: |{delta:.2f} - {STAGE4_DELTA}| = {abs(delta-STAGE4_DELTA):.2f}pp <= {OAT_TOL_PP}pp -> {'PASS' if gate_delta else 'FAIL'}")
            print(f"    GATE switch: |{sw:,} - {STAGE4_SWITCHES:,}| = {sw_resid} <= {OAT_SWITCH_TOL} -> {'PASS' if gate_sw else 'FAIL'}")
            if sw_resid:
                print(f"    NOTE: {sw_resid} settlement(s) differ from the headline run "
                      f"(cached vs rebuilt hybrid LUT; documented in REPRODUCING.md).")
            gate_ok = gate_delta and gate_sw
            if not gate_ok:
                print(f"    WARNING: Central case gate FAILED. "
                      f"OAT variants may not be trusted. Continuing anyway.")
            gate_passed = gate_ok

        results.append({
            "variant":        variant,
            "grid_cap_cost":  cap_cost,
            "grid_gen_cost":  gen_cost,
            "delta_lcoe_pct": delta,
            "switch_count":   sw,
            "elapsed_s":      elapsed,
            "note":           note,
        })

        # Per-variant outputs are written under new filenames; existing outputs are not overwritten
        if variant != "central":
            tag = variant.replace("+", "plus").replace("-", "minus")
            out_r0 = OUTDIR / f"2026-08_final_oat_{tag}_R0.csv"
            out_r1 = OUTDIR / f"2026-08_final_oat_{tag}_R1_n20.csv"
            df_r0.sort_values("id", inplace=True)
            df_r1.sort_values("id", inplace=True)
            df_r0.to_csv(out_r0, index=False)
            df_r1.to_csv(out_r1, index=False)
            print(f"    Saved: {out_r0.name}, {out_r1.name}")

    df_out = pd.DataFrame(results)
    out_path = OUTDIR / "2026-08_final_oat_grid_costs.csv"
    df_out.to_csv(out_path, index=False)
    print(f"\n  Saved: {out_path.name}")

    print("\n  OAT Summary:")
    print(df_out[["variant","grid_cap_cost","grid_gen_cost","delta_lcoe_pct","switch_count"]].to_string(index=False))

    return df_out, gate_passed


# ── §4  MAIN ─────────────────────────────────────────────────────────────────
def main():
    t_total = time.time()
    print("="*70)
    print("  Post-GSA Tasks 0-addendum + 1 — Full-Spine Computations")
    print(f"  Seed: 42 (OAT arms); LHS samples from the s08 CSV (seed=43)")
    print("="*70)

    # Guard: verify protected files exist and will not be overwritten
    for f in PROTECTED:
        if f.exists():
            print(f"  Guard OK (not overwriting): {f.name}")

    print("\n[1/5] Loading profiles and transmission network …")
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile               = load_wind_profile(WIND_PROFILE)
    print(f"  Annual GHI: {ghi_profile.sum()/1000:.0f} kWh/m²/yr  "
          f"| Mean wind: {wind_profile.mean():.2f} m/s")
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    print(f"  TX start points: {len(x_tx):,}")
    if len(x_tx) == 0:
        raise RuntimeError(
            f"transmission network at {TX_SHP} yielded zero starting points; "
            "grid extension would be silently disabled and the run would be wrong"
        )

    cfg_base = load_config()

    # Load GRID3 full spine
    print("\n[2/5] Loading full GRID3 spine (270,526 settlements) …")
    spine_n20 = pd.read_csv(PE_N20)
    if "PE_ratio" in spine_n20.columns:
        spine_n20 = spine_n20.rename(columns={"PE_ratio": "PE_ratio_n20"})
    if "N_hh" in spine_n20.columns:
        spine_n20 = spine_n20.rename(columns={"N_hh": "N_hh_val"})
    for nm, path in [(10, PE_N10), (50, PE_N50)]:
        if path.exists():
            tmp = pd.read_csv(path, usecols=["id", "PE_ratio"])
            spine_n20 = spine_n20.merge(
                tmp.rename(columns={"PE_ratio": f"PE_ratio_n{nm}"}), on="id", how="left"
            )
    print(f"  Loaded: {len(spine_n20):,} settlements")

    # The PV-hybrid lookup table is rebuilt inside every arm (pv_lut_cache=None), as s06 does.
    print("\n[3/5] PV-hybrid lookup table rebuilt per arm.")
    pv_lut_cache = None

    # LHS full-spine validation
    print("\n[4/5] LHS full-spine validation …")
    lhs_val_df = task0_lhs_validation(
        spine_n20, cfg_base, x_tx, y_tx,
        ghi_profile, temp_profile, wind_profile, pv_lut_cache
    )

    if "--lhs-only" in sys.argv:
        print("\n  --lhs-only: grid-side OAT block skipped")
        print(lhs_val_df[["label", "N_mid", "fullspine_delta", "subsample_corrected",
                          "diff_corrected_pp", "fullspine_switch", "subsample_switch"]].to_string(index=False))
        print(f"\nOutputs in: {OUTDIR}")
        return

    # Grid-side OAT
    print("\n[5/5] Grid-side OAT …")
    oat_df, gate_ok = task1_grid_oat(
        spine_n20, cfg_base, x_tx, y_tx,
        ghi_profile, temp_profile, wind_profile, pv_lut_cache
    )

    # Final summary
    elapsed_total = time.time() - t_total
    print("\n" + "="*70)
    print(f"  COMPLETE — Total elapsed: {elapsed_total/60:.1f} min")
    print("="*70)
    print("\n  LHS full-spine validation:")
    print(lhs_val_df[["label","fullspine_delta","subsample_corrected",
                       "diff_corrected_pp","fullspine_switch","subsample_switch"]].to_string(index=False))
    print("\n  Grid-side OAT:")
    print(oat_df[["variant","grid_cap_cost","grid_gen_cost","delta_lcoe_pct","switch_count"]].to_string(index=False))
    print(f"\n  Gate (central reproduces +{STAGE4_DELTA:.1f}%): {'PASSED ✓' if gate_ok else 'FAILED ✗'}")
    print(f"\nOutputs in: {OUTDIR}")


if __name__ == "__main__":
    main()
