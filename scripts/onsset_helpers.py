"""
onsset_helpers.py — shared loaders (solar and wind profiles, config) for stages 06 onward.

Both R0 and R1 arms share ONE in-memory spine loaded from the R0 CSV; PE_ratio (and any
other R1-only columns) are merged from the R1 CSV by settlement id. Only
AverageToPeakLoadRatio and PE columns differ between arms, which
`assert_base_cols_match()` in s06_run_arms.py verifies before each arm runs.

Technologies available:
    1 = Grid extension              (enabled)
    3 = SA_PV stand-alone           (enabled)
    5 = MG_PVHybrid                 (ENABLED — PV+battery+diesel lookup)
    6 = MG_Wind                     (attempted — see WIND_HYBRID_STATUS below)
    7 = MG_Hydro mini-grid          (enabled)
    2 = SA_Diesel                   (enabled, reference cost only)

WIND_HYBRID_STATUS: The wind-hybrid optimization in hybrids_wind.py contains a
suspected bug in year_simulation_wind (net_load = net_load[0] with hour_numbers
cycling 0–23), which causes the numba JIT function to fail when net_load is a
1D array. Wind-hybrid LCOE computation is wrapped in try/except; if it errors,
MG_Wind falls back to LCOE=99 and this is reported explicitly.

Profile source: renewables.ninja, Lusaka (−15.42, 28.28), year 2025, MERRA-2.
    Solar cite: Pfenninger & Staffell 2016 doi:10.1016/j.energy.2016.08.060
    Wind cite:  Staffell & Pfenninger 2016 doi:10.1016/j.energy.2016.08.068

"""

import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

sys.path.insert(0, str(REPO / "data" / "onsset_repo"))

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

# ── paths ─────────────────────────────────────────────────────────────────────
CONFIG     = REPO / "config" / "config.yaml"
OUTDIR     = REPO / "data" / "onsset_outputs"
TX_SHP     = (REPO / "data" / "raw" / "zambia" / "grid" /
              "transmission_network_wb" / "zambia-electricity-transmission-network" /
              "Zambia Electricity Transmission Network.shp")

SOLAR_PROFILE = (REPO / "data" / "raw" / "zambia" / "renewables_hourly" /
                 "solar" / "solar_lusaka.csv")
WIND_PROFILE  = (REPO / "data" / "raw" / "zambia" / "renewables_hourly" /
                 "wind" / "wind_lusaka.csv")


# ── scenario constants (from runner.py defaults) ───────────────────────────────
HV_LINE_TYPE        = 69
HV_LINE_COST        = 53000
HV_MV_SUB_COST      = 25000
HV_MV_SUB_TYPE      = 10000
MV_LINE_TYPE        = 33
MV_LINE_AMPERAGE    = 275
MV_LINE_COST        = 25000
LV_LINE_TYPE        = 0.24
LV_LINE_COST        = 15000
LV_LINE_MAX_LEN     = 1
SERV_TRANSF_TYPE    = 75
SERV_TRANSF_COST    = 9000
MAX_NODES_PER_TRANS = 95
CONN_COST_PER_HH    = 125
TIERS               = {1: 38.7, 2: 219, 3: 803, 4: 2117, 5: 3000}


# ── Profile loading ────────────────────────────────────────────────────────────

