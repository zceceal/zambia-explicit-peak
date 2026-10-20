"""
s26_run_diesel_oat.py — diesel price, one at a time, on the full spine.

Re-solves R0 and R1 (N_mid = 20) on all 270,526 settlements at each diesel price and reports
DLCOE%, SA_PV->Grid switches, the technology mix, and two diesel diagnostics the s08 Morris screen
cannot give:

1. MG_PVHybrid diesel use. The hybrid optimiser may size a diesel genset (up to diesel_limit = 0.5
   of generation). The lookup table's fuel cost is captured as it is built, and each settlement
   allocated MG_PVHybrid is flagged as burning diesel if its table entry has fuel cost > 0.

2. SA_Diesel shadow cost. SA_Diesel is not in the candidate list of any arm runner (`techs` in
   s06/s08/s09/onsset_helpers omits it), so the solve never costs it. Here its LCOE is computed at
   2030 from the arm's live state, with the same Technology object build_tech_objects() returns,
   and compared with the LCOE of the technology the solve chose. It is written to a separate array
   and never to the frame: it cannot change the allocation, and the central gate checks that the
   allocation equals the committed s06 outputs exactly.

Conventions:
- pv_lut_cache=None throughout: the PV-hybrid table is rebuilt in every arm, after seed 42, as s06
  does, so each arm sees its own diesel price.
- Gate: the central variant must reproduce the s06 headline (+-OAT_TOL_PP on DLCOE%, exact switch
  count) and the s06 2030 allocation and LCOE column exactly, or no variant is run.
- Outputs carry the RUN_LABEL prefix; names starting 2026-08_final or 2026-09 are refused, and no
  existing file is overwritten. The summary is rewritten after each variant.

Usage: python scripts/s26_run_diesel_oat.py [--variants central,diesel-0.95,...]
"""

import argparse
import copy
import time
from pathlib import Path

import numpy as np
import pandas as pd

import s09_run_oat_checks as s09
from s09_run_oat_checks import (
    run_arm_full, make_full_pair,
    compute_delta_lcoe_pct, count_sapv_to_grid,
    GRID_CAP_COST_CENTRAL, GRID_GEN_COST_CENTRAL,
    STAGE4_DELTA, STAGE4_SWITCHES, OAT_TOL_PP, OAT_SWITCH_TOL,
    PE_N20, TX_SHP, SOLAR_PROFILE, WIND_PROFILE,
    OUTDIR, REPO,
)
from onsset_helpers import load_solar_profile, load_wind_profile, load_config, build_tech_objects
from onsset import (
    SettlementProcessor,
    SET_GHI, SET_TIER, SET_MG_DIESEL_FUEL, SET_SA_DIESEL_FUEL, SET_ENERGY_PER_CELL, SET_POP,
    SET_NEW_CONNECTIONS, SET_TOTAL_ENERGY_PER_CELL, SET_ELEC_FINAL_CODE, SET_NUM_PEOPLE_PER_HH,
    SET_GRID_CELL_AREA, SET_AVERAGE_TO_PEAK,
)

RUN_LABEL   = "2026-10_diesel_followup"
SUMMARY_DIR = REPO / "results" / "summary"
YEAR        = 2030
CENTRAL_DIESEL = 1.90

# (label, diesel price USD/L, note). Coarse first pass; finer variants are added only if diesel
# starts winning between two of these.
VARIANTS = [
    ("central",     CENTRAL_DIESEL, "Gate check — must reproduce the s06 central headline"),
    ("diesel-0.95", 0.95,           "-50% on the ERB May 2026 pump price"),
    ("diesel-0.38", 0.38,           "-80%"),
    ("diesel-0.10", 0.10,           "~free fuel; upper-bound stress test"),
]

CODE_NAMES = {1: "Grid", 3: "SA_PV", 5: "MG_PVHybrid", 6: "MG_Wind", 7: "MG_Hydro", 99: "None"}


def _out(path: Path) -> Path:
    """Refuse committed-result prefixes and existing files."""
    if path.name.startswith(("2026-08_final", "2026-09")):
        raise RuntimeError(f"refusing to write a committed-result name: {path.name}")
    if path.exists():
        raise RuntimeError(f"refusing to overwrite existing file: {path}")
    return path


