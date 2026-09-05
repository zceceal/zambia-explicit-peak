"""
s06_run_arms.py — the controlled comparison: R0 and R1 least-cost solves.

Inputs:
  R0/R1 base: data/processed/zambia_grid3_spine_pe_n20.csv  (pre-processed by
              s05_compute_peak_ratios.py — IsUrban_type dropped, border slivers reassigned,
              Pop2030, N_hh, N_hh_2020 and PE_ratio added)
  N_mid sweep PE: zambia_grid3_spine_pe_n10.csv, zambia_grid3_spine_pe_n50.csv

Outputs (RUN_LABEL below sets the prefix; do not overwrite an existing run):
  data/onsset_outputs/2026-08_final_lcoe_R0.csv
  data/onsset_outputs/2026-08_final_lcoe_R1_n10.csv
  data/onsset_outputs/2026-08_final_lcoe_R1_n20.csv    (central case)
  data/onsset_outputs/2026-08_final_lcoe_R1_n50.csv
  data/onsset_outputs/2026-08_final_lcoe_tech_split.csv

Shared loaders (solar and wind profiles, config, technology objects) come from
onsset_helpers.py. Four arms: R0 (once) + R1 x {10, 20, 50}, seeds fixed with
np.random.seed(42) before each arm.
"""

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Third-party deprecation noise only; see onsset_helpers.py for the filter's scope.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(HERE))

# Shared helpers (profile loaders, technology builders, config)
from onsset_helpers import (
    load_solar_profile, load_wind_profile,
    build_pv_hybrid_lookup, apply_pv_hybrid_lookup,
    build_wind_hybrid_lookup, apply_wind_hybrid_lookup,
    compute_offgrid_min, per_connection_stats,
    build_tech_objects, build_mg_pv_hybrid_params, build_mg_wind_hybrid_params,
    load_config,
    HV_LINE_TYPE, HV_LINE_COST, HV_MV_SUB_COST, HV_MV_SUB_TYPE,
    MV_LINE_TYPE, MV_LINE_AMPERAGE, MV_LINE_COST,
    LV_LINE_TYPE, LV_LINE_COST, LV_LINE_MAX_LEN,
    SERV_TRANSF_TYPE, SERV_TRANSF_COST, MAX_NODES_PER_TRANS, CONN_COST_PER_HH, TIERS,
    _PHYSICAL_INPUT_COLS,
)

import yaml

