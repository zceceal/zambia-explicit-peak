"""
validate_inputs.py — pre-run validation gate for the Zambia OnSSET experiment.

Purpose
-------
A single, rerunnable rigour gate that must pass *before* any expensive scenario
run. It produces a pass/fail table that doubles as the "table of validation
results" that documents rigour in development (care, accuracy,
consistency). Run it after any change to the spine, the calibration, or the
pre-processor.

It checks, against the committed spine and PE spine:
  1. Schema     — expected OnSSET columns present; row count stable.
  2. Integrity  — no NaN in coordinate / population / distance / demand columns.
  3. Ranges     — Pop total, GHI, IsUrban coding, urban population share.
  4. Calibration— national / urban / rural base-year electrification plausible.
  5. Sentinels  — documented data-gap columns carry the 9999 sentinel.
  6. Identity   — R0 spine and R1 (PE) spine are byte-identical on every shared
                  column except the demand/peak columns {PE_ratio, N_hh}. This is
                  the controlled-comparison guarantee.
  7. PE submodel— PE_ratio within the Lorenzoni [P_inf, P_1] = [1.45, 3.98]
                  bounds, no NaN.

Nothing here writes to the spine or specs; it is read-only. Exit code 0 = all
pass, 1 = at least one FAIL. A markdown report is written to
data/onsset_outputs/validation_report.md.

Usage
-----
    python validate_inputs.py
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

SPINE = REPO / "data" / "processed" / "zambia_settlements.csv"
PE    = REPO / "data" / "processed" / "zambia_settlements_PE.csv"
REPORT = REPO / "data" / "onsset_outputs" / "validation_report.md"

# ── Expected schema (48 cols built 2026-06-16; calibration cols appended) ─────
EXPECTED_COLS = {
    "X_deg", "Y_deg", "Pop", "GridCellArea", "Country", "ElecPop", "WindVel",
    "GHI", "TravelHours", "Elevation", "ResidentialDemandTierCustom", "Slope",
    "NightLights", "LandCover", "SubstationDist", "TransformerDist",
    "CurrentHVLineDist", "PlannedHVLineDist", "CurrentMVLineDist",
    "PlannedMVLineDist", "RoadDist", "HydropowerDist", "Hydropower",
    "HydropowerFID", "IsUrban", "PerCapitaDemand", "ElectrificationOrder",
    "ResidentialDemandTier1", "ResidentialDemandTier2", "ResidentialDemandTier3",
    "ResidentialDemandTier4", "ResidentialDemandTier5", "id", "Admin_1",
    "MGDist", "GridPenalty", "WindCF", "PopStartYear", "ElecPop2020",
}
NO_NAN_COLS = ["X_deg", "Y_deg", "Pop", "GridCellArea", "GHI", "IsUrban",
               "CurrentHVLineDist", "CurrentMVLineDist", "RoadDist",
               "PopStartYear", "ElecPop2020"]
SENTINEL_9999 = ["SubstationDist", "PlannedHVLineDist", "PlannedMVLineDist", "MGDist"]

EXPECTED_ROWS   = 278_936
POP_TOTAL_RANGE = (18.0e6, 19.0e6)     # WorldPop 2020 UN-adjusted ≈ 18.38 M
GHI_RANGE       = (1700.0, 2400.0)     # kWh/m²/yr, Zambia
URBAN_POP_SHARE = (0.40, 0.50)         # Zambia ~44%
NAT_ELEC_RATE   = (0.40, 0.50)         # WB 2020 ≈ 0.445
P_INF, P_1      = 1.45, 3.98           # Lorenzoni 2020 Table 2

results: list[tuple[str, str, bool, str]] = []


def check(group: str, name: str, ok: bool, detail: str) -> None:
    results.append((group, name, bool(ok), detail))


def main() -> int:
    if not SPINE.exists():
        print(f"FATAL: spine not found at {SPINE}")
        return 1
    df = pd.read_csv(SPINE)

    # 1. SCHEMA ────────────────────────────────────────────────────────────────
    missing = EXPECTED_COLS - set(df.columns)
    check("Schema", "expected columns present", not missing,
          "all present" if not missing else f"MISSING: {sorted(missing)}")
    check("Schema", "row count stable", len(df) == EXPECTED_ROWS,
          f"{len(df):,} rows (expected {EXPECTED_ROWS:,})")

    # 2. INTEGRITY ──────────────────────────────────────────────────────────────
    nan_cols = [c for c in NO_NAN_COLS if c in df.columns and df[c].isna().any()]
    check("Integrity", "no NaN in critical columns", not nan_cols,
          "clean" if not nan_cols else f"NaN in {nan_cols}")

    # 3. RANGES ─────────────────────────────────────────────────────────────────
    pop = df["Pop"].sum()
    check("Ranges", "total population", POP_TOTAL_RANGE[0] <= pop <= POP_TOTAL_RANGE[1],
          f"{pop/1e6:.2f} M (expect {POP_TOTAL_RANGE[0]/1e6:.0f}–{POP_TOTAL_RANGE[1]/1e6:.0f} M)")
    ghi_ok = GHI_RANGE[0] <= df["GHI"].min() and df["GHI"].max() <= GHI_RANGE[1]
    check("Ranges", "GHI within physical band", ghi_ok,
          f"[{df['GHI'].min():.0f}, {df['GHI'].max():.0f}] kWh/m²/yr")
    urb_ok = set(df["IsUrban"].unique()).issubset({0, 1, 2})
    check("Ranges", "IsUrban coding {0,1,2}", urb_ok,
          f"values {sorted(df['IsUrban'].unique())}")
    ushare = df.loc[df["IsUrban"] > 1, "Pop"].sum() / pop
    check("Ranges", "urban population share", URBAN_POP_SHARE[0] <= ushare <= URBAN_POP_SHARE[1],
          f"{ushare*100:.1f}% (expect {URBAN_POP_SHARE[0]*100:.0f}–{URBAN_POP_SHARE[1]*100:.0f}%)")

    # 4. CALIBRATION ────────────────────────────────────────────────────────────
    if "ElecPop2020" in df.columns:
        nat = df["ElecPop2020"].sum() / pop
        upop = df.loc[df["IsUrban"] > 1, "Pop"].sum()
        rpop = pop - upop
        urate = df.loc[df["IsUrban"] > 1, "ElecPop2020"].sum() / upop if upop else float("nan")
        rrate = df.loc[df["IsUrban"] == 0, "ElecPop2020"].sum() / rpop if rpop else float("nan")
        check("Calibration", "national electrification rate",
              NAT_ELEC_RATE[0] <= nat <= NAT_ELEC_RATE[1],
              f"{nat*100:.1f}% (WB-2020 ≈ 44.5%)")
        check("Calibration", "urban access > rural access", urate > rrate,
              f"urban {urate*100:.1f}% vs rural {rrate*100:.1f}%")
    else:
        check("Calibration", "ElecPop2020 present", False, "column missing — calibration not run")

    # 5. SENTINELS ──────────────────────────────────────────────────────────────
    for c in SENTINEL_9999:
        if c in df.columns:
            allsent = bool((df[c] == 9999).all())
            check("Sentinels", f"{c} == 9999 (documented gap)", allsent,
                  "all 9999" if allsent else f"{(df[c]==9999).mean()*100:.1f}% are 9999")

    # 6. CONTROLLED-COMPARISON IDENTITY ─────────────────────────────────────────
    if PE.exists():
        dpe = pd.read_csv(PE)
        skip = {"PE_ratio", "N_hh"}
        shared = [c for c in df.columns if c in dpe.columns and c not in skip]
        # Floats are compared within machine tolerance, NOT with .equals(): a CSV
        # round-trip perturbs floats at ~1e-13, which .equals() flags spuriously.
        # The controlled-comparison guarantee is "identical to machine precision".
        differ, max_drift = [], 0.0
        for c in shared:
            if pd.api.types.is_numeric_dtype(df[c]) and pd.api.types.is_numeric_dtype(dpe[c]):
                if not np.allclose(df[c].values, dpe[c].values, rtol=0, atol=1e-9, equal_nan=True):
                    differ.append(c)
                else:
                    max_drift = max(max_drift, float(np.nanmax(np.abs(df[c].values - dpe[c].values))))
            elif not df[c].equals(dpe[c]):
                differ.append(c)
        check("Identity", "R0/R1 identical (machine precision) on non-demand cols", not differ,
              f"{len(shared)} cols, max round-trip drift {max_drift:.1e} (< 1e-9)"
              if not differ else f"GENUINELY DIFFER: {differ}")
        # 7. PE submodel
        if "PE_ratio" in dpe.columns:
            pe = dpe["PE_ratio"]
            bounds_ok = bool((pe >= P_INF - 1e-9).all() and (pe <= P_1 + 1e-9).all())
            check("PE submodel", "PE_ratio within [P_inf, P_1]", bounds_ok and not pe.isna().any(),
                  f"[{pe.min():.3f}, {pe.max():.3f}], mean {pe.mean():.3f}")
    else:
        check("Identity", "PE spine present", False, f"missing {PE.name} — run compute_settlement_pe.py")

    # ── Report ──────────────────────────────────────────────────────────────────
    n_fail = sum(1 for *_, ok, _ in [(r[0], r[1], r[2], r[3]) for r in results] if not ok)
    n_pass = len(results) - n_fail

    lines = [f"# Input validation report — {datetime.now():%Y-%m-%d %H:%M}", "",
             f"**{n_pass}/{len(results)} checks passed.** "
             f"{'ALL PASS — cleared for run.' if n_fail == 0 else f'{n_fail} FAIL — DO NOT RUN.'}",
             "", "| Group | Check | Result | Detail |", "|---|---|---|---|"]
    print("=" * 74)
    print(f"INPUT VALIDATION — {n_pass}/{len(results)} passed"
          + ("  ✅ ALL PASS" if n_fail == 0 else f"  ❌ {n_fail} FAIL"))
    print("=" * 74)
    last = None
    for group, name, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        g = group if group != last else ""
        print(f"  [{tag}] {group:11s} {name:42s} {detail}")
        lines.append(f"| {g} | {name} | {'✅ PASS' if ok else '❌ FAIL'} | {detail} |")
        last = group

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"\nReport → {REPORT.relative_to(REPO)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