# ── Diagnostics captured during each arm (read-only wrappers) ────────────────
_capture = {}   # filled per arm: fuel LUT, shadow SA_Diesel LCOEs, MG diesel flags
_cfg_now = {}   # cfg of the arm being solved, for the SA_Diesel Technology object

_orig_build_lut = s09.build_pv_hybrid_lookup
_orig_offgrid_min = s09.compute_offgrid_min


def _spy_build_lut(onsseter, ghi_profile, temp_profile, year, *args, **kwargs):
    out = _orig_build_lut(onsseter, ghi_profile, temp_profile, year, *args, **kwargs)
    if year == YEAR:
        _, _, _, fuel_lut, ghi_min, ghi_max, d_min, d_max = out
        _capture["fuel_lut"] = dict(fuel_lut)
        _capture["lut_range"] = (ghi_min, ghi_max, d_min, d_max)
    return out


def _spy_offgrid_min(onsseter, year, off_grid_techs):
    out = _orig_offgrid_min(onsseter, year, off_grid_techs)
    if year != YEAR:
        return out
    df = onsseter.df
    start_yr = int(_cfg_now["cfg"]["scenario"]["start_year"])
    end_yr   = int(_cfg_now["cfg"]["scenario"]["end_year"])
    sa_diesel = build_tech_objects(_cfg_now["cfg"], start_yr, end_yr)["sa_diesel"]
    common = dict(
        energy_per_cell=df[SET_ENERGY_PER_CELL + str(year)].copy(),
        start_year=start_yr, end_year=end_yr,
        people=df[SET_POP + str(year)].copy(),
        new_connections=df[SET_NEW_CONNECTIONS + str(year)].copy(),
        total_energy_per_cell=df[SET_TOTAL_ENERGY_PER_CELL].copy(),
        prev_code=df[SET_ELEC_FINAL_CODE + str(start_yr)].copy(),
        num_people_per_hh=df[SET_NUM_PEOPLE_PER_HH].copy(),
        grid_cell_area=df[SET_GRID_CELL_AREA].copy(),
        fuel_cost=df[SET_SA_DIESEL_FUEL + str(year)].copy(),
        base_to_peak_load_ratio=df[SET_AVERAGE_TO_PEAK].copy(),
    )
    # Capacity factor: the Technology's own 0.5, and get_lcoe's default 0.9 (smaller genset,
    # so cheaper diesel: the more favourable bound for diesel).
    lc_05 = sa_diesel.get_lcoe(capacity_factor=sa_diesel.capacity_factor, **common)[0]
    lc_09 = sa_diesel.get_lcoe(capacity_factor=0.9, **common)[0]
    _capture["sad_lcoe_cf05"] = np.asarray(lc_05, dtype=float).ravel().copy()
    _capture["sad_lcoe_cf09"] = np.asarray(lc_09, dtype=float).ravel().copy()
    _capture["sad_fuel_usd_kwh"] = df[SET_SA_DIESEL_FUEL + str(year)].to_numpy().copy()
    _capture["mg_fuel_usd_kwh"] = df[SET_MG_DIESEL_FUEL + str(year)].to_numpy().copy()

    # MG_PVHybrid: the table entry each settlement reads, as apply_pv_hybrid_lookup forms the key
    ghi_min, ghi_max, d_min, d_max = _capture["lut_range"]
    fl = _capture["fuel_lut"]
    _capture["mg_lut_fuel"] = np.array([
        fl.get((int(t), max(ghi_min, min(ghi_max, round(g, -2))),
                max(d_min, min(d_max, round(d, 1)))), np.nan)
        for t, g, d in zip(df[SET_TIER].to_numpy(), df[SET_GHI].to_numpy(),
                           df[SET_MG_DIESEL_FUEL + str(year)].to_numpy())])
    _capture["ids"] = df["id"].to_numpy().copy()
    return out


s09.build_pv_hybrid_lookup = _spy_build_lut
s09.compute_offgrid_min    = _spy_offgrid_min


def tech_mix(df: pd.DataFrame) -> dict:
    counts = df[f"FinalElecCode{YEAR}"].value_counts().to_dict()
    return {f"n_code{int(k)}": int(v) for k, v in counts.items()}