from onsset import (
    SettlementProcessor, Technology,
    SET_GRID_PENALTY, SET_WINDVEL, SET_WINDCF, SET_AVERAGE_TO_PEAK,
    SET_GHI, SET_TIER, SET_ENERGY_PER_CELL, SET_MG_DIESEL_FUEL,
    SET_POP, SET_ELEC_FINAL_CODE,
    SET_LCOE_MG_PV_HYBRID, SET_LCOE_MG_WIND,
    SET_MIN_OFFGRID_LCOE, SET_MIN_OFFGRID,
    SET_MV_DIST_PLANNED, SET_HV_DIST_PLANNED,
    SET_MV_DIST_CURRENT, SET_HV_DIST_CURRENT,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
PE_N10     = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n10.csv"
PE_N20     = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"
PE_N50     = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n50.csv"
CONFIG     = HERE / "config.yaml"
OUTDIR     = REPO / "data" / "onsset_outputs"

TX_SHP     = (REPO / "data" / "raw" / "zambia" / "grid" /
              "transmission_network_wb" / "zambia-electricity-transmission-network" /
              "Zambia Electricity Transmission Network.shp")
SOLAR_PROFILE = (REPO / "data" / "raw" / "zambia" / "renewables_hourly" /
                 "solar" / "solar_lusaka.csv")
WIND_PROFILE  = (REPO / "data" / "raw" / "zambia" / "renewables_hourly" /
                 "wind" / "wind_lusaka.csv")

RUN_LABEL = "2026-08_final_lcoe"   # prefix for every file this script writes

np.random.seed(42)


def assert_base_cols_match(df_ref: pd.DataFrame, df_arm: pd.DataFrame, label: str,
                           pe_cols=("PE_ratio",)) -> None:
    """
    Pre-run guard: every column an arm shares with the R0 reference frame must be identical, so
    the ONLY input difference between arms is the P/E representation.  Fails the run otherwise.

    The check originated inline in s12_run_2050_horizon.py; it lives here so every run script can
    call the same one on its own arm frames.
    """
    skip      = set(pe_cols)
    base_cols = [c for c in df_arm.columns if c not in skip]
    missing   = [c for c in base_cols if c not in df_ref.columns]
    assert not missing, f"{label}: base columns absent from R0: {missing}"
    diff = [c for c in base_cols if not df_ref[c].equals(df_arm[c])]
    assert not diff, f"{label}: base columns differ from R0: {diff}"
    print(f"  {label}: base columns byte-identical to R0 "
          f"(only {', '.join(sorted(skip))} differs) — PASS")


def run_arm(arm_label: str, spine_df: pd.DataFrame, cfg: dict,
            x_tx_orig: np.ndarray, y_tx_orig: np.ndarray,
            ghi_profile: np.ndarray, temp_profile: np.ndarray,
            wind_profile: np.ndarray,
            n_mid: int = None) -> tuple:
    """
    Run one LCOE arm on a fresh copy of spine_df.
    arm_label: 'R0' or 'R1_n{n_mid}'
    n_mid: if not None, apply PE_ratio from column 'PE_ratio' (already set on spine_df)
    Returns (onsseter, summary, hybrid_status)
    """
    np.random.seed(42)

    print(f"\n{'='*65}")
    print(f"  ARM {arm_label}  (N_mid={n_mid if n_mid else 'N/A (R0)'})")
    print(f"{'='*65}")
    t_arm_start = time.time()

    hh_u         = float(cfg["household_size"]["urban"])
    hh_r         = float(cfg["household_size"]["rural"])
    urban_tier   = int(cfg["demand_tiers"]["urban_tier"])
    rural_tier_l = int(cfg["demand_tiers"]["rural_tier_large"])
    rural_tier_s = int(cfg["demand_tiers"]["rural_tier_small"])
    rural_cutoff = int(cfg["demand_tiers"]["rural_cutoff_size"])
    losses       = float(cfg["grid"]["losses"])
    grid_price   = float(cfg["grid"]["generation_cost_usd_kwh"])
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

    # Mini-grid size threshold, in households. Read from config so that a parameter which
    # decides which technologies exist is visible and auditable; default preserves the
    # published value exactly.
    min_mg_size = int(cfg.get("technology_options", {}).get("min_mg_size", 100))
    techs       = ["Grid", "SA_PV", "MG_PVHybrid", "MG_Wind", "MG_Hydro"]
    tech_codes  = [1, 3, 5, 6, 7]
    all_off_grid = ["SA_PV", "MG_PVHybrid", "MG_Wind", "MG_Hydro"]

    mg_pv_hybrid_params  = build_mg_pv_hybrid_params(cfg, min_mg_size)
    mg_wind_hybrid_params = build_mg_wind_hybrid_params(cfg, min_mg_size)

    # use the in-memory DataFrame copy
    onsseter = SettlementProcessor.__new__(SettlementProcessor)
    onsseter.df = spine_df.copy()

    onsseter.condition_df()
    onsseter.df[SET_GRID_PENALTY] = 1
    onsseter.df[SET_WINDCF] = onsseter.calc_wind_cfs(onsseter.df[SET_WINDVEL])
    onsseter.add_xy_3395()

    onsseter.df["PerHouseholdDemand"] = 0
    if "ElectrificationOrder" not in onsseter.df.columns:
        onsseter.df["ElectrificationOrder"] = 0

    # OnSSET's planned-line field must include the existing network (it is
    # tested against MaxGridDist). No qualifying planned layer: planned = current.
    onsseter.df[SET_MV_DIST_PLANNED] = onsseter.df[SET_MV_DIST_CURRENT]
    onsseter.df[SET_HV_DIST_PLANNED] = onsseter.df[SET_HV_DIST_CURRENT]

    # GUARD: s05 evaluated the household count N (and therefore PE_ratio) on its own call to
    # project_pop_and_urban(), and wrote that Pop{year} into the spine. The projection below
    # overwrites the column. The two must agree on every settlement, or the peak would be
    # sized on a different population from the energy it is paired with. The column has
    # travelled with its row through condition_df()'s sort, so a positional compare is valid.
    ay_col = f"Pop{years[0]}"
    spine_pop_ay = onsseter.df[ay_col].to_numpy().copy() if ay_col in onsseter.df.columns else None

    onsseter.project_pop_and_urban(pop_future, urb_future, start_year, years)

    if spine_pop_ay is not None:
        engine_pop_ay = onsseter.df[ay_col].to_numpy()
        n_diff = int((~np.isclose(spine_pop_ay, engine_pop_ay, rtol=0, atol=1e-6)).sum())
        assert n_diff == 0, (
            f"{ay_col} written by s05 differs from the engine's projection on {n_diff:,} "
            f"settlements: N and PE_ratio were evaluated on a different population from the "
            f"energy. Re-run s05 against the current config and calibration.")
        print(f"  {ay_col}: s05 projection == engine projection on all "
              f"{len(engine_pop_ay):,} settlements — PASS")
    else:
        raise RuntimeError(
            f"spine has no {ay_col} column — it was built by a pre-2026-09-04 s05 that evaluated "
            f"N at the base-year population. Re-run s05.")

    onsseter.current_mv_line_dist()
    onsseter.prepare_wtf_tier_columns(*[TIERS[i] for i in range(1, 6)])

    # Fresh copy of transmission start points for each arm
    x_coords = x_tx_orig.copy()
    y_coords = y_tx_orig.copy()
    new_lines_geojson = {}
    summary = {"arm": arm_label}
    hybrid_status = {"pv_ok": None, "wind_ok": None}

    for i, year in enumerate(years):
        time_step  = year - (years[i - 1] if i > 0 else start_year)
        start_yr_t = year - time_step
        print(f"\n  ── Year {year} (time_step={time_step}) ──")

        techs_obj         = build_tech_objects(cfg, start_yr_t, end_year)
        grid_calc         = techs_obj["grid"]
        mg_hydro_calc     = techs_obj["mg_hydro"]
        sa_pv_calc        = techs_obj["sa_pv"]
        mg_pv_hybrid_calc = techs_obj["mg_pv_hybrid"]
        mg_wind_calc      = techs_obj["mg_wind_hybrid"]
        sa_diesel_calc    = techs_obj["sa_diesel"]

        grid_cap_gen_limit = 9999 * 1000 * time_step
        grid_connect_limit = 9999 * 1000 * time_step

        onsseter.calculate_demand(year, hh_r, hh_u, time_step,
                                  urban_tier, rural_tier_l, rural_tier_s,
                                  rural_cutoff, TIERS)

        # Apply P/E override for R1 arms only
        if n_mid is not None and "PE_ratio" in onsseter.df.columns:
            pe = onsseter.df["PE_ratio"].clip(lower=0.1)
            onsseter.df[SET_AVERAGE_TO_PEAK] = (1.0 / pe).clip(upper=1.0)
            print(f"    R1 AverageToPeakLoadRatio: "
                  f"mean={onsseter.df[SET_AVERAGE_TO_PEAK].mean():.4f}  "
                  f"median={onsseter.df[SET_AVERAGE_TO_PEAK].median():.4f}")
            # GUARD (2026-08-16): the override above MUST run after calculate_demand,
            # which unconditionally resets AverageToPeakLoadRatio to the tier table.
            # If a refactor ever moves it earlier, R1 silently collapses onto R0 and the
            # experiment measures nothing. Fail loudly instead.
            assert onsseter.df[SET_AVERAGE_TO_PEAK].nunique() > 100, (
                "R1 arm but AverageToPeakLoadRatio is (near-)uniform - the P/E override "
                "was applied before calculate_demand overwrote it, or not at all.")

        onsseter.calculate_unmet_demand(year, reliability=0.963)
        onsseter.diesel_cost_columns(sa_diesel_cost, mg_diesel_cost, year)

        print(f"    Building PV-hybrid lookup …")
        t0 = time.time()
        (lcoe_pv_lut, inv_pv_lut, cap_pv_lut, _,
         ghi_min, ghi_max, diesel_min, diesel_max) = build_pv_hybrid_lookup(
            onsseter, ghi_profile, temp_profile,
            year, time_step, end_year, mg_pv_hybrid_params, start_yr_t,
        )
        print(f"    PV-hybrid lookup done in {time.time()-t0:.0f}s")

        hybrid_lcoe_pv, hybrid_inv_pv, hybrid_cap_pv = apply_pv_hybrid_lookup(
            onsseter, lcoe_pv_lut, inv_pv_lut, cap_pv_lut,
            year, time_step, mg_pv_hybrid_params,
            ghi_min, ghi_max, diesel_min, diesel_max,
        )
        mg_pv_hybrid_calc.hybrid_fuel      = hybrid_lcoe_pv
        mg_pv_hybrid_calc.hybrid_investment = hybrid_inv_pv
        mg_pv_hybrid_calc.hybrid_capacity   = hybrid_cap_pv
        hybrid_status["pv_ok"] = True

        print(f"    Building wind-hybrid lookup …")
        t0 = time.time()
        (lcoe_w_lut, inv_w_lut, cap_w_lut, _,
         wind_min, wind_max, w_diesel_min, w_diesel_max, wind_ok) = build_wind_hybrid_lookup(
            onsseter, wind_profile,
            year, time_step, end_year, mg_wind_hybrid_params, start_yr_t,
        )
        hybrid_status["wind_ok"] = wind_ok
        print(f"    Wind-hybrid lookup done in {time.time()-t0:.0f}s  (wind_ok={wind_ok})")

        if wind_ok:
            hybrid_lcoe_w, hybrid_inv_w, hybrid_cap_w = apply_wind_hybrid_lookup(
                onsseter, lcoe_w_lut, inv_w_lut, cap_w_lut,
                year, time_step, mg_wind_hybrid_params,
                wind_min, wind_max, w_diesel_min, w_diesel_max,
            )
            mg_wind_calc.hybrid_fuel       = hybrid_lcoe_w
            mg_wind_calc.hybrid_investment = hybrid_inv_w
            mg_wind_calc.hybrid_capacity   = hybrid_cap_w
        else:
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
                grid_price, year, time_step, end_year, grid_calc, sa_diesel_calc,
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
         new_lines_geojson[year]) = \
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

        final_step = (i == len(years) - 1)
        onsseter.check_grid_limitations(grid_conn_limit, grid_cap_gen_limit,
                                        year, time_step, final_step)
        onsseter.apply_limitations(elec_target, year, time_step, 2)

        code_col = "FinalElecCode" + str(year)
        inv_col  = "InvestmentCost" + str(year)
        cap_col  = "NewCapacity" + str(year)
        pop_col  = "Pop" + str(year)
        if code_col in onsseter.df.columns:
            tech_split = onsseter.df.groupby(code_col).agg(
                n_settlements=("id", "count"),
                population=(pop_col, "sum") if pop_col in onsseter.df.columns else ("Pop", "sum"),
                investment=(inv_col, "sum") if inv_col in onsseter.df.columns else (code_col, "count"),
                capacity=(cap_col, "sum")   if cap_col in onsseter.df.columns else (code_col, "count"),
            )
            summary[year] = tech_split.to_dict()
            tech_labels = {1: "Grid", 3: "SA_PV", 5: "MG_PVHybrid",
                           6: "MG_Wind", 7: "MG_Hydro", 99: "Unelectrified"}
            print(f"\n    Technology split ({year}):")
            print(f"    {'Code':<6} {'Label':<22} {'Settlements':>12} {'Population':>14} {'Investment $bn':>16}")
            print(f"    {'-'*72}")
            for code, row in tech_split.iterrows():
                lbl = tech_labels.get(int(code), str(code))
                n_val   = row.get("n_settlements", 0)
                pop_val = row.get("population", 0)
                inv_val = row.get("investment", 0)
                print(f"    {int(code):<6} {lbl:<22} {int(n_val):>12,} {pop_val:>14,.0f} {inv_val/1e9:>16.3f}")
            print(f"\n    Per-connection investment (median, inf excluded):")
            for tc, tl in [(1, "Grid"), (3, "SA_PV"), (5, "MG_PVHybrid"), (7, "MG_Hydro")]:
                med, n = per_connection_stats(onsseter.df, year, tc, tl)
                if not np.isnan(med):
                    print(f"      {tl:<18} median ${med:>10,.0f}/connection (n={n:,})")

    elapsed = time.time() - t_arm_start
    print(f"\n  ARM {arm_label} complete in {elapsed/60:.1f} min")
    return onsseter, summary, hybrid_status


