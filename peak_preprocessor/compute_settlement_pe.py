"""
Compute per-settlement PE_ratio column from the Zambia settlement spine.

Reads:   data/processed/zambia_settlements.csv  (spine — NOT overwritten)
Writes:  data/processed/zambia_settlements_PE.csv  (spine + PE_ratio column)

N per settlement is derived as:
    N = max(1, Pop / HH_size)
where HH_size = 4.6 for urban (IsUrban == 1) and 5.0 for rural (IsUrban == 0),
per the ZamStats 2022 Census of Population and Housing (Section 4.3).

Coherence note (2026-06-20): these are now the SAME household-size values used
by OnSSET's demand computation (specs NumPeoplePerHHUrban=4.6, Rural=5.0), so the
previous incoherence (DHS 5.0/5.0 for demand vs Egli 4.5/5.3 for N) is resolved.
DHS 2018 (5.0/5.0) and Egli 2023 Table S8 (4.5/5.3, global) are retained as
documented sensitivities.

Central case: N_mid = 20 (beta ≈ 0.316).
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np

# ── Resolve paths relative to repo root ──────────────────────────────────────
HERE    = Path(__file__).resolve().parent
REPO    = HERE.parents[2]   # peak_preprocessor -> scripts -> _claude_workspace -> repo root
SPINE   = REPO / "data" / "processed" / "zambia_settlements.csv"
OUT     = REPO / "data" / "processed" / "zambia_settlements_PE.csv"

sys.path.insert(0, str(HERE))
from pe_diversity import pe_from_n, N_MID_CENTRAL, compute_beta

# ── Household sizes for N computation (ZamStats 2022 Census, Section 4.3) ─────
# Coherent with OnSSET demand (specs NumPeoplePerHHUrban=4.6, Rural=5.0).
# Sensitivities: DHS 2018 (5.0/5.0); Egli 2023 Table S8 (4.5/5.3, global).
HH_SIZE_URBAN = 4.6
HH_SIZE_RURAL = 5.0

REQUIRED_COLS = {"Pop", "IsUrban"}


def main() -> None:
    print(f"Reading spine: {SPINE}")
    df = pd.read_csv(SPINE)
    print(f"  {len(df):,} rows, {len(df.columns)} columns")

    # ── Validate required columns ─────────────────────────────────────────────
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise KeyError(
            f"Required column(s) missing from spine: {missing}\n"
            f"Available: {sorted(df.columns)}"
        )

    print(f"  Pop range:    [{df['Pop'].min():.1f}, {df['Pop'].max():.1f}]")
    print(f"  IsUrban values: {sorted(df['IsUrban'].unique())}")

    # ── Compute household count N ─────────────────────────────────────────────
    is_urban   = df["IsUrban"] > 1  # consistent with calibration/LCOE scripts; spine has only {0, 2}
    hh_size    = np.where(is_urban, HH_SIZE_URBAN, HH_SIZE_RURAL)
    N_raw      = df["Pop"].values / hh_size
    N_clipped  = np.maximum(N_raw, 1.0)   # enforce N >= 1

    n_clipped_count = int(np.sum(N_raw < 1.0))
    print(f"\n  Settlements with Pop/HH_size < 1 (clipped to N=1): {n_clipped_count:,}")

    # ── Compute PE_ratio for central N_mid=20 ────────────────────────────────
    beta_central = compute_beta(N_MID_CENTRAL)
    print(f"\n  Central case: N_mid={N_MID_CENTRAL}, beta={beta_central:.6f}")

    df["N_hh"]    = N_clipped
    df["PE_ratio"] = pe_from_n(N_clipped, N_mid=N_MID_CENTRAL)

    # ── Sanity checks ─────────────────────────────────────────────────────────
    from pe_diversity import P_1_DEFAULT, P_INF_DEFAULT
    EPS = 1e-10  # float arithmetic at clipped N=1 may land epsilon above P_1
    assert ((df["PE_ratio"] >= P_INF_DEFAULT - EPS) &
            (df["PE_ratio"] <= P_1_DEFAULT   + EPS)).all(), \
        "PE_ratio out of [P_inf, P_1] bounds — logic error"
    assert not df["PE_ratio"].isna().any(), "NaN in PE_ratio"

    print(f"\n  PE_ratio summary:")
    print(f"    min  = {df['PE_ratio'].min():.4f}")
    print(f"    mean = {df['PE_ratio'].mean():.4f}")
    print(f"    max  = {df['PE_ratio'].max():.4f}")

    # ── Save (do not overwrite spine) ─────────────────────────────────────────
    df.to_csv(OUT, index=False)
    print(f"\nWritten: {OUT}")
    print(f"  New columns added: N_hh, PE_ratio")
    print(f"  Original spine unchanged at: {SPINE}")


if __name__ == "__main__":
    main()
