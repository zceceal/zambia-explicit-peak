"""
Generate realised P/E histogram on the calibrated spine.

Output: figures/fig_methods_pe_realised_distribution.png
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(ROOT / "peak_preprocessor"))

from pe_diversity import P_1_DEFAULT, P_INF_DEFAULT

PE_CSV  = REPO / "data" / "processed" / "zambia_settlements_PE.csv"
OUT_PNG = REPO / "figures" / "fig_methods_pe_realised_distribution.png"


def main():
    df = pd.read_csv(PE_CSV)

    # Population-weighted vs unweighted
    pe   = df["PE_ratio"].values
    pop  = df["Pop"].values
    is_urban = df["IsUrban"].values > 1

    # Separate urban/rural
    pe_urban  = pe[is_urban]
    pe_rural  = pe[~is_urban]
    pop_urban = pop[is_urban]
    pop_rural = pop[~is_urban]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # ── Left: settlement-count histogram ─────────────────────────────────────
    ax = axes[0]
    bins = np.linspace(P_INF_DEFAULT, P_1_DEFAULT, 40)
    ax.hist(pe_rural,  bins=bins, color="#4575b4", alpha=0.7, label=f"Rural  (n={len(pe_rural):,})")
    ax.hist(pe_urban,  bins=bins, color="#d73027", alpha=0.7, label=f"Urban  (n={len(pe_urban):,})")
    ax.axvline(P_INF_DEFAULT, color="k", ls="--", lw=1, label=f"$P_∞$={P_INF_DEFAULT}")
    ax.axvline(P_1_DEFAULT,   color="k", ls=":",  lw=1, label=f"$P_1$={P_1_DEFAULT}")
    ax.set_xlabel("P/E ratio", fontsize=11)
    ax.set_ylabel("Number of settlements", fontsize=11)
    ax.set_title("Realised P/E — settlement count\n(calibrated spine)", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    # ── Right: population-weighted histogram ──────────────────────────────────
    ax2 = axes[1]
    ax2.hist(pe_rural,  bins=bins, weights=pop_rural,  color="#4575b4", alpha=0.7,
             label=f"Rural  pop={pop_rural.sum()/1e6:.2f} M")
    ax2.hist(pe_urban,  bins=bins, weights=pop_urban,  color="#d73027", alpha=0.7,
             label=f"Urban  pop={pop_urban.sum()/1e6:.2f} M")

    # Key stats
    median_all = np.median(pe)
    mean_all   = np.mean(pe)
    ax2.axvline(median_all, color="navy", ls="-.", lw=1.2, label=f"Median all={median_all:.3f}")
    ax2.axvline(P_INF_DEFAULT, color="k", ls="--", lw=1, label=f"$P_∞$={P_INF_DEFAULT}")
    ax2.axvline(P_1_DEFAULT,   color="k", ls=":",  lw=1, label=f"$P_1$={P_1_DEFAULT}")
    ax2.set_xlabel("P/E ratio", fontsize=11)
    ax2.set_ylabel("Population", fontsize=11)
    ax2.set_title("Realised P/E — population-weighted\n(calibrated spine)", fontsize=10)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f} M"))
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle(
        "Zambia: realised after-diversity P/E distribution (Lorenzoni 2020, N_mid=20, β=0.317)\n"
        f"Range [{P_INF_DEFAULT}, {P_1_DEFAULT}] | "
        f"Mean={mean_all:.4f} | Median={median_all:.4f} | "
        f"Total settlements {len(pe):,}",
        fontsize=10, y=1.01
    )

    caption = (
        "  "
        "P/E = P_inf + (P_1 − P_inf) · N^(−β), Lorenzoni et al. (2020) anchors.  "
        f"Urban cells use HH_size=4.5, rural HH_size=5.3 (Egli 2023 Table S8).  "
        f"N_mid=20 central case; β = 0.9484 / ln(20) ≈ 0.317.  "
        f"Urban share (IsUrban=2): {is_urban.mean()*100:.1f}% of settlements, "
        f"{pop_urban.sum()/pop.sum()*100:.1f}% of population."
    )
    fig.text(0.5, -0.02, caption, ha="center", fontsize=7.5, color="dimgrey")

    fig.tight_layout()
    fig.savefig(str(OUT_PNG), dpi=180, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