def compare_arms(df0: pd.DataFrame, df1: pd.DataFrame, years: list,
                 label0: str, label1: str, pe_cols: list) -> dict:
    """
    Compare two arm result DataFrames. Returns switch counts and ΔInvestment.
    """
    tech_labels = {1: "Grid", 3: "SA_PV", 5: "MG_PVHybrid",
                   6: "MG_Wind", 7: "MG_Hydro", 99: "Unelectrified"}

    # byte-identity check
    common_cols = [c for c in df0.columns if c in df1.columns]
    pe_col_set  = set(pe_cols) | {"AverageToPeakLoadRatio"}
    diff_cols   = [c for c in common_cols if not df0[c].equals(df1[c])]
    phys_differ = [c for c in diff_cols if c in _PHYSICAL_INPUT_COLS]
    non_pe_diff = [c for c in diff_cols if c not in pe_col_set]
    print(f"\n  Byte-identity assertion ({label0} vs {label1}):")
    print(f"    Total differing columns:      {len(diff_cols)}")
    print(f"    Physical input cols differing: {phys_differ if phys_differ else 'none — PASS'}")
    print(f"    Non-PE differing (results):   {len(non_pe_diff)}")

    result = {}
    last_year = years[-1]

    print(f"\n  Technology split at {last_year}:")
    print(f"  {'Tech':<18} {label0+' sett':>12} {label0+' pop':>12} {label1+' sett':>12} {label1+' pop':>12}")
    print(f"  {'-'*72}")
    for code in [1, 3, 5, 6, 7, 99]:
        lbl = tech_labels.get(code, str(code))
        fc0 = df0["FinalElecCode" + str(last_year)]
        fc1 = df1["FinalElecCode" + str(last_year)]
        n0, p0 = (fc0 == code).sum(), df0.loc[fc0 == code, "Pop"].sum()
        n1, p1 = (fc1 == code).sum(), df1.loc[fc1 == code, "Pop"].sum()
        print(f"  {lbl:<18} {int(n0):>12,} {p0:>12,.0f} {int(n1):>12,} {p1:>12,.0f}")

    for year in years:
        fc0 = df0["FinalElecCode" + str(year)]
        fc1 = df1["FinalElecCode" + str(year)]
        n_switch = (fc0 != fc1).sum()
        inv0 = df0["InvestmentCost" + str(year)].sum() if ("InvestmentCost" + str(year)) in df0.columns else 0
        inv1 = df1["InvestmentCost" + str(year)].sum() if ("InvestmentCost" + str(year)) in df1.columns else 0
        result[year] = {"n_switch": int(n_switch), "inv_r0": inv0, "inv_r1": inv1,
                        "delta_inv": inv1 - inv0}
        print(f"\n  Year {year}: {n_switch:,} settlements switch  |  "
              f"ΔInv = ${(inv1-inv0)/1e9:+.3f} bn  "
              f"(R0: ${inv0/1e9:.3f} bn, {label1}: ${inv1/1e9:.3f} bn)")

    fc0 = df0["FinalElecCode" + str(last_year)]
    fc1 = df1["FinalElecCode" + str(last_year)]
    print(f"\n  Switch matrix {label0}→{label1} at {last_year}:")
    for from_code in [3, 1, 5, 7]:
        for to_code in [1, 3, 5, 7]:
            n = ((fc0 == from_code) & (fc1 == to_code)).sum()
            if n > 0:
                print(f"    {tech_labels.get(from_code,'?')} → {tech_labels.get(to_code,'?')}: {n:,}")

    return result


