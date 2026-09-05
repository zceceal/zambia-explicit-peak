#!/usr/bin/env python3
"""
s25_collect_summaries.py — copy the summary CSVs s06, s08, s09, s10 and s11 write into
data/onsset_outputs/ (git-ignored) into results/summary/ (committed), so the committed
summary directory reflects the run that just produced it rather than whichever run last
happened to touch each file by hand.

Always overwrites: this is the last step of every full run, not a one-off migration.

    python scripts/s25_collect_summaries.py
"""

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "onsset_outputs"
DST = REPO / "results" / "summary"

FILES = [
    "2026-08_final_lcoe_tech_split.csv",
    "2026-08_final_morris_delta_lcoe.csv",
    "2026-08_final_morris_delta_lcoe_corrected.csv",
    "2026-08_final_morris_ee_raw.csv",
    "2026-08_final_morris_switch_count.csv",
    "2026-08_final_lhs_uncertainty.csv",
    "2026-08_final_lhs_emulator_validation.csv",
    "2026-08_final_took_effect_checks.csv",
    "2026-08_final_oat_drought_price.csv",
    "2026-08_final_oat_grid_costs.csv",
    "2026-08_final_per_connection_analysis.csv",
    "2026-08_final_sizing_convention_fband.csv",
    "2026-09-02_lhs_fullspine_validation.csv",
]


def main():
    DST.mkdir(parents=True, exist_ok=True)
    missing = [name for name in FILES if not (SRC / name).exists()]
    if missing:
        print("REFUSING TO RUN — missing source files in data/onsset_outputs/:")
        for name in missing:
            print(f"    {name}")
        return 1

    for name in FILES:
        shutil.copyfile(SRC / name, DST / name)
        print(f"  {name}")
    print(f"\ncopied {len(FILES)} files from {SRC.relative_to(REPO)} to {DST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