def arm_diagnostics(df: pd.DataFrame, cap: dict) -> tuple[dict, pd.DataFrame]:
    """SA_Diesel shadow comparison and MG diesel use for one solved arm."""
    assert np.array_equal(cap["ids"], df["id"].to_numpy()), "row order changed after 2030 step"
    fc      = df[f"FinalElecCode{YEAR}"].to_numpy()
    win     = df[f"MinimumOverallLCOE{YEAR}"].to_numpy()
    prev    = df[f"FinalElecCode{int(_cfg_now['cfg']['scenario']['start_year'])}"].to_numpy()
    elig    = (prev != 1) & np.isfinite(win) & (win < 99)   # not grid-connected in the base year
    out = {}
    for tag in ("cf05", "cf09"):
        sad = cap[f"sad_lcoe_{tag}"]
        ratio = np.nan_to_num(np.where(elig, sad / win, np.inf), nan=np.inf)
        wins = elig & (sad < win)
        i = int(np.argmin(ratio))
        out[f"sad_{tag}_n_lower"]    = int(wins.sum())
        out[f"sad_{tag}_share_pct"]  = 100.0 * wins.sum() / elig.sum()
        out[f"sad_{tag}_pop_lower"]  = float(df[f"{SET_POP}{YEAR}"].to_numpy()[wins].sum())
        out[f"sad_{tag}_min_ratio"]  = float(ratio[i])
        out[f"sad_{tag}_closest_id"] = df["id"].iloc[i]
        out[f"sad_{tag}_closest_sad_lcoe"] = float(sad[i])
        out[f"sad_{tag}_closest_win_lcoe"] = float(win[i])
        out[f"sad_{tag}_closest_win_tech"] = CODE_NAMES.get(int(fc[i]), str(fc[i]))
        out[f"sad_{tag}_closest_urban"] = int(df["IsUrban"].iloc[i] > 1)
        out[f"sad_{tag}_closest_pop"]   = float(df[f"{SET_POP}{YEAR}"].iloc[i])
        out[f"sad_{tag}_median_ratio"]  = float(np.median(ratio[elig]))
    out["n_eligible"] = int(elig.sum())
    mg = fc == 5
    mg_fuel = cap["mg_lut_fuel"][mg]
    out["mg_n"]             = int(mg.sum())
    out["mg_n_diesel_used"] = int((mg_fuel > 0).sum())
    out["mg_n_lut_miss"]    = int(np.isnan(mg_fuel).sum())   # should be 0
    out["mg_median_lut_fuel"] = float(np.nanmedian(mg_fuel)) if mg.any() else float("nan")
    out["lut_n_entries_fuel_gt0"] = int(sum(v > 0 for v in cap["fuel_lut"].values()))
    out["lut_n_entries"]    = len(cap["fuel_lut"])

    per = pd.DataFrame({
        "id": df["id"].to_numpy(), "IsUrban": df["IsUrban"].to_numpy(),
        f"Pop{YEAR}": df[f"{SET_POP}{YEAR}"].to_numpy(),
        f"FinalElecCode{YEAR}": fc, f"MinimumOverallLCOE{YEAR}": win, "eligible": elig,
        "SA_Diesel_LCOE_cf05": cap["sad_lcoe_cf05"], "SA_Diesel_LCOE_cf09": cap["sad_lcoe_cf09"],
        "SADieselFuelCost": cap["sad_fuel_usd_kwh"], "MGDieselFuelCost": cap["mg_fuel_usd_kwh"],
        "MG_lut_fuel": cap["mg_lut_fuel"],
    })
    return out, per


def movers(df_c: pd.DataFrame, df_v: pd.DataFrame) -> pd.DataFrame:
    """Settlements whose 2030 technology differs from the central solve of the same arm."""
    c = df_c[f"FinalElecCode{YEAR}"].to_numpy(); v = df_v[f"FinalElecCode{YEAR}"].to_numpy()
    m = c != v
    return pd.DataFrame({
        "id": df_v["id"].to_numpy()[m], "from": c[m], "to": v[m],
        "IsUrban": df_v["IsUrban"].to_numpy()[m], f"Pop{YEAR}": df_v[f"{SET_POP}{YEAR}"].to_numpy()[m],
    })


