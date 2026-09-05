#!/usr/bin/env python3
"""
Acceptance test for the condition_df index-alignment fix (2026-08-16).

OnSSET sizes a stand-alone PV system as

    installed_capacity = peak_load / capacity_factor
                       = [E / (8760 * ATR)] / (GHI / 8760)
                       =  E / (ATR * GHI)

This script recomputes that closed form and reports the share of stand-alone PV
settlements it reproduces. It must report ~100%; REPRODUCING.md §7 explains what
a lower figure means.

Usage:
    python scripts/check_index_alignment.py data/onsset_outputs/<run>_R0.csv
"""
import sys
import numpy as np
import pandas as pd

NEEDED = ["GHI", "AverageToPeakLoadRatio", "EnergyPerSettlement2030",
          "FinalElecCode2030", "NewCapacity2030"]


def main(path: str) -> int:
    df = pd.read_csv(path, usecols=NEEDED)
    energy = df["EnergyPerSettlement2030"].to_numpy()
    predicted = energy / (df["AverageToPeakLoadRatio"].to_numpy() * df["GHI"].to_numpy())
    actual = df["NewCapacity2030"].to_numpy()
    sa_pv = df["FinalElecCode2030"].to_numpy() == 3

    share = 100.0 * np.isclose(predicted[sa_pv], actual[sa_pv], rtol=1e-6).mean()
    print(f"{path}")
    print(f"  stand-alone PV settlements : {int(sa_pv.sum()):,}")
    print(f"  reproduced by E/(ATR*GHI)  : {share:.3f}%")
    print(f"  total stand-alone capacity : {actual[sa_pv].sum() / 1e3:,.0f} MW")

    if share > 99.0:
        print("  PASS - index alignment is correct")
        return 0
    print("  FAIL - the frame index is still permuted; do not use these outputs")
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