def main():
    print("=" * 65)
    print("  s06 — R0 / R1 LCOE run (N_mid sweep: 10, 20, 50)")
    print("=" * 65)

    cfg = load_config()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    print(f"\nLoading solar profile: {SOLAR_PROFILE.name}")
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    print(f"  Annual GHI: {ghi_profile.sum()/1000:.0f} kWh/m²/yr  |  "
          f"Mean temp: {temp_profile.mean():.1f}°C")
    print(f"Loading wind profile: {WIND_PROFILE.name}")
    wind_profile = load_wind_profile(WIND_PROFILE)
    print(f"  Mean wind (corrected to 20m): {wind_profile.mean():.2f} m/s")

    print(f"\nLoading transmission network …")
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    print(f"  Starting points: {len(x_tx):,}")
    if len(x_tx) == 0:
        raise RuntimeError(
            f"transmission network at {TX_SHP} yielded zero starting points; "
            "grid extension would be silently disabled and the run would be wrong"
        )

    years = cfg["scenario"]["years_of_analysis"]

    # ── Load spines, merge all PE columns ──────────────────────────────────────
    print("\n" + "=" * 65)
    print("  Loading GRID3 PE spines (base for all arms)")
    print("=" * 65)

    print(f"  Loading central-case spine (N_mid=20): {PE_N20.name}")
    df_base = pd.read_csv(PE_N20)
    print(f"  {len(df_base):,} rows × {len(df_base.columns)} columns")

    # Rename central PE column, then merge n10 and n50
    df_base = df_base.rename(columns={"PE_ratio": "PE_ratio_n20"})
    if "N_hh" in df_base.columns:
        df_base = df_base.rename(columns={"N_hh": "N_hh_n20"})

    for n_mid, path in [(10, PE_N10), (50, PE_N50)]:
        print(f"  Merging PE_ratio for N_mid={n_mid} from {path.name}")
        df_pe = pd.read_csv(path, usecols=["id", "PE_ratio"])
        df_base = df_base.merge(df_pe.rename(columns={"PE_ratio": f"PE_ratio_n{n_mid}"}),
                                on="id", how="left")

    pe_cols_all = ["PE_ratio_n10", "PE_ratio_n20", "PE_ratio_n50"]
    print(f"  PE columns merged: {pe_cols_all}")

    # ── Report P/E distribution on GRID3 spine ────────────────────────────────
    print("\n  P/E distribution on GRID3 spine (N_mid=20, central case):")
    pe20 = df_base["PE_ratio_n20"]
    is_urban = df_base["IsUrban"] > 1
    print(f"    Overall: min={pe20.min():.4f}, median={pe20.median():.4f}, "
          f"mean={pe20.mean():.4f}, max={pe20.max():.4f}")
    print(f"    Urban:   median={pe20[is_urban].median():.4f}, mean={pe20[is_urban].mean():.4f}")
    print(f"    Rural:   median={pe20[~is_urban].median():.4f}, mean={pe20[~is_urban].mean():.4f}")
    atp_mean = (1.0 / pe20.clip(lower=0.1)).clip(upper=1.0).mean()
    print(f"    Mean AverageToPeakLoadRatio (R1, N_mid=20): {atp_mean:.4f}")
    print(f"    (R0 tier-table value for Tier 3/5: 0.5 — R1 varies by settlement)")

    # ── Verify pre-run byte-identity for the shared spine ─────────────────────
    # For each R1 arm, we set df["PE_ratio"] from the appropriate column before running.
    # The base (non-PE) columns should be identical across all arms by construction — but
    # "by construction" is not a check, so each arm's frame is asserted against R0's below,
    # immediately before that arm runs (assert_base_cols_match).
    print("\n  Pre-run byte-identity: asserted per arm against R0 before each arm runs.")

    # ── Run R0 ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  Running R0 (energy-only baseline)")
    print("=" * 65)
    df_r0 = df_base.drop(columns=pe_cols_all, errors="ignore").copy()
    if "N_hh_n20" in df_r0.columns:
        df_r0 = df_r0.drop(columns=["N_hh_n20"])
    proc_r0, sum_r0, hs_r0 = run_arm("R0", df_r0, cfg, x_tx, y_tx,
                                     ghi_profile, temp_profile, wind_profile,
                                     n_mid=None)
    r0_path = OUTDIR / f"{RUN_LABEL}_R0.csv"
    proc_r0.df.sort_values("id", inplace=True)   # labels are now lat/lon order; restore id order on disk
    proc_r0.df.to_csv(r0_path, index=False)
    print(f"  R0 output → {r0_path.name}")

    # ── Run R1 arms ────────────────────────────────────────────────────────────
    results = {}
    proc_r1_n20 = None

    for n_mid in [20, 10, 50]:
        print(f"\n{'='*65}")
        print(f"  Running R1  (N_mid={n_mid})")
        print(f"{'='*65}")
        df_r1 = df_base.drop(columns=[c for c in pe_cols_all if f"_n{n_mid}" not in c],
                              errors="ignore").copy()
        # Rename the active PE column to the standard name
        df_r1 = df_r1.rename(columns={f"PE_ratio_n{n_mid}": "PE_ratio"})
        if "N_hh_n20" in df_r1.columns:
            df_r1 = df_r1.drop(columns=["N_hh_n20"])

        label = f"R1_n{n_mid}"
        assert_base_cols_match(df_r0, df_r1, label)
        proc_r1, sum_r1, hs_r1 = run_arm(label, df_r1, cfg, x_tx, y_tx,
                                          ghi_profile, temp_profile, wind_profile,
                                          n_mid=n_mid)
        r1_path = OUTDIR / f"{RUN_LABEL}_{label}.csv"
        proc_r1.df.sort_values("id", inplace=True)
        proc_r1.df.to_csv(r1_path, index=False)
        print(f"  {label} output → {r1_path.name}")

        # Compare vs R0
        print(f"\n  Comparing R0 vs {label}:")
        cmp = compare_arms(proc_r0.df, proc_r1.df, years, "R0", label,
                           pe_cols=["PE_ratio"])
        results[n_mid] = cmp

        if n_mid == 20:
            proc_r1_n20 = proc_r1

    # ── N_mid sweep summary ────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  N_MID SWEEP SUMMARY — switch count + ΔInvestment error bars")
    print("=" * 65)
    last_year = years[-1]
    print(f"\n  {'N_mid':>6}  {'Switches':>10}  {'ΔInv 2030 (R1-R0)':>20}  "
          f"{'ΔInv 2035 (R1-R0)':>20}")
    print(f"  {'-'*62}")
    for n_mid in [10, 20, 50]:
        r = results[n_mid]
        y1, y2 = years[0], years[1]
        print(f"  {n_mid:>6}  {r[last_year]['n_switch']:>10,}  "
              f"{r[y1]['delta_inv']/1e9:>+19.3f} bn  "
              f"{r[y2]['delta_inv']/1e9:>+19.3f} bn")

    # ── Write tech-split CSV ───────────────────────────────────────────────────
    rows = []
    for arm_label, df_arm in [("R0", proc_r0.df)]:
        for year in years:
            code_col = "FinalElecCode" + str(year)
            inv_col  = "InvestmentCost" + str(year)
            if code_col not in df_arm.columns:
                continue
            for code in [1, 3, 5, 6, 7, 99]:
                mask = df_arm[code_col] == code
                rows.append({"year": year, "arm": arm_label, "n_mid": "N/A",
                              "tech_code": code,
                              "n_settlements": int(mask.sum()),
                              "population": float(df_arm.loc[mask, "Pop"].sum()),
                              "investment_usd": float(df_arm.loc[mask, inv_col].sum()) if inv_col in df_arm.columns else np.nan})

    for n_mid in [10, 20, 50]:
        r1_path = OUTDIR / f"{RUN_LABEL}_R1_n{n_mid}.csv"
        if r1_path.exists():
            df_r1x = pd.read_csv(r1_path)
            for year in years:
                code_col = "FinalElecCode" + str(year)
                inv_col  = "InvestmentCost" + str(year)
                if code_col not in df_r1x.columns:
                    continue
                for code in [1, 3, 5, 6, 7, 99]:
                    mask = df_r1x[code_col] == code
                    rows.append({"year": year, "arm": "R1", "n_mid": n_mid,
                                 "tech_code": code,
                                 "n_settlements": int(mask.sum()),
                                 "population": float(df_r1x.loc[mask, "Pop"].sum()),
                                 "investment_usd": float(df_r1x.loc[mask, inv_col].sum()) if inv_col in df_r1x.columns else np.nan})

    split_path = OUTDIR / f"{RUN_LABEL}_tech_split.csv"
    pd.DataFrame(rows).to_csv(split_path, index=False)
    print(f"\n  Tech-split CSV → {split_path.name}")


if __name__ == "__main__":
    main()
