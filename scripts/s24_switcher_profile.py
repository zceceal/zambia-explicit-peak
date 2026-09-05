"""
s24_switcher_profile.py — profile of the settlements that switch technology.

Reads the two published per-settlement solves and writes the switcher statistics
quoted in the paper (Section "Where the reallocation occurred") to
results/summary/. No solve is performed; this is a summary of existing outputs.

  python scripts/s24_switcher_profile.py

Household count N is the analysis-year one, Pop2030 / NumPeoplePerHH, which is the
count the coincidence model is evaluated at (paper Section 2.2.4).
"""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "results" / "summary" / "2026-09-03_switcher_profile.csv"
D = ROOT / "data" / "onsset_outputs"
YEAR = 2030
COLS = ["IsUrban", "Pop2020", "NumPeoplePerHH", f"MinimumOverall{YEAR}", "Pop2030"]

r0 = pd.read_csv(D / "2026-08_final_lcoe_R0.csv", usecols=COLS)
r1 = pd.read_csv(D / "2026-08_final_lcoe_R1_n20.csv", usecols=COLS)

tech0 = r0[f"MinimumOverall{YEAR}"].values
tech1 = r1[f"MinimumOverall{YEAR}"].values
sw = tech0 != tech1

n_hh = (r0["Pop2030"].values / r0["NumPeoplePerHH"].values)
n_sw = n_hh[sw]
urban_sw = int(r0["IsUrban"].values[sw].sum())

rows = [
    ("switchers_total", int(sw.sum())),
    ("switchers_urban", urban_sw),
    ("switchers_rural", int(sw.sum()) - urban_sw),
    ("switcher_median_hh_2030", float(np.median(n_sw))),
    ("switcher_mean_hh_2030", float(np.mean(n_sw))),
    ("switcher_share_hh_gt2", float((n_sw > 2).mean())),
    ("switcher_share_hh_le2", float((n_sw <= 2).mean())),
    ("switcher_count_hh_ge5", int((n_sw >= 5).sum())),
    ("switcher_share_hh_ge5", float((n_sw >= 5).mean())),
    ("switcher_pop2030", float(r0["Pop2030"].values[sw].sum())),
    ("switcher_pop2030_share_national", float(
        r0["Pop2030"].values[sw].sum() / r0["Pop2030"].values.sum())),
]
df = pd.DataFrame(rows, columns=["quantity", "value"])
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False)
for q, v in rows:
    print(f"  {q:<38} {v}")
print(f"\n  wrote {OUT.relative_to(ROOT)}")
