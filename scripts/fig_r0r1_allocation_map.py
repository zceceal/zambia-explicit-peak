#!/usr/bin/env python3
"""
fig_r0r1_allocation_map.py - side-by-side national maps of the least-cost technology
allocation under the two cases (paper Figure 2).

Kept separate from s13 because it reads the two arm outputs directly rather than the
summary tables. The figure is drawn at the width it is printed at (0.66 x textwidth
= 4.42 in); drawing it larger and letting LaTeX scale it down is what previously
rendered the panel titles at 6.2 pt.

    python scripts/fig_r0r1_allocation_map.py [run-label]
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

REPO = Path(__file__).resolve().parents[1]
OUTDIR = REPO / "data" / "onsset_outputs"
FIGDIR = REPO / "figures"
RUN = sys.argv[1] if len(sys.argv) > 1 else "2026-08_final_lcoe"
YEAR = 2030

plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix",
    "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5, "legend.fontsize": 8, "axes.linewidth": 0.7,
})

COL = f"MinimumOverall{YEAR}"
COLS = ["X_deg", "Y_deg", COL]
r0 = pd.read_csv(OUTDIR / f"{RUN}_R0.csv", usecols=COLS)
r1 = pd.read_csv(OUTDIR / f"{RUN}_R1_n20.csv", usecols=COLS)
assert len(r0) == len(r1) == 270_526

EXPECTED = {
    "R0": {"Grid2030": 32_058, "SA_PV2030": 236_843, "MG_PVHybrid2030": 1_625},
    "R1": {"Grid2030": 66_519, "SA_PV2030": 202_382, "MG_PVHybrid2030": 1_625},
}
for name, df in (("R0", r0), ("R1", r1)):
    got = df[COL].value_counts().to_dict()
    assert got == EXPECTED[name], f"GATE FAIL {name}: {got}"
print("Gate passed: both allocations match the Table 2 splits")

STYLE = {  # technology -> (colour, legend label, z-order, marker size)
    "SA_PV2030":       ("#E8A33D", "Stand-alone solar",   1, 0.045),
    "Grid2030":        ("#2C6FA6", "Grid extension",      2, 0.055),
    "MG_PVHybrid2030": ("#1B7F5E", "PV-hybrid mini-grid", 3, 1.10),
}

fig, axes = plt.subplots(1, 2, figsize=(4.42, 2.42), sharex=True, sharey=True)
for ax, df, title in zip(axes, (r0, r1),
                         ("(a) R0 — energy-only", "(b) R1 — explicit peak")):
    for tech, (colour, _, z, size) in STYLE.items():
        m = df[COL] == tech
        ax.scatter(df.loc[m, "X_deg"], df.loc[m, "Y_deg"], s=size, c=colour,
                   marker=".", linewidths=0, zorder=z, rasterized=True)
    n_grid = int((df[COL] == "Grid2030").sum())
    ax.set_title(f"{title}\n{n_grid:,} settlements to grid", fontsize=8, pad=3)
    ax.set_xlim(21.9, 33.8)
    ax.set_ylim(-18.2, -8.2)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude (°E)")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
axes[0].set_ylabel("Latitude (°)")

handles = [Line2D([], [], marker="o", ls="", ms=4, mfc=c, mec="none", label=lab)
           for c, lab, _, _ in STYLE.values()]
fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
           bbox_to_anchor=(0.5, -0.045))
fig.tight_layout(rect=(0, 0.055, 1, 1))
for ext in ("png", "pdf"):
    fig.savefig(FIGDIR / f"fig_results_r0_r1_allocation_map.{ext}", dpi=320,
                bbox_inches="tight")
print("Saved: fig_results_r0_r1_allocation_map.{png,pdf}")