def load_solar_profile(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """
    Parse a renewables.ninja solar CSV (3 comment lines + header).
    Returns (ghi_W_m2, temp_C) as 1D float64 arrays of length 8760.
    GHI = (irradiance_direct + irradiance_diffuse) × 1000  [W/m²].
    """
    df = pd.read_csv(str(path), skiprows=3)
    ghi  = ((df["irradiance_direct"] + df["irradiance_diffuse"]) * 1000.0).values.astype(np.float64)
    temp = df["temperature"].values.astype(np.float64)
    assert len(ghi) == 8760, f"Expected 8760 rows, got {len(ghi)} in {path.name}"
    return ghi, temp


def load_wind_profile(path: Path,
                      hub_from: float = 80.0,
                      hub_to: float   = 20.0,
                      shear: float    = 0.143) -> np.ndarray:
    """
    Parse a renewables.ninja wind CSV (3 comment lines + header).
    Returns wind_speed in m/s as a 1D float64 array of length 8760.

    Hub-height correction (Hellmann power law):
        v(hub_to) = v(hub_from) × (hub_to / hub_from) ^ shear
    Factor: (20/80)^0.143 = 0.820  (open terrain, standard shear exponent).

    NOTE: the OnSSET wind lookup table normalises each profile by its mean and
    re-scales to the settlement's SET_WINDVEL.  A constant height correction
    cancels out in that normalisation (it doesn't change the hourly shape).
    It is applied here for physical correctness; the effect on results is nil.
    """
    df = pd.read_csv(str(path), skiprows=3)
    wind = df["wind_speed"].values.astype(np.float64)
    assert len(wind) == 8760, f"Expected 8760 rows, got {len(wind)} in {path.name}"
    correction = (hub_to / hub_from) ** shear
    return wind * correction


# ── Lookup-table builders ──────────────────────────────────────────────────────

def build_pv_hybrid_lookup(onsseter, ghi_profile, temp_profile,
                           year, time_step, end_year,
                           mg_pv_hybrid_params, start_yr_t):
    """
    Replicate pv_hybrids_lcoe_lookuptable() logic from onsset.py, reading
    profiles ourselves instead of relying on read_environmental_data()
    (whose default skiprows=341882 is incompatible with our 8760-row files).

    F5 FIX (2026-06-23): GHI bins now cover the full realised data range.
    Previous code used round(min/max, -2) = [1800, 2100] for Zambia data
    (min 1778, max 2133), meaning 8,553 settlements with GHI > 2100 were
    priced at the top-bin clamp.  Now uses floor/ceil to nearest 100 so no
    settlement's rounded GHI falls outside the bin range.

    Returns four dicts keyed by (tier, ghi_bin, diesel_bin):
        lcoe_lut, inv_lut, cap_lut, fuel_lut
    """
    # F5: floor/ceil so actual min and max are strictly within the bin range
    _ghi_raw_min = float(onsseter.df[SET_GHI].min())
    _ghi_raw_max = float(onsseter.df[SET_GHI].max())
    ghi_min   = int(np.floor(_ghi_raw_min / 100)) * 100   # e.g. 1700 for min=1778
    ghi_max   = int(np.ceil(_ghi_raw_max  / 100)) * 100   # e.g. 2200 for max=2133

    d_col     = SET_MG_DIESEL_FUEL + str(year)
    diesel_min = round(float(onsseter.df[d_col].min()), 1)
    diesel_max = round(float(onsseter.df[d_col].max()), 1)

    ghi_range    = np.round(np.arange(ghi_min, ghi_max + 100, 100), -2)
    diesel_range = np.round(np.arange(diesel_min, diesel_max + 0.1, 0.1), 1)
    tiers        = [1, 2, 3, 4, 5]

    # F5 validation: verify no settlement GHI is outside the table range
    _rounded_ghi = np.round(onsseter.df[SET_GHI].values, -2).astype(int)
    _out_of_range = ((_rounded_ghi < ghi_min) | (_rounded_ghi > ghi_max)).sum()
    if _out_of_range > 0:
        print(f"    F5 WARNING: {_out_of_range} settlements have rounded GHI outside "
              f"[{ghi_min}, {ghi_max}] — they will be clamped.")
    else:
        print(f"    F5 OK: all settlement GHIs are within bin range "
              f"[{ghi_min}, {ghi_max}] (data range: [{_ghi_raw_min:.0f}, {_ghi_raw_max:.0f}])")

    n_entries = len(tiers) * len(ghi_range) * len(diesel_range)
    print(f"    PV-hybrid lookup: {len(tiers)} tiers × {len(ghi_range)} GHI bins "
          f"× {len(diesel_range)} diesel bins = {n_entries} optimisations")

    profile_sum = ghi_profile.sum()  # annual sum in Wh/m²/year

    lcoe_lut = {}
    inv_lut  = {}
    cap_lut  = {}
    fuel_lut = {}

    done = 0
    t0 = time.time()
    for t in tiers:
        for g in ghi_range:
            for d in diesel_range:
                # Scale profile so annual sum = g × 1000 Wh/m²/year
                scaled_ghi = ghi_profile * g * 1000.0 / profile_sum
                try:
                    gen_lcoe, inv, cap, fuel = SettlementProcessor.optimize_mini_grid(
                        scaled_ghi, temp_profile,
                        10000,          # reference annual demand kWh
                        t, d,
                        start_yr_t, end_year,
                        year, time_step,
                        mg_pv_hybrid_params,
                    )
                except Exception as exc:
                    print(f"      WARN optimize_mini_grid t={t} g={g} d={d}: {exc}")
                    gen_lcoe, inv, cap, fuel = 99.0, 0.0, 0.0, 0.0

                lcoe_lut[t, g, d] = gen_lcoe
                inv_lut [t, g, d] = inv
                cap_lut [t, g, d] = cap
                fuel_lut[t, g, d] = fuel
                done += 1

        elapsed = time.time() - t0
        print(f"      tier {t} done  ({done}/{n_entries}, {elapsed:.0f}s elapsed)")

    return lcoe_lut, inv_lut, cap_lut, fuel_lut, ghi_min, ghi_max, diesel_min, diesel_max


def apply_pv_hybrid_lookup(onsseter, lcoe_lut, inv_lut, cap_lut,
                           year, time_step,
                           mg_pv_hybrid_params,
                           ghi_min, ghi_max, diesel_min, diesel_max):
    """
    Apply the PV-hybrid lookup table per settlement.
    Returns (hybrid_lcoe, hybrid_investment, hybrid_capacity) as pd.Series.
    """
    d_col  = SET_MG_DIESEL_FUEL + str(year)
    e_col  = SET_ENERGY_PER_CELL + str(year)
    p_col  = SET_POP + str(year)
    fc_col = SET_ELEC_FINAL_CODE + str(year - time_step)

    # NOTE (2026-08-16): a units mismatch, left in place deliberately. This test is on
    # POPULATION (p_col), whereas onsset.py's calculate_off_grid_lcoes gates the same
    # technology on HOUSEHOLDS (Pop / NumPeoplePerHH) against the same constant. With
    # min_mg_size = 100 the household test is ~5x stricter and always binds afterwards, so
    # this condition has no effect on any reported result. It is documented rather than
    # changed because altering it cannot improve the outputs and could perturb them.
    potential_mg = np.where(
        ((onsseter.df[p_col] > mg_pv_hybrid_params["min_mg_connections"])
         & (onsseter.df[fc_col] != 1)
         & (onsseter.df[fc_col] != 10))
        | (onsseter.df[fc_col] == 5),
        1, 0,
    )
    onsseter.df["_PotentialMG_pv"] = potential_mg

    def _lookup(row):
        if row["_PotentialMG_pv"] != 1:
            return 99.0, 0.0, 0.0
        ghi_key    = max(ghi_min,    min(ghi_max,    round(row[SET_GHI], -2)))
        diesel_key = max(diesel_min, min(diesel_max, round(row[d_col],    1)))
        tier       = int(row[SET_TIER])
        energy     = float(row[e_col])
        scale      = energy / 10000.0
        lcoe = lcoe_lut.get((tier, ghi_key, diesel_key), 99.0)
        inv  = inv_lut .get((tier, ghi_key, diesel_key), 0.0) * scale
        cap  = cap_lut .get((tier, ghi_key, diesel_key), 0.0) * scale
        return lcoe, inv, cap

    result = onsseter.df.apply(_lookup, axis=1, result_type="expand")
    del onsseter.df["_PotentialMG_pv"]

    hybrid_lcoe       = pd.Series(result[0].values, index=onsseter.df.index)
    hybrid_investment = pd.Series(result[1].values, index=onsseter.df.index)
    hybrid_capacity   = pd.Series(result[2].values, index=onsseter.df.index)
    return hybrid_lcoe, hybrid_investment, hybrid_capacity


def build_wind_hybrid_lookup(onsseter, wind_profile,
                             year, time_step, end_year,
                             mg_wind_hybrid_params, start_yr_t):
    """
    Replicate wind_hybrids_lcoe_lookuptable() logic.
    Returns four dicts keyed by (tier, wind_bin, diesel_bin), or None if the
    optimization fails (known bug in year_simulation_wind in hybrids_wind.py).
    """
    wind_min  = int(round(float(onsseter.df[SET_WINDVEL].min())))
    wind_max  = int(round(float(onsseter.df[SET_WINDVEL].max())))
    d_col     = SET_MG_DIESEL_FUEL + str(year)
    diesel_min = round(float(onsseter.df[d_col].min()), 1)
    diesel_max = round(float(onsseter.df[d_col].max()), 1)

    wind_range   = np.round(np.arange(wind_min, wind_max + 1))
    diesel_range = np.round(np.arange(diesel_min, diesel_max + 0.1, 0.1), 1)
    tiers        = [1, 2, 3, 4, 5]

    n_entries = len(tiers) * len(wind_range) * len(diesel_range)
    print(f"    Wind-hybrid lookup: {len(tiers)} tiers × {len(wind_range)} wind bins "
          f"× {len(diesel_range)} diesel bins = {n_entries} optimisations")

    wind_mean = float(np.average(wind_profile))

    lcoe_lut = {}
    inv_lut  = {}
    cap_lut  = {}
    fuel_lut = {}

    failed_count = 0
    done = 0
    t0 = time.time()
    for t in tiers:
        for g in wind_range:
            for d in diesel_range:
                scaled_wind = wind_profile * g / wind_mean
                try:
                    gen_lcoe, inv, cap, fuel = onsseter.optimize_wind_mini_grid(
                        scaled_wind, 10000, t, d,
                        start_yr_t, end_year, year, time_step,
                        mg_wind_hybrid_params,
                    )
                except Exception as exc:
                    failed_count += 1
                    gen_lcoe, inv, cap, fuel = 99.0, 0.0, 0.0, 0.0
                    if failed_count == 1:
                        print(f"      WIND-HYBRID ERROR (first of potentially many): {exc}")
                        print("      Wind-hybrid optimization failing — will default to LCOE=99.")

                lcoe_lut[t, g, d] = gen_lcoe
                inv_lut [t, g, d] = inv
                cap_lut [t, g, d] = cap
                fuel_lut[t, g, d] = fuel
                done += 1

        elapsed = time.time() - t0
        print(f"      tier {t} done  ({done}/{n_entries}, {elapsed:.0f}s, failures={failed_count})")

    wind_ok = (failed_count == 0)
    print(f"    Wind-hybrid lookup complete. Failures: {failed_count}/{n_entries}. "
          f"{'OK' if wind_ok else 'ALL FELL BACK TO LCOE=99 — wind hybrid disabled.'}")
    return lcoe_lut, inv_lut, cap_lut, fuel_lut, wind_min, wind_max, diesel_min, diesel_max, wind_ok


def apply_wind_hybrid_lookup(onsseter, lcoe_lut, inv_lut, cap_lut,
                             year, time_step, mg_wind_hybrid_params,
                             wind_min, wind_max, diesel_min, diesel_max):
    """Apply wind-hybrid lookup per settlement; returns (lcoe, investment, capacity)."""
    d_col  = SET_MG_DIESEL_FUEL + str(year)
    e_col  = SET_ENERGY_PER_CELL + str(year)
    p_col  = SET_POP + str(year)
    fc_col = SET_ELEC_FINAL_CODE + str(year - time_step)

    # NOTE (2026-08-16): same population-vs-household units mismatch as the PV-hybrid path
    # above; the household gate in onsset.py binds first, so this has no effect on results.
    potential_mg = np.where(
        ((onsseter.df[p_col] > mg_wind_hybrid_params["min_mg_connections"])
         & (onsseter.df[fc_col] != 1)
         & (onsseter.df[fc_col] != 2))
        | (onsseter.df[fc_col] == 6),
        1, 0,
    )
    onsseter.df["_PotentialMG_wind"] = potential_mg

    def _lookup(row):
        if row["_PotentialMG_wind"] != 1:
            return 99.0, 0.0, 0.0
        w_key      = max(wind_min,   min(wind_max,   int(round(float(row[SET_WINDVEL])))))
        diesel_key = max(diesel_min, min(diesel_max, round(row[d_col], 1)))
        tier       = int(row[SET_TIER])
        energy     = float(row[e_col])
        scale      = energy / 10000.0
        lcoe = lcoe_lut.get((tier, w_key, diesel_key), 99.0)
        inv  = inv_lut .get((tier, w_key, diesel_key), 0.0) * scale
        cap  = cap_lut .get((tier, w_key, diesel_key), 0.0) * scale
        return lcoe, inv, cap

    result = onsseter.df.apply(_lookup, axis=1, result_type="expand")
    del onsseter.df["_PotentialMG_wind"]

    hybrid_lcoe       = pd.Series(result[0].values, index=onsseter.df.index)
    hybrid_investment = pd.Series(result[1].values, index=onsseter.df.index)
    hybrid_capacity   = pd.Series(result[2].values, index=onsseter.df.index)
    return hybrid_lcoe, hybrid_investment, hybrid_capacity


# ── Off-grid minimum recomputation ────────────────────────────────────────────

def compute_offgrid_min(onsseter, year, off_grid_techs):
    """
    Compute SET_MIN_OFFGRID_LCOE and SET_MIN_OFFGRID from all off-grid technologies
    including hybrids (no override to 99).
    """
    cols = [c + str(year) for c in off_grid_techs]
    available = [c for c in cols if c in onsseter.df.columns]
    onsseter.df[SET_MIN_OFFGRID_LCOE + str(year)] = onsseter.df[available].min(axis=1)
    onsseter.df[SET_MIN_OFFGRID + str(year)]      = onsseter.df[available].T.idxmin()


# ── Per-connection cost reporting (F4 guard) ───────────────────────────────────

def per_connection_stats(df, year, tech_code, tech_name):
    """
    Compute robust per-connection investment cost: median of the realised
    InvestmentCost/NewConnections distribution, excluding inf and NaN.
    (F4: 8,276 SA_PV settlements have ~0 capacity/investment but correct
    technology assignment; their InvestmentPerConnection = inf/0 corrupts any
    mean.  Median with inf excluded is robust.)
    """
    code_col = "FinalElecCode" + str(year)
    inv_col  = "InvestmentCost" + str(year)
    con_col  = "NewConnections" + str(year)
    mask = (df[code_col] == tech_code) & (df[con_col] > 0)
    if mask.sum() == 0:
        return np.nan, 0
    ratio = df.loc[mask, inv_col] / df.loc[mask, con_col]
    # Exclude inf, -inf, NaN and the near-zero capacity artefacts (inv < $1)
    finite = ratio.replace([np.inf, -np.inf], np.nan).dropna()
    finite = finite[finite > 1.0]  # exclude the ~0 investment artefacts (F4)
    median = finite.median()
    n = len(finite)
    return median, n


# ── Technology objects ─────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG) as f:
        return yaml.safe_load(f)


def build_tech_objects(cfg: dict, start_year: int, end_year: int) -> dict:
    dr_grid = float(cfg["discount_rates"]["grid"])
    dr_mg   = float(cfg["discount_rates"]["mini_grid"])
    dr_sa   = float(cfg["discount_rates"]["standalone"])
    losses  = float(cfg["grid"]["losses"])
    grid_gi = float(cfg["grid"]["capacity_investment_cost_usd_kw"])

    Technology.set_default_values(
        base_year=start_year, start_year=start_year, end_year=end_year,
        hv_line_type=HV_LINE_TYPE, hv_line_cost=HV_LINE_COST,
        hv_mv_sub_station_cost=HV_MV_SUB_COST, hv_mv_substation_type=HV_MV_SUB_TYPE,
    )

    # NOTE (V2 / Step 7): The OPERATIVE AverageToPeakLoadRatio for both arms is
    # set by OnSSET's tier table in calculate_demand() (onsset.py:2015-2020):
    #   Tier 1→0.3, Tier 2→0.4, Tier 3/4/5→0.5.
    # For Zambia (all rural Tier 3 / urban Tier 5) this means every settlement
    # gets 0.5 in R0 (peak = 2× avg), then the R1 arm overrides per-settlement
    # with 1/PE_ratio.  The two scalar values below are therefore INERT — they
    # are overridden by the column before any LCOE function reads it:
    #   grid.base_to_peak_r0 = 0.8 in config.yaml (INERT — overridden by tier table)
    #   sa_pv base_to_peak_load_ratio = 0.9 below  (INERT — overridden by tier table)
    # The 0.5 vs 0.8 discrepancy is a load-factor convention note; the per-settlement column overrides both.

    grid_calc = Technology(
        om_of_td_lines=0.02, distribution_losses=losses,
        connection_cost_per_hh=CONN_COST_PER_HH,
        base_to_peak_load_ratio=float(cfg["grid"]["base_to_peak_r0"]),  # INERT — tier table overrides
        capacity_factor=1, tech_life=30,
        grid_capacity_investment=grid_gi,
        grid_penalty_ratio=1,
        grid_price=float(cfg["grid"]["generation_cost_usd_kwh"]),
        discount_rate=dr_grid,
        mv_line_type=MV_LINE_TYPE, mv_line_amperage_limit=MV_LINE_AMPERAGE,
        mv_line_cost=MV_LINE_COST, lv_line_type=LV_LINE_TYPE,
        lv_line_cost=LV_LINE_COST, lv_line_max_length=LV_LINE_MAX_LEN,
        service_transf_type=SERV_TRANSF_TYPE, service_transf_cost=SERV_TRANSF_COST,
        max_nodes_per_serv_trans=MAX_NODES_PER_TRANS, cnse=0,
    )

    mg_hydro_calc = Technology(
        om_of_td_lines=0.02, distribution_losses=0.05,
        connection_cost_per_hh=100, base_to_peak_load_ratio=0.85,
        capacity_factor=0.5, tech_life=30,
        capital_cost={float("inf"): 3000}, om_costs=0.03,
        discount_rate=dr_mg, mv_line_type=MV_LINE_TYPE,
        mv_line_amperage_limit=MV_LINE_AMPERAGE, mv_line_cost=MV_LINE_COST,
        lv_line_type=LV_LINE_TYPE, lv_line_cost=LV_LINE_COST,
        lv_line_max_length=LV_LINE_MAX_LEN, service_transf_type=SERV_TRANSF_TYPE,
        service_transf_cost=SERV_TRANSF_COST,
        max_nodes_per_serv_trans=MAX_NODES_PER_TRANS, mini_grid=True,
    )

    sa_pv_calc = Technology(
        base_to_peak_load_ratio=0.9,  # INERT — overridden by tier table (operative value = 0.5)
        tech_life=5, om_costs=0.02,
        capital_cost={float("inf"): 6950, 1: 4470, 0.100: 6380,
                      0.050: 8780, 0.020: 9620},
        standalone=True, discount_rate=dr_sa,
    )

    mg_pv_hybrid_calc = Technology(
        om_of_td_lines=0.02, distribution_losses=0.05,
        connection_cost_per_hh=100, capacity_factor=0.5, tech_life=20,
        discount_rate=dr_mg, mv_line_type=MV_LINE_TYPE,
        mv_line_amperage_limit=MV_LINE_AMPERAGE, mv_line_cost=MV_LINE_COST,
        lv_line_type=LV_LINE_TYPE, lv_line_cost=LV_LINE_COST,
        lv_line_max_length=LV_LINE_MAX_LEN, service_transf_type=SERV_TRANSF_TYPE,
        service_transf_cost=SERV_TRANSF_COST,
        max_nodes_per_serv_trans=MAX_NODES_PER_TRANS, mini_grid=True, hybrid=True,
    )

    mg_wind_hybrid_calc = Technology(
        om_of_td_lines=0.02, distribution_losses=0.05,
        connection_cost_per_hh=100, capacity_factor=0.5, tech_life=20,
        discount_rate=dr_mg, mv_line_type=MV_LINE_TYPE,
        mv_line_amperage_limit=MV_LINE_AMPERAGE, mv_line_cost=MV_LINE_COST,
        lv_line_type=LV_LINE_TYPE, lv_line_cost=LV_LINE_COST,
        lv_line_max_length=LV_LINE_MAX_LEN, service_transf_type=SERV_TRANSF_TYPE,
        service_transf_cost=SERV_TRANSF_COST,
        max_nodes_per_serv_trans=MAX_NODES_PER_TRANS, mini_grid=True, hybrid=True,
    )

    sa_diesel_calc = Technology(
        base_to_peak_load_ratio=0.85, capacity_factor=0.5, tech_life=10,
        om_costs=0.1, capital_cost={float("inf"): 928}, efficiency=0.28,
        discount_rate=dr_grid, standalone=True,
    )

    return {
        "grid": grid_calc, "mg_hydro": mg_hydro_calc, "sa_pv": sa_pv_calc,
        "mg_pv_hybrid": mg_pv_hybrid_calc, "mg_wind_hybrid": mg_wind_hybrid_calc,
        "sa_diesel": sa_diesel_calc,
    }


# ── Hybrid parameter dicts ─────────────────────────────────────────────────────

def build_mg_pv_hybrid_params(cfg: dict, min_mg_size: int) -> dict:
    dr_mg = float(cfg["discount_rates"]["mini_grid"])
    return {
        "min_mg_connections": min_mg_size,
        "diesel_cost":        500,
        "discount_rate":      dr_mg,
        "n_chg":              0.92,
        "n_dis":              0.92,
        "battery_cost":       float(cfg.get("battery_capex_usd_per_kwh", 300)),
        "pv_cost":            1400,
        "charge_controller":  0,
        "pv_inverter":        0,
        "pv_life":            25,
        "diesel_life":        10,
        "pv_om":              0.015,
        "diesel_om":          0.1,
        "battery_inverter_cost":  150,
        "battery_inverter_life":  10,
        "dod_max":            0.8,
        "inv_eff":            0.93,
        "lpsp_max":           0.02,
        "diesel_limit":       0.5,
        "full_life_cycles":   4000,
    }


def build_mg_wind_hybrid_params(cfg: dict, min_mg_size: int) -> dict:
    dr_mg = float(cfg["discount_rates"]["mini_grid"])
    return {
        "min_mg_connections": min_mg_size,
        "diesel_cost":        500,
        "discount_rate":      dr_mg,
        "n_chg":              0.92,
        "n_dis":              0.92,
        "battery_cost":       float(cfg.get("battery_capex_usd_per_kwh", 300)),
        "wind_cost":          1400,
        "charge_controller":  0,
        "wind_life":          25,
        "diesel_life":        10,
        "wind_om":            0.015,
        "diesel_om":          0.1,
        "battery_inverter_cost":  150,
        "battery_inverter_life":  10,
        "dod_max":            0.8,
        "inv_eff":            0.93,
        "lpsp_max":           0.02,
        "diesel_limit":       0.7,
        "full_life_cycles":   4000,
    }


# ── Main arm runner ────────────────────────────────────────────────────────────

def run_arm(arm: str, spine_path: Path, cfg: dict,
            x_tx: np.ndarray, y_tx: np.ndarray,
            ghi_profile: np.ndarray, temp_profile: np.ndarray,
            wind_profile: np.ndarray,
            spine_df: pd.DataFrame = None) -> tuple[SettlementProcessor, dict, dict]:
    """
    Run full LCOE pipeline for one arm.  Returns (processor, summary, hybrid_status).
    hybrid_status: dict with keys 'pv_ok', 'wind_ok'.

    F1 parameter: spine_df — if provided, this pre-loaded DataFrame is used
    instead of reading the CSV from spine_path.  Both R0 and R1 arms are built
    from the same R0 spine (loaded once in main()), so physical input columns
    are guaranteed identical.  Only PE_ratio and AverageToPeakLoadRatio differ.
    """
    print(f"\n{'='*65}")
    print(f"  ARM {arm} — spine: {spine_path.name}"
          + (" [from in-memory DataFrame — F1]" if spine_df is not None else ""))
    print(f"{'='*65}")

    hh_u          = float(cfg["household_size"]["urban"])
    hh_r          = float(cfg["household_size"]["rural"])
    urban_tier    = int(cfg["demand_tiers"]["urban_tier"])
    rural_tier_l  = int(cfg["demand_tiers"]["rural_tier_large"])
    rural_tier_s  = int(cfg["demand_tiers"]["rural_tier_small"])
    rural_cutoff  = int(cfg["demand_tiers"]["rural_cutoff_size"])
    losses        = float(cfg["grid"]["losses"])
    grid_price    = float(cfg["grid"]["generation_cost_usd_kwh"])
    diesel_price  = float(cfg["diesel_price_usd_per_l"])
    max_grid_ext  = float(cfg["grid"]["max_extension_dist_km"])
    start_year    = int(cfg["scenario"]["start_year"])
    end_year      = int(cfg["scenario"]["end_year"])
    years         = cfg["scenario"]["years_of_analysis"]
    pop_future    = float(cfg["scenario"]["pop_end_year"])
    urb_future    = float(cfg["scenario"]["urban_ratio_end_year"])
    elec_target   = float(cfg["scenario"]["elec_target"])

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

    # F1: use in-memory DataFrame if provided, otherwise load from CSV
    if spine_df is not None:
        onsseter = SettlementProcessor.__new__(SettlementProcessor)
        onsseter.df = spine_df.copy()
    else:
        onsseter = SettlementProcessor(str(spine_path))

    onsseter.condition_df()
    onsseter.df[SET_GRID_PENALTY] = 1
    onsseter.df[SET_WINDCF] = onsseter.calc_wind_cfs(onsseter.df[SET_WINDVEL])
    onsseter.add_xy_3395()

    onsseter.df["PerHouseholdDemand"]    = 0
    onsseter.df["ElectrificationOrder"]  = onsseter.df.get("ElectrificationOrder", 0)

    onsseter.df[SET_MV_DIST_PLANNED] = onsseter.df[SET_MV_DIST_CURRENT]
    onsseter.df[SET_HV_DIST_PLANNED] = onsseter.df[SET_HV_DIST_CURRENT]

    onsseter.project_pop_and_urban(pop_future, urb_future, start_year, years)
    onsseter.current_mv_line_dist()
    onsseter.prepare_wtf_tier_columns(*[TIERS[i] for i in range(1, 6)])

    x_coords = x_tx.copy()
    y_coords = y_tx.copy()
    new_lines_geojson = {}
    summary      = {"arm": arm}
    hybrid_status = {"pv_ok": None, "wind_ok": None}

    for i, year in enumerate(years):
        time_step  = year - (years[i - 1] if i > 0 else start_year)
        start_yr_t = year - time_step
        print(f"\n  ── Year {year} (time_step={time_step}) ──")

        techs_obj        = build_tech_objects(cfg, start_yr_t, end_year)
        grid_calc        = techs_obj["grid"]
        mg_hydro_calc    = techs_obj["mg_hydro"]
        sa_pv_calc       = techs_obj["sa_pv"]
        mg_pv_hybrid_calc= techs_obj["mg_pv_hybrid"]
        mg_wind_calc     = techs_obj["mg_wind_hybrid"]
        sa_diesel_calc   = techs_obj["sa_diesel"]

        grid_cap_gen_limit = 9999 * 1000 * time_step
        grid_connect_limit = 9999 * 1000 * time_step

        # ── Demand ────────────────────────────────────────────────────────
        onsseter.calculate_demand(year, hh_r, hh_u, time_step,
                                  urban_tier, rural_tier_l, rural_tier_s,
                                  rural_cutoff, TIERS)

        if arm == "R1" and "PE_ratio" in onsseter.df.columns:
            pe = onsseter.df["PE_ratio"].clip(lower=0.1)
            onsseter.df[SET_AVERAGE_TO_PEAK] = (1.0 / pe).clip(upper=1.0)
            # GUARD (2026-08-16): must follow calculate_demand, which resets this column
            # to the tier table. See the identical guard in s06_run_arms.py.
            assert onsseter.df[SET_AVERAGE_TO_PEAK].nunique() > 100, (
                "R1 arm but AverageToPeakLoadRatio is (near-)uniform - override ran "
                "before calculate_demand overwrote it, or not at all.")
            print(f"    R1 AverageToPeakLoadRatio: mean={onsseter.df[SET_AVERAGE_TO_PEAK].mean():.4f}")

        onsseter.calculate_unmet_demand(year, reliability=0.963)
        onsseter.diesel_cost_columns(sa_diesel_cost, mg_diesel_cost, year)

        # ── Build PV-hybrid lookup and set Technology attributes ──────────
        print(f"    Building PV-hybrid LCOE lookup table …")
        t_lut_start = time.time()
        (lcoe_pv_lut, inv_pv_lut, cap_pv_lut, _,
         ghi_min, ghi_max, diesel_min, diesel_max) = build_pv_hybrid_lookup(
            onsseter, ghi_profile, temp_profile,
            year, time_step, end_year, mg_pv_hybrid_params, start_yr_t,
        )
        pv_lut_time = time.time() - t_lut_start
        print(f"    PV-hybrid lookup done in {pv_lut_time:.0f}s")

        hybrid_lcoe_pv, hybrid_inv_pv, hybrid_cap_pv = apply_pv_hybrid_lookup(
            onsseter, lcoe_pv_lut, inv_pv_lut, cap_pv_lut,
            year, time_step, mg_pv_hybrid_params,
            ghi_min, ghi_max, diesel_min, diesel_max,
        )
        mg_pv_hybrid_calc.hybrid_fuel       = hybrid_lcoe_pv
        mg_pv_hybrid_calc.hybrid_investment  = hybrid_inv_pv
        mg_pv_hybrid_calc.hybrid_capacity    = hybrid_cap_pv
        hybrid_status["pv_ok"] = True
        print(f"    PV-hybrid LCOE applied. Valid (< 99) settlements: "
              f"{(hybrid_lcoe_pv < 98).sum():,}")

        # ── Build wind-hybrid lookup and set Technology attributes ─────────
        print(f"    Building wind-hybrid LCOE lookup table …")
        t_wlut_start = time.time()
        (lcoe_w_lut, inv_w_lut, cap_w_lut, _,
         wind_min, wind_max, w_diesel_min, w_diesel_max, wind_ok) = build_wind_hybrid_lookup(
            onsseter, wind_profile,
            year, time_step, end_year, mg_wind_hybrid_params, start_yr_t,
        )
        w_lut_time = time.time() - t_wlut_start
        hybrid_status["wind_ok"] = wind_ok
        print(f"    Wind-hybrid lookup done in {w_lut_time:.0f}s  (wind_ok={wind_ok})")

        if wind_ok:
            hybrid_lcoe_w, hybrid_inv_w, hybrid_cap_w = apply_wind_hybrid_lookup(
                onsseter, lcoe_w_lut, inv_w_lut, cap_w_lut,
                year, time_step, mg_wind_hybrid_params,
                wind_min, wind_max, w_diesel_min, w_diesel_max,
            )
            mg_wind_calc.hybrid_fuel       = hybrid_lcoe_w
            mg_wind_calc.hybrid_investment  = hybrid_inv_w
            mg_wind_calc.hybrid_capacity    = hybrid_cap_w
            print(f"    Wind-hybrid LCOE applied. Valid (< 99) settlements: "
                  f"{(hybrid_lcoe_w < 98).sum():,}")
        else:
            n = len(onsseter.df)
            mg_wind_calc.hybrid_fuel       = pd.Series(np.full(n, 99.0))
            mg_wind_calc.hybrid_investment = pd.Series(np.zeros(n))
            mg_wind_calc.hybrid_capacity   = pd.Series(np.zeros(n))
            print("    Wind-hybrid DISABLED (optimization failed) — LCOE = 99")

        # ── Off-grid LCOEs ────────────────────────────────────────────────
        (sa_pv_inv, sa_pv_cap, mg_pv_h_inv, mg_pv_h_cap,
         mg_wind_inv, mg_wind_cap, mg_hydro_inv, mg_hydro_cap) = \
            onsseter.calculate_off_grid_lcoes(
                mg_hydro_calc, mg_wind_calc, sa_pv_calc, mg_pv_hybrid_calc,
                year, end_year, time_step, techs, tech_codes, min_mg_size, 0,
            )

        # ── Recompute off-grid minimum INCLUDING hybrids ───────────────────
        compute_offgrid_min(onsseter, year, all_off_grid)

        # ── Grid pre-electrification ──────────────────────────────────────
        grid_inv, grid_cap, grid_cap_gen_limit, grid_conn_limit = \
            onsseter.pre_electrification(
                grid_price, year, time_step, end_year, grid_calc, sa_diesel_calc,
                "None", grid_cap_gen_limit, grid_connect_limit,
            )

        # ── Max extension distance ────────────────────────────────────────
        onsseter.max_extension_dist(
            year, time_step, end_year, start_yr_t, grid_calc, sa_diesel_calc,
            "None", 0, 0,
        )

        # ── Pre-selection ─────────────────────────────────────────────────
        onsseter.pre_selection(elec_target, year, time_step, 2, 5)

        # ── Grid extension (numba) ────────────────────────────────────────
        (onsseter.df["Grid" + str(year)],
         onsseter.df["MinGridDist" + str(year)],
         grid_inv, grid_cap, x_coords, y_coords,
         new_lines_geojson[year]) = \
            onsseter.elec_extension_numba(
                grid_calc, sa_diesel_calc, "None",
                max_grid_ext, year, end_year, time_step,
                grid_cap_gen_limit, grid_conn_limit,
                x_coords, y_coords, mg_interconnection=False,
            )

        # ── Technology choice ─────────────────────────────────────────────
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

        # ── Year summary ──────────────────────────────────────────────────
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
            print(f"    {'Code':<6} {'Label':<22} {'Settlements':>12} {'Population':>14}")
            print(f"    {'-'*56}")
            for code, row in tech_split.iterrows():
                lbl = tech_labels.get(int(code), str(code))
                pop_val = row.get("population", 0)
                n_val   = row.get("n_settlements", 0)
                print(f"    {int(code):<6} {lbl:<22} {int(n_val):>12,} {pop_val:>14,.0f}")

            # F4: per-connection cost (robust: median, inf excluded)
            print(f"\n    Per-connection investment cost (median, inf excluded — F4 guard):")
            for tc, tl in [(1, "Grid"), (3, "SA_PV"), (5, "MG_PVHybrid"), (7, "MG_Hydro")]:
                med, n = per_connection_stats(onsseter.df, year, tc, tl)
                if not np.isnan(med):
                    print(f"      {tl:<18} median ${med:>10,.0f}/connection  (n={n:,})")

    return onsseter, summary, hybrid_status


# ── Comparison ────────────────────────────────────────────────────────────────

# Physical input columns that must be identical between R0 and R1 outputs
# (everything except PE columns and the AverageToPeakLoadRatio override).
_PHYSICAL_INPUT_COLS = [
    "Pop", "GridCellArea", "ElecPop", "WindVel", "GHI", "TravelHours",
    "Elevation", "Slope", "NightLights", "Pop2020", "Pop2030", "Pop2035",
    "RoadDist", "SubstationDist", "HVLineDist", "MVLineDist", "HydropowerDist",
    "X_deg", "Y_deg", "SADieselFuelCost",
]


def compare_arms(proc_r0, proc_r1, years, cfg, out_dir, label, hybrid_status,
                 pe_cols: list[str]) -> pd.DataFrame:
    df0 = proc_r0.df.copy()
    df1 = proc_r1.df.copy()

    print("\n" + "=" * 65)
    print("R0 vs R1 comparison")
    print(f"PV-hybrid: {'enabled' if hybrid_status.get('pv_ok') else 'DISABLED'}")
    print(f"Wind-hybrid: {'enabled' if hybrid_status.get('wind_ok') else 'DISABLED'}")
    print("=" * 65)

    # F1 post-run assertion: check which columns differ between the two arms
    common_cols = [c for c in df0.columns if c in df1.columns]
    pe_col_set  = set(pe_cols) | {"AverageToPeakLoadRatio"}
    diff_cols   = [c for c in common_cols if not df0[c].equals(df1[c])]
    phys_differ = [c for c in diff_cols if c in _PHYSICAL_INPUT_COLS]

    print(f"\n  F1 POST-RUN ASSERTION:")
    print(f"    Total columns differing R0 vs R1: {len(diff_cols)}")
    print(f"    PE/demand columns (expected to differ): "
          f"{[c for c in diff_cols if c in pe_col_set]}")
    if phys_differ:
        print(f"    *** ASSERTION FAIL: physical input columns differ: {phys_differ} ***")
    else:
        print(f"    PASS — no physical input column differs between arms.")
    non_pe_diff = [c for c in diff_cols if c not in pe_col_set]
    print(f"    Non-PE differing columns ({len(non_pe_diff)} downstream results): "
          f"{non_pe_diff[:20]}{'...' if len(non_pe_diff) > 20 else ''}")

    rows = []
    for year in years:
        code_col = "FinalElecCode" + str(year)
        inv_col  = "InvestmentCost" + str(year)
        cap_col  = "NewCapacity" + str(year)

        for arm, df in [("R0", df0), ("R1", df1)]:
            if code_col not in df.columns:
                print(f"  WARN: {code_col} missing from {arm}")
                continue
            for code in [1, 3, 5, 6, 7, 99]:
                mask = df[code_col] == code
                rows.append({
                    "year": year, "arm": arm, "tech_code": code,
                    "n_settlements": int(mask.sum()),
                    "population":    float(df.loc[mask, "Pop"].sum()) if "Pop" in df.columns else np.nan,
                    "investment_usd": float(df.loc[mask, inv_col].sum()) if inv_col in df.columns else np.nan,
                    "capacity_kw":   float(df.loc[mask, cap_col].sum()) if cap_col in df.columns else np.nan,
                })

    if not rows:
        print("  No tech-split data.")
        return pd.DataFrame()

    comp_df = pd.DataFrame(rows)
    comp_path = out_dir / f"{label}_tech_split.csv"
    comp_df.to_csv(comp_path, index=False)
    print(f"  Tech-split table → {comp_path.relative_to(REPO)}")

    tech_labels = {1: "Grid", 3: "SA_PV", 5: "MG_PVHybrid",
                   6: "MG_Wind", 7: "MG_Hydro", 99: "Unelectrified"}

    for year in years:
        switches_all  = (df0["FinalElecCode" + str(year)] != df1["FinalElecCode" + str(year)]).sum()
        switches_hyb  = ((df1["FinalElecCode" + str(year)].isin([5, 6])) &
                         (~df0["FinalElecCode" + str(year)].isin([5, 6]))).sum()
        print(f"  Year {year}: {switches_all:,} settlements switch technology R0→R1 "
              f"(of which {switches_hyb:,} move INTO hybrid)")

    last_year = years[-1]
    print(f"\n  Technology split at {last_year} (settlements | population):")
    print(f"  {'Tech':<18} {'R0 sett':>10} {'R0 pop':>12} {'R1 sett':>10} {'R1 pop':>12}")
    print(f"  {'-'*65}")
    for code in [1, 3, 5, 6, 7, 99]:
        lbl = tech_labels.get(code, str(code))
        r0  = comp_df[(comp_df.year == last_year) & (comp_df.arm == "R0") & (comp_df.tech_code == code)]
        r1  = comp_df[(comp_df.year == last_year) & (comp_df.arm == "R1") & (comp_df.tech_code == code)]
        n0  = int(r0["n_settlements"].values[0]) if len(r0) else 0
        p0  = float(r0["population"].values[0])   if len(r0) else 0
        n1  = int(r1["n_settlements"].values[0]) if len(r1) else 0
        p1  = float(r1["population"].values[0])   if len(r1) else 0
        print(f"  {lbl:<18} {n0:>10,} {p0:>12,.0f} {n1:>10,} {p1:>12,.0f}")

    for year in years:
        r0y  = comp_df[(comp_df.year == year) & (comp_df.arm == "R0")]
        r1y  = comp_df[(comp_df.year == year) & (comp_df.arm == "R1")]
        inv0 = r0y["investment_usd"].sum()
        inv1 = r1y["investment_usd"].sum()
        cap0 = r0y["capacity_kw"].sum()
        cap1 = r1y["capacity_kw"].sum()
        print(f"\n  Year {year}:")
        print(f"    R0 investment: ${inv0/1e9:.3f} bn  |  R1: ${inv1/1e9:.3f} bn  |  ΔR1−R0: ${(inv1-inv0)/1e9:+.3f} bn")
        print(f"    R0 capacity:   {cap0/1e3:.1f} MW   |  R1: {cap1/1e3:.1f} MW   |  ΔR1−R0: {(cap1-cap0)/1e3:+.1f} MW")

    # Switch matrix for the final year
    print(f"\n  Switch matrix R0→R1 at {last_year}:")
    fc0 = df0["FinalElecCode" + str(last_year)]
    fc1 = df1["FinalElecCode" + str(last_year)]
    for from_code in [3, 1, 5, 7]:
        for to_code in [1, 3, 5, 7]:
            n = ((fc0 == from_code) & (fc1 == to_code)).sum()
            if n > 0:
                fl = tech_labels.get(from_code, str(from_code))
                tl = tech_labels.get(to_code, str(to_code))
                print(f"    {fl} → {tl}: {n:,}")

    return comp_df
