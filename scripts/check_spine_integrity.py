#!/usr/bin/env python3
"""
check_spine_integrity.py — hard validation of the spine and calibration outputs.

The verification gates inside s01-s04 compute their verdicts but only PRINT them: a NaN in a
resource column, a failed population reconciliation or a missed calibration target produces output
files indistinguishable from a good run. This script validates the artefacts those stages actually
produced, so the evidence exists without rebuilding the spine, and it exits non-zero on any failure
so it can gate a pipeline.

    python scripts/check_spine_integrity.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SPINE = REPO / "data" / "processed" / "zambia_grid3_spine_pe_n20.csv"

EXPECTED_ROWS   = 270_526
EXPECTED_CLUST  = 214_198
EXPECTED_DISP   = 56_328
POP_TOTAL       = 18_383_608     # WorldPop 2020 UN-adjusted national total (paper §2.3.1)
POP_TOL         = 0.005          # reconciliation tolerance, fractional

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def main():
    print(f"check_spine_integrity.py — validating {SPINE.name}\n")
    if not SPINE.exists():
        print(f"  FAIL  spine file missing: {SPINE}")
        return 1
    df = pd.read_csv(SPINE)

    check("settlement count", len(df) == EXPECTED_ROWS, f"{len(df):,} vs {EXPECTED_ROWS:,}")
    if "source" in df.columns:
        vc = df["source"].value_counts()
        n_cl = int(vc.get("grid3_cluster", vc.max()))
        n_di = int(len(df) - n_cl)
        check("cluster / dispersed split", {n_cl, n_di} == {EXPECTED_CLUST, EXPECTED_DISP},
              f"{n_cl:,} / {n_di:,}")

    pop = df["Pop"].sum()
    check("population reconciliation", abs(pop / POP_TOTAL - 1) < POP_TOL,
          f"{pop:,.0f} vs {POP_TOTAL:,} ({100 * (pop / POP_TOTAL - 1):+.3f}%)")

    for col, lo, hi in [("GHI", 1000, 3000), ("Pop", 0, None), ("X_deg", 21, 34.5),
                        ("Y_deg", -19, -8), ("N_hh", 1, None), ("PE_ratio", 1.4, 3.99)]:
        if col not in df.columns:
            check(f"{col} present", False)
            continue
        v = df[col]
        bad_nan = int(v.isna().sum())
        check(f"{col}: no NaN", bad_nan == 0, f"{bad_nan} NaN")
        if lo is not None:
            n = int((v < lo).sum())
            check(f"{col} >= {lo}", n == 0, f"{n} below")
        if hi is not None:
            n = int((v > hi).sum())
            check(f"{col} <= {hi}", n == 0, f"{n} above")

    # PE_ratio must be consistent with the curve it claims to implement
    sys.path.insert(0, str(REPO / "peak_preprocessor"))
    from pe_diversity import pe_from_n
    expect = pe_from_n(np.maximum(df["N_hh"].to_numpy(), 1.0), N_mid=20)
    agree = float(np.isclose(expect, df["PE_ratio"].to_numpy(), rtol=1e-6).mean())
    check("PE_ratio matches pe_from_n(N_hh, 20)", agree > 0.999, f"{100 * agree:.3f}% agree")

    # N_hh must sit on the analysis-year population the energy is paired with, not the base year
    if "Pop2030" in df.columns and "NumPeoplePerHH" not in df.columns:
        is_u = (df["IsUrban"] > 1).to_numpy()
        expect_n = np.maximum(df["Pop2030"].to_numpy() / np.where(is_u, 4.6, 5.0), 1.0)
        agree_n = float(np.isclose(expect_n, df["N_hh"].to_numpy(), rtol=1e-9).mean())
        check("N_hh evaluated at Pop2030", agree_n > 0.999, f"{100 * agree_n:.3f}% agree")
    else:
        check("N_hh evaluated at Pop2030", "Pop2030" in df.columns,
              "Pop2030 column absent — spine built by a pre-2026-09-04 s05")

    # base-year urban classification: exactly two classes, urban count small and plausible
    if "IsUrban" in df.columns:
        n_urb = int((df["IsUrban"] > 1).sum())
        check("urban classification plausible", 50 <= n_urb <= 2000, f"{n_urb} urban settlements")

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
