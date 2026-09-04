"""
Build the R1 (explicit-peak) settlement spine for the 2050 horizon.

Pop2050 is produced by the engine's own SettlementProcessor.project_pop_and_urban(), called
with the 2050 scenario (WPP-2024 medium variant: 38,083,385 people, urban share 0.672) on the
same PopStartYear column the solve projects from. The household count N and PE_ratio are then
evaluated on that Pop2050 with the household sizes of config.yaml, exactly as s05 does for the
primary analysis year. The 2050 solve (s12) re-runs the projection itself and asserts that its
Pop2050 equals the one written here on every settlement.

Run from anywhere; paths resolve relative to the repository root:
  python scripts/s12b_build_2050_spine.py
Outputs: data/processed/zambia_grid3_spine_pe_2050_n20.csv  (+ _n10 / _n50 for the sweep)
"""
import sys, os
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
sys.path.insert(0, str(REPO / "peak_preprocessor"))
sys.path.insert(0, str(HERE))
from pe_diversity import pe_from_n
from s05_compute_peak_ratios import load_config, household_sizes, project_pop, n_hh_from_pop

PROC = REPO / "data" / "processed"

# confirmed WPP-2024 medium-variant 2050 targets (see SOURCES_WPP2050.md)
POP2050, URBAN2050 = 38_083_385, 0.672
START_YEAR, YEARS = 2020, [2050]


def main():
    cfg = load_config()
    hh_urban, hh_rural = household_sizes(cfg)
    for nmid, tag in [(20, "n20"), (10, "n10"), (50, "n50")]:
        spine = pd.read_csv(PROC / f"zambia_grid3_spine_pe_{tag}.csv")
        pop2050 = project_pop(spine, POP2050, URBAN2050, START_YEAR, YEARS)
        is_urban = (spine["IsUrban"] > 1).to_numpy()
        n_hh = n_hh_from_pop(pop2050, is_urban, hh_urban, hh_rural)
        out = spine.copy()
        out["Pop2050"] = pop2050
        out["N_hh"] = n_hh
        out["PE_ratio"] = pe_from_n(n_hh, N_mid=nmid)
        # the primary-year projection column is not meaningful in a 2050-only run
        out = out.drop(columns=[c for c in out.columns if c.startswith("Pop20") and c != "Pop2050"],
                       errors="ignore")
        path = PROC / f"zambia_grid3_spine_pe_2050_{tag}.csv"
        out.to_csv(path, index=False)
        print(f"  wrote {path.name}  (n_mid={nmid}; Pop2050 {pop2050.sum()/1e6:.3f} M, "
              f"urban {pop2050[is_urban].sum()/pop2050.sum()*100:.1f}%; "
              f"rural median N {np.median(n_hh[~is_urban]):.2f}, median P/E {np.median(out['PE_ratio']):.3f})")
    print("done. Run R1 2050 with these spines; R0 2050 uses the same specs (uniform BaseToPeak).")


if __name__ == "__main__":
    main()