def main():
    global RUN_LABEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(v[0] for v in VARIANTS))
    ap.add_argument("--label", default=RUN_LABEL, help=f"output file prefix (default {RUN_LABEL})")
    args = ap.parse_args()
    RUN_LABEL = args.label
    wanted = args.variants.split(",")
    variants = [v for v in VARIANTS if v[0] in wanted]
    if variants[0][0] != "central":
        raise SystemExit("the central gate variant must run first")

    summary_paths = [_out(OUTDIR / f"{RUN_LABEL}_oat_diesel_price.csv"),
                     _out(SUMMARY_DIR / f"{RUN_LABEL}_oat_diesel_price.csv")]
    print("  Output paths (new files only):")
    for p in summary_paths:
        print(f"    {p}")
    for lab, _, _ in variants:
        for p in (OUTDIR / f"{RUN_LABEL}_sadiesel_shadow_{lab}.csv",
                  OUTDIR / f"{RUN_LABEL}_movers_{lab}.csv",
                  OUTDIR / f"{RUN_LABEL}_oat_{lab}_R0.csv",
                  OUTDIR / f"{RUN_LABEL}_oat_{lab}_R1_n20.csv"):
            print(f"    {_out(p)}")

    t_total = time.time()
    print("\n[1/3] Loading profiles, TX network, config …")
    ghi_profile, temp_profile = load_solar_profile(SOLAR_PROFILE)
    wind_profile = load_wind_profile(WIND_PROFILE)
    x_tx, y_tx = SettlementProcessor.start_extension_points(str(TX_SHP))
    if len(x_tx) == 0:
        raise RuntimeError("transmission network yielded zero starting points")
    cfg_base = load_config()
    assert abs(float(cfg_base["diesel_price_usd_per_l"]) - CENTRAL_DIESEL) < 1e-12

    print("\n[2/3] Loading full GRID3 spine …")
    spine = pd.read_csv(PE_N20)
    # Only N_mid = 20 is solved, so the n10/n50 spines are not read (make_full_pair drops them).
    spine = spine.rename(columns={"PE_ratio": "PE_ratio_n20", "N_hh": "N_hh_val"})
    print(f"  Loaded: {len(spine):,} settlements")
    spine_r0, spine_r1 = make_full_pair(spine, n_mid=20)
    del spine

    keep = ["id", "IsUrban", f"{SET_POP}{YEAR}", f"FinalElecCode{YEAR}",
            f"MinimumOverallLCOE{YEAR}", f"EnergyPerSettlement{YEAR}"]
    central = {}
    rows = []
    print("\n[3/3] Running variants …")
    for label, price, note in variants:
        print(f"\n  Variant: {label}  diesel={price:.2f} USD/L — {note}")
        cfg_v = copy.deepcopy(cfg_base)
        cfg_v["grid"]["capacity_investment_cost_usd_kw"] = GRID_CAP_COST_CENTRAL
        cfg_v["grid"]["generation_cost_usd_kwh"] = GRID_GEN_COST_CENTRAL
        cfg_v["diesel_price_usd_per_l"] = float(price)
        _cfg_now["cfg"] = cfg_v

        t0 = time.time()
        arms, diag, per = {}, {}, []
        for arm, sp, nm in (("R0", spine_r0, None), ("R1", spine_r1, 20)):
            _capture.clear()
            df = run_arm_full(f"DZ_{arm}", sp, cfg_v, x_tx, y_tx, ghi_profile, temp_profile,
                              wind_profile, n_mid=nm, pv_lut_cache=None, silent=True)
            d, p = arm_diagnostics(df, _capture)
            diag[arm] = d
            per.append(p.add_prefix(f"{arm}_").rename(columns={f"{arm}_id": "id"}))
            if label != "central":
                df.to_csv(_out(OUTDIR / f"{RUN_LABEL}_oat_{label}_{'R0' if arm == 'R0' else 'R1_n20'}.csv"),
                          index=False)
            arms[arm] = df[keep].copy()
            del df

        delta = compute_delta_lcoe_pct(arms["R0"], arms["R1"])
        sw = count_sapv_to_grid(arms["R0"], arms["R1"])
        elapsed = time.time() - t0
        print(f"    DLCOE% = {delta:+.4f}%  SA_PV->Grid = {sw:,}  ({elapsed:.0f}s)")

        row = {"variant": label, "diesel_price_usd_l": price, "delta_lcoe_pct": delta,
               "switch_count": sw, "elapsed_s": elapsed, "note": note}
        for arm in ("R0", "R1"):
            for k, v in tech_mix(arms[arm]).items():
                row[f"{arm}_{k}"] = v
            for k, v in diag[arm].items():
                row[f"{arm}_{k}"] = v
            print(f"    {arm}: MG_PVHybrid {diag[arm]['mg_n']:,} (diesel-burning "
                  f"{diag[arm]['mg_n_diesel_used']:,}); SA_Diesel lower than chosen tech in "
                  f"{diag[arm]['sad_cf05_n_lower']:,} (CF 0.5) / {diag[arm]['sad_cf09_n_lower']:,} "
                  f"(CF 0.9) of {diag[arm]['n_eligible']:,}; closest ratio "
                  f"{diag[arm]['sad_cf09_min_ratio']:.3f} (CF 0.9)")

        shadow = per[0].merge(per[1], on="id", how="inner", validate="1:1")
        shadow.to_csv(_out(OUTDIR / f"{RUN_LABEL}_sadiesel_shadow_{label}.csv"), index=False)

        if label == "central":
            # Gate: headline and exact allocation against the committed s06 outputs.
            cols = ["id", f"FinalElecCode{YEAR}", f"MinimumOverallLCOE{YEAR}"]
            exact = True
            for arm, f in (("R0", "2026-08_final_lcoe_R0.csv"), ("R1", "2026-08_final_lcoe_R1_n20.csv")):
                # round_trip: pandas' default float parser can be one ulp off what to_csv wrote
                ref = pd.read_csv(OUTDIR / f, usecols=cols, float_precision="round_trip"
                                  ).set_index("id").loc[arms[arm]["id"]]
                same_code = np.array_equal(ref[cols[1]].to_numpy(), arms[arm][cols[1]].to_numpy())
                max_abs = float(np.max(np.abs(ref[cols[2]].to_numpy() - arms[arm][cols[2]].to_numpy())))
                same_lcoe = max_abs == 0.0
                print(f"    {arm} vs s06 {f}: FinalElecCode identical={same_code}, "
                      f"MinimumOverallLCOE identical={same_lcoe} (max |diff| {max_abs:.3g})")
                row[f"{arm}_identical_to_s06"] = bool(same_code and same_lcoe)
                exact &= same_code and same_lcoe
            gate_ok = (abs(delta - STAGE4_DELTA) <= OAT_TOL_PP
                       and abs(sw - STAGE4_SWITCHES) <= OAT_SWITCH_TOL and exact)
            row["gate_pass"] = gate_ok
            print(f"    GATE: DLCOE {delta:.4f} vs {STAGE4_DELTA:.4f} (tol {OAT_TOL_PP} pp), "
                  f"switches {sw:,} vs {STAGE4_SWITCHES:,} (tol {OAT_SWITCH_TOL}), exact s06 "
                  f"allocation {exact} -> {'PASS' if gate_ok else 'FAIL'}")
            central = arms
        else:
            for arm in ("R0", "R1"):
                mv = movers(central[arm], arms[arm])
                mv.insert(0, "arm", arm)
                row[f"{arm}_n_movers"] = len(mv)
                if arm == "R0":
                    mv_all = mv
                else:
                    mv_all = pd.concat([mv_all, mv])
                if len(mv):
                    print(f"    {arm} movers vs central: "
                          + ", ".join(f"{CODE_NAMES.get(a, a)}->{CODE_NAMES.get(b, b)}: {n}"
                                      for (a, b), n in mv.groupby(["from", "to"]).size().items()))
            mv_all.to_csv(_out(OUTDIR / f"{RUN_LABEL}_movers_{label}.csv"), index=False)

        rows.append(row)
        for p in summary_paths:
            pd.DataFrame(rows).to_csv(p, index=False)   # checkpoint after every variant
        del arms
        if label == "central" and not gate_ok:
            print("\n  GATE FAILED — no diesel variant run.")
            break

    out = pd.DataFrame(rows)
    print("\n" + "=" * 70)
    print(f"  COMPLETE — {(time.time() - t_total) / 60:.1f} min")
    print(out[["variant", "diesel_price_usd_l", "delta_lcoe_pct", "switch_count",
               "R0_mg_n", "R1_mg_n", "R0_mg_n_diesel_used", "R1_mg_n_diesel_used",
               "R0_sad_cf09_n_lower", "R1_sad_cf09_n_lower",
               "R0_sad_cf09_min_ratio", "R1_sad_cf09_min_ratio"]].to_string(index=False))


if __name__ == "__main__":
    main()
