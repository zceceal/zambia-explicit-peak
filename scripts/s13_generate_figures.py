"""
s13_generate_figures.py — regenerate all figures from current model outputs.

All figures sourced from the GRID3 model (270,526-settlement spine).
Filenames are stable across runs.
Generation log appended to notes/2026-07-03_post_GSA_finalisation.md.

Figures generated:
  1. fig_methods_pe_realised_distribution.png  — GRID3 spine P/E distribution
  2. fig_methods_pe_empirical_validation.png   — model envelope + Wassie (corrected N)
  3. fig_methods_pe_coincidence_curve.png      — PE diversity curve (spine-independent)
  4. fig_methods_pe_nmid_sweep.png             — N_mid sweep ΔLCOE% from Stage-4
  5. fig_results_tech_split_R0_R1.png          — R0/R1 technology split (pop-weighted)
  6. fig_sensitivity_morris.png                — Morris μ*/σ chart (Stage-5 corrected)
  7. fig_headline_uncertainty.png             — LHS 5-95 band + full-spine anchors
  8. fig_results_switching_map.png            — SA_PV→Grid switching settlements vs MV network (Figure 4.5)
  8b. fig_results_switching_map_bw.png        — greyscale-safe variant

Script + input file + date: generate_all_figures.py | GRID3 Stage-4/5 outputs | 2026-07-05
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# Headline switch count of the current canonical run (s06, N_mid=20, 2030).
# Used as a gate so a figure can never be drawn from a stale arm output.
EXPECTED_SWITCHES = 34_461   # was 17,787 before the index-alignment fix

HERE    = Path(__file__).resolve().parent
REPO    = HERE.parent
FIGDIR  = REPO / "figures"
OUTDIR  = REPO / "data" / "onsset_outputs"
PROCDIR = REPO / "data" / "processed"
RAWDIR  = REPO / "data" / "raw"

sys.path.insert(0, str(REPO / "peak_preprocessor"))
from pe_diversity import (
    pe_from_n, compute_beta,
    P_1_DEFAULT, P_INF_DEFAULT, P_STEP_DEFAULT,
    SD_P_1, SD_P_INF, SD_P_STEP, N_MID_CENTRAL,
)

FIGDIR.mkdir(parents=True, exist_ok=True)

# ── Style constants ──────────────────────────────────────────────────────────
BLUE   = "#4575b4"
RED    = "#d73027"
ORANGE = "#f46d43"
GREEN  = "#1a9641"
PURPLE = "#762a83"
GREY   = "#999999"

log_entries = []


# ── Publication style (LaTeX-ready): Times-like STIX serif, no in-image titles/footers ──
PUBLICATION = True
import matplotlib as mpl
mpl.rcParams.update({
    "font.family": "STIXGeneral",
    "mathtext.fontset": "stix",
    "font.size": 10.5,
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "legend.fontsize": 9,
    "xtick.labelsize": 9.5,
    "ytick.labelsize": 9.5,
    "axes.linewidth": 0.8,
    "savefig.bbox": "tight",
})

def save_fig(fig, name: str, dpi: int = 300):
    path = FIGDIR / name
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight")
    if PUBLICATION and not name.endswith("_bw.png"):
        pdf = str(path).rsplit(".", 1)[0] + ".pdf"
        try:
            fig.savefig(pdf, bbox_inches="tight")   # vector for LaTeX
        except Exception as e:
            print(f"  (pdf skipped for {name}: {e})")
    plt.close(fig)
    log_entries.append(f"  {name}  ← generate_all_figures.py | {path.name} | 2026-07-05 (publication style)")
    print(f"  Saved: {name}")


def fig0_workflow():
    """Figure 3.1 — framework architecture, column-flowchart convention
    (style follows Peña Balderrama et al. 2020, Fig. 4: stage headers,
    vertical chains, straight orthogonal connectors)."""
    import matplotlib.patches as mpatches
    fig, ax = plt.subplots(figsize=(10.5, 6.2)); ax.axis("off")
    REUSED = "#c6d4e8"; BUILT = "#f6c28b"; EDGE = "#444444"; HDR = "#3d4a5d"

    def box(x, y, w, h, text, colour, fs=8.8, bold=False, ec=EDGE, lw=1.0):
        ax.add_patch(mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008",
                     fc=colour, ec=ec, lw=lw))
        ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs,
                fontweight="bold" if bold else "normal")

    def header(x, w, text):
        ax.add_patch(mpatches.FancyBboxPatch((x, 0.925), w, 0.058,
                     boxstyle="round,pad=0.006", fc=HDR, ec=HDR))
        ax.text(x + w/2, 0.954, text, ha="center", va="center",
                fontsize=9.5, color="white", fontweight="bold")

    def harrow(x0, x1, y):
        ax.annotate("", xy=(x1, y), xytext=(x0, y),
                    arrowprops=dict(arrowstyle="-|>", color=EDGE, lw=1.2))

    def varrow(x, y0, y1):
        ax.annotate("", xy=(x, y1), xytext=(x, y0),
                    arrowprops=dict(arrowstyle="-|>", color=EDGE, lw=1.2))

    # ── Column geometry ─────────────────────────────────────────────────
    c1x, c1w = 0.015, 0.225      # shared inputs
    c2x, c2w = 0.290, 0.240      # demand representation
    c3x, c3w = 0.580, 0.185      # least-cost solve
    c4x, c4w = 0.815, 0.175      # controlled contrast

    header(c1x, c1w, "1.  Shared inputs")
    header(c2x, c2w, "2.  Demand representation")
    header(c3x, c3w, "3.  Least-cost solve")
    header(c4x, c4w, "4.  Controlled contrast")

    # ── Column 1: shared-input container with four data boxes ───────────
    ax.add_patch(mpatches.FancyBboxPatch((c1x, 0.075), c1w, 0.815,
                 boxstyle="round,pad=0.006", fc="none", ec="#888888",
                 lw=0.9, linestyle="--"))
    box(c1x+0.012, 0.715, c1w-0.024, 0.145,
        "Settlements & population\nGRID3 extents + WorldPop\n(270,526 settlements)", REUSED)
    box(c1x+0.012, 0.535, c1w-0.024, 0.145,
        "Grid infrastructure\nZESCO MV network,\nNEP planned extensions", REUSED)
    box(c1x+0.012, 0.355, c1w-0.024, 0.145,
        "Resources & access\nsolar atlas, roads, hydro,\nNEAS-2023 calibration", REUSED)
    box(c1x+0.012, 0.175, c1w-0.024, 0.145,
        "Techno-economic\nparameters\n(GEP/OnSSET + Zambia)", REUSED)
    ax.text(c1x + c1w/2, 0.115, "identical in both\nconfigurations",
            ha="center", va="center", fontsize=8, style="italic", color="#555555")

    # ── Column 2: demand assignment forking into the two arms ───────────
    box(c2x, 0.660, c2w, 0.200,
        "Demand assignment\nMTF tiers: urban Tier 5, rural Tier 3\n"
        "→ annual kWh per household", REUSED)
    box(c2x + 0.048, 0.390, c2w - 0.048, 0.185,
        "R0  —  energy-only\nuniform peak factor\n(unmodified OnSSET)", REUSED)
    box(c2x, 0.130, c2w, 0.185,
        r"R1  —  explicit peak" "\n" r"demand pre-processor:" "\n" r"coincidence curve $\rho(N)$" "\n" r"(built)", BUILT)

    # ── Column 3: engine (spans both arm levels; arrows meet its left edge) ──
    box(c3x, 0.170, c3w, 0.500,
        "OnSSET least-cost\nengine (unmodified;\nMentis et al. 2017)\n\n"
        "7-technology LCOE\ncomparison per\nsettlement, 2030/2035\n\nrun once per arm", REUSED)

    # ── Column 4: outputs and treatment effect ───────────────────────────
    box(c4x, 0.520, c4w, 0.240,
        "Outputs (per arm)\ntechnology allocation,\nLCOE, investment,\ncapacity", REUSED)
    box(c4x, 0.200, c4w, 0.210,
        "R1 − R0\n= effect of explicit\npeak representation", REUSED, bold=False)

    # ── Connectors (straight / orthogonal only) ──────────────────────────
    harrow(c1x + c1w + 0.008, c2x - 0.006, 0.760)          # inputs -> demand assignment
    varrow(c2x + 0.048 + (c2w - 0.048)/2, 0.660, 0.578)    # assignment -> R0
    varrow(c2x + 0.022, 0.660, 0.318)                      # assignment -> R1 (left gutter, clear of R0)
    harrow(c2x + c2w + 0.008, c3x - 0.006, 0.483)          # R0 -> engine
    harrow(c2x + c2w + 0.008, c3x - 0.006, 0.222)          # R1 -> engine
    harrow(c3x + c3w + 0.008, c4x - 0.006, 0.640)          # engine -> outputs
    varrow(c4x + c4w/2, 0.520, 0.413)                      # outputs -> contrast
    # shared inputs -> engine, routed orthogonally beneath the arm boxes
    ax.plot([c1x + c1w/2, c1x + c1w/2], [0.075, 0.038], color=EDGE, lw=1.2)
    ax.plot([c1x + c1w/2, c3x + c3w/2], [0.038, 0.038], color=EDGE, lw=1.2)
    varrow(c3x + c3w/2, 0.038, 0.166)

    ax.legend(handles=[mpatches.Patch(fc=REUSED, ec=EDGE, label="Established component (reused)"),
                       mpatches.Patch(fc=BUILT,  ec=EDGE, label="Component built for this study")],
              loc="lower right", fontsize=8.5, frameon=True, edgecolor="#bbbbbb")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    save_fig(fig, "fig_methods_onsset_workflow.png")


# ── Figure 3.2 — coincidence curve (spine-independent) ───────────────────────
def fig_curve():
    N = np.logspace(0, np.log10(3000), 300)
    lo = pe_from_n(N, N_mid=20, P_1=P_1_DEFAULT-2*SD_P_1, P_inf=max(1.0, P_INF_DEFAULT-2*SD_P_INF), P_step=P_STEP_DEFAULT-2*SD_P_STEP)
    hi = pe_from_n(N, N_mid=20, P_1=P_1_DEFAULT+2*SD_P_1, P_inf=P_INF_DEFAULT+2*SD_P_INF, P_step=P_STEP_DEFAULT+2*SD_P_STEP)
    # Drawn at the printed width (0.98 x column width = 3.08 in) so LaTeX applies no
    # downscaling: at 6.3 in the 0.49x shrink rendered the legend at 4.2 pt.
    fig, ax = plt.subplots(figsize=(3.08, 2.45))
    ax.fill_between(N, lo, hi, alpha=0.15, color=BLUE, label=r"Model envelope, $\pm$2 SD")
    ax.plot(N, pe_from_n(N, N_mid=10), color=BLUE, lw=1.0, ls="--", label=r"$N_\mathrm{mid}$ = 10")
    ax.plot(N, pe_from_n(N, N_mid=20), color=BLUE, lw=1.6,          label=r"$N_\mathrm{mid}$ = 20 (central)")
    ax.plot(N, pe_from_n(N, N_mid=50), color=BLUE, lw=1.0, ls=":",  label=r"$N_\mathrm{mid}$ = 50")
    ax.axhline(P_INF_DEFAULT, color="k", ls="--", lw=0.7, alpha=0.6)
    ax.axhline(P_1_DEFAULT,   color="k", ls=":",  lw=0.7, alpha=0.6)
    ax.set_xscale("log")
    ax.set_xlabel("Number of connected households, $N$", fontsize=8.5)
    ax.set_ylabel(r"Peak-to-mean ratio $\rho$", fontsize=8.5)
    ax.tick_params(labelsize=7.5)
    ax.set_ylim(1.0, 4.6)
    ax.grid(ls="--", alpha=0.35)
    ax.legend(frameon=False, loc="upper right", fontsize=7.5)
    fig.tight_layout()
    save_fig(fig, "fig_methods_pe_coincidence_curve.png")


# ── Figure 3.3 — empirical validation (three measured anchors) ───────────────
def fig_validation():
    N = np.logspace(0, np.log10(3e6), 400)
    lo = pe_from_n(N, N_mid=20, P_1=P_1_DEFAULT-SD_P_1, P_inf=max(1.0, P_INF_DEFAULT-SD_P_INF), P_step=P_STEP_DEFAULT-SD_P_STEP)
    hi = pe_from_n(N, N_mid=20, P_1=P_1_DEFAULT+SD_P_1, P_inf=P_INF_DEFAULT+SD_P_INF, P_step=P_STEP_DEFAULT+SD_P_STEP)
    fig, ax = plt.subplots(figsize=(6.3, 4.2))
    ax.fill_between(N, lo, hi, alpha=0.15, color=BLUE, label=r"Model envelope, $\pm$1 SD")
    ax.plot(N, pe_from_n(N, N_mid=20), color=BLUE, lw=2.0,          label=r"Central ($N_\mathrm{mid}$ = 20)")
    ax.plot(N, pe_from_n(N, N_mid=10), color=BLUE, lw=1.2, ls="--", label=r"$N_\mathrm{mid}$ = 10")
    ax.plot(N, pe_from_n(N, N_mid=50), color=BLUE, lw=1.2, ls=":",  label=r"$N_\mathrm{mid}$ = 50")
    ax.scatter([450], [1.80], color=RED, marker="^", s=60, zorder=5,
               label=r"Tum mini-grid, $N$ = 450 (residential): 1.80")
    ax.scatter([443], [2.88], color=RED, marker="s", s=55, zorder=5,
               label=r"Omorate mini-grid, $N$ = 443 (incl. productive): 2.88")
    ax.scatter([1.3e6], [1.67], color=GREEN, marker="o", s=65, zorder=5,
               label=r"Zambia residential system 2020, $N \approx 1.3$M: 1.67")
    ax.axhline(P_INF_DEFAULT, color="k", ls="--", lw=0.8, alpha=0.5)
    ax.axhline(P_1_DEFAULT,   color="k", ls=":",  lw=0.8, alpha=0.5)
    ax.set_xscale("log")
    ax.set_xlabel("Number of connected households, $N$")
    ax.set_ylabel(r"Peak-to-mean ratio $\rho$")
    ax.set_ylim(1.0, 4.6)
    ax.grid(ls="--", alpha=0.35)
    ax.legend(frameon=False, loc="upper right", fontsize=8.2)
    fig.tight_layout()
    save_fig(fig, "fig_methods_pe_empirical_validation.png")


# ── Figure 3.4 — realised P/E distribution on the GRID3 spine ────────────────
def fig_distribution():
    spine_path = PROCDIR / "zambia_grid3_spine_pe_n20.csv"
    df = pd.read_csv(spine_path, usecols=["PE_ratio", "Pop", "IsUrban"])
    pe, pop, is_u = df["PE_ratio"].values, df["Pop"].values, (df["IsUrban"] > 1).values
    bins = np.linspace(P_INF_DEFAULT - 0.02, P_1_DEFAULT + 0.02, 42)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.3, 3.0))
    for ax, w in [(ax1, None), (ax2, pop)]:
        ax.hist(pe[~is_u], bins=bins, weights=None if w is None else w[~is_u], color=BLUE, alpha=0.75,
                label=f"Rural (n = {np.sum(~is_u):,})" if w is None else f"Rural ({pop[~is_u].sum()/1e6:.2f} M)")
        ax.hist(pe[is_u], bins=bins, weights=None if w is None else w[is_u], color=RED, alpha=0.75,
                label=f"Urban (n = {np.sum(is_u):,})" if w is None else f"Urban ({pop[is_u].sum()/1e6:.2f} M)")
        ax.axvline(P_INF_DEFAULT, color="k", ls="--", lw=0.8)
        ax.axvline(P_1_DEFAULT,   color="k", ls=":",  lw=0.8)
        ax.set_xlabel(r"Peak-to-mean ratio $\rho$")
        ax.legend(frameon=False, fontsize=8)
        ax.grid(axis="y", ls="--", alpha=0.35)
    ax1.set_ylabel("Number of settlements")
    ax2.set_ylabel("Population (millions)")
    ax1.set_title("(a) Settlement count", fontsize=10)
    ax2.set_title("(b) Population-weighted", fontsize=10)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:g}"))
    fig.tight_layout()
    save_fig(fig, "fig_methods_pe_realised_distribution.png")


# ── Figure 4.1 — technology split R0 vs R1 (Pop2030-weighted) ────────────────
def fig_techsplit():
    use = ["Pop2030", "MinimumOverall2030"]
    r0 = pd.read_csv(OUTDIR / "2026-08_final_lcoe_R0.csv", usecols=use)
    r1 = pd.read_csv(OUTDIR / "2026-08_final_lcoe_R1_n20.csv", usecols=use)
    tot = r0["Pop2030"].sum()
    techs = [("Grid2030", "Grid extension", BLUE), ("SA_PV2030", "Stand-alone PV", ORANGE),
             ("MG_PVHybrid2030", "PV-hybrid mini-grid", GREEN)]
    fig, ax = plt.subplots(figsize=(6.3, 3.6))
    x = np.arange(len(techs)); wdt = 0.36
    R0_COL, R1_COL = "#b8bfc9", BLUE            # colour by configuration -> legend matches exactly
    for off, df, col in [(-wdt/2, r0, R0_COL), (wdt/2, r1, R1_COL)]:
        shares = [df.loc[df.MinimumOverall2030 == t, "Pop2030"].sum() / tot * 100 for t, _, _ in techs]
        bars = ax.bar(x + off, shares, wdt, color=col, edgecolor="k", linewidth=0.6)
        for b, v in zip(bars, shares):
            ax.text(b.get_x() + b.get_width()/2, v + 0.8, f"{v:.1f}%", ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels([n for _, n, _ in techs])
    ax.set_ylabel("Share of 2030 population (%)")
    ax.set_ylim(0, 70)
    handles = [mpatches.Patch(fc=R0_COL, ec="k", label="R0 (energy-only)"),
               mpatches.Patch(fc=R1_COL, ec="k", label="R1 (explicit peak)")]
    ax.legend(handles=handles, frameon=False)
    ax.grid(axis="y", ls="--", alpha=0.35)
    fig.tight_layout()
    save_fig(fig, "fig_results_tech_split_R0_R1.png")


RUN = "2026-08_final_lcoe"


def _arm_pair(r0_name, r1_name, year=2030):
    """Energy-weighted DeltaLCOE% and SA_PV->grid switch count for one arm pair.

    Read from the arm CSVs rather than hard-coded, so a figure can never carry a
    number from a superseded run. Returns None if either output is missing.
    """
    p0, p1 = OUTDIR / r0_name, OUTDIR / r1_name
    if not (p0.exists() and p1.exists()):
        return None
    lc, ec, fc = f"MinimumOverallLCOE{year}", f"EnergyPerSettlement{year}", f"FinalElecCode{year}"
    d0 = pd.read_csv(p0, usecols=[lc, ec, fc])
    d1 = pd.read_csv(p1, usecols=[lc, ec, fc])
    c0 = (d0[lc] * d0[ec]).sum()
    c1 = (d1[lc] * d1[ec]).sum()
    return (c1 - c0) / c0 * 100.0, int(((d0[fc] == 3) & (d1[fc] == 1)).sum())


def nmid_series():
    """(N_mid list, Tier-3 series, Tier-2 series or None) computed from the arm outputs."""
    nm = [10, 20, 50]
    t3 = [_arm_pair(f"{RUN}_R0.csv", f"{RUN}_R1_n{n}.csv") for n in nm]
    t2 = [_arm_pair(f"{RUN}_R0_ruralT2.csv", f"{RUN}_R1_ruralT2_n{n}.csv") for n in nm]
    if any(v is None for v in t3):
        return nm, None, None
    return nm, ([v[0] for v in t3], [v[1] for v in t3]), \
           (([v[0] for v in t2], [v[1] for v in t2]) if all(v is not None for v in t2) else None)


# ── Figure 4.2 — N_mid sweep x demand tier (verified full-country solves) ────
def fig_nmid_sweep():
    nm, t3, t2 = nmid_series()
    if t3 is None:
        print("  SKIP fig_nmid_sweep: Tier-3 arm outputs not found"); return
    t3_d, t3_s = t3
    if t2 is None:
        print("  NOTE fig_nmid_sweep: Tier-2 arms (s07) not found - plotting Tier 3 only")
        t2_d = t2_s = None
    else:
        t2_d, t2_s = t2
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.3, 3.1))
    ax1.plot(nm, t3_d, "o-",  color=BLUE,   label="Rural Tier 3 (central)")
    if t2_d: ax1.plot(nm, t2_d, "s--", color=ORANGE, label="Rural Tier 2 (sensitivity)")
    for ys in [y for y in (t3_d, t2_d) if y]:
        for xv, yv in zip(nm, ys):
            ax1.annotate(f"+{yv:.1f}%", (xv, yv), textcoords="offset points", xytext=(2, 6), fontsize=8)
    ax1.set_xlabel(r"$N_\mathrm{mid}$ (households)")
    ax1.set_ylabel(r"$\Delta$LCOE (%)")
    ax1.set_title("(a) Lifetime-cost change", fontsize=10)
    _all = list(t3_d) + list(t2_d or [])
    _pad = max(2.0, 0.12 * (max(_all) - min(_all)))
    ax1.set_xticks(nm); ax1.set_ylim(min(_all) - _pad, max(_all) + _pad)
    ax1.grid(ls="--", alpha=0.35)
    ax1.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax2.semilogy(nm, t3_s, "o-",  color=BLUE,   label="Rural Tier 3")
    if t2_s: ax2.semilogy(nm, t2_s, "s--", color=ORANGE, label="Rural Tier 2")
    for xv, yv in zip(nm, t3_s):
        ax2.annotate(f"{yv:,}", (xv, yv), textcoords="offset points", xytext=(3, -11), fontsize=8)
    for xv, yv in zip(nm, t2_s or []):
        ax2.annotate(f"{yv:,}", (xv, yv), textcoords="offset points", xytext=(3, 5), fontsize=8)
    ax2.set_xlabel(r"$N_\mathrm{mid}$ (households)")
    ax2.set_ylabel(r"Settlements switching SA PV $\rightarrow$ grid")
    ax2.set_title("(b) Technology reallocation", fontsize=10)
    ax2.set_xticks(nm); ax2.set_xlim(5, 60)
    ax2.grid(ls="--", alpha=0.35, which="both")
    ax2.legend(frameon=False, fontsize=8.5, loc="center left")
    fig.tight_layout()
    save_fig(fig, "fig_methods_pe_nmid_sweep.png")


# ── Figure 4.3 — Morris screen (ranking only) ────────────────────────────────
def fig_morris():
    bc = pd.read_csv(OUTDIR / "2026-08_final_morris_delta_lcoe_corrected.csv").sort_values("mu_star")
    sw = pd.read_csv(OUTDIR / "2026-08_final_morris_switch_count.csv").sort_values("mu_star")
    names = {"Rural_tier": "Rural demand tier", "MaxGridDist_km": "Max. grid distance",
             "Discount_rate": "Discount rate", "N_mid": r"$N_\mathrm{mid}$",
             "SA_PV_capex_mult": "SA PV/battery capex", "Diesel_price_USDl": "Diesel price"}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.6, 3.2))
    for ax, df, colour, xlab, fmt in [
            (ax1, bc, BLUE,   r"$\mu^{*}$ (percentage points)", lambda v: f"{v:.1f}"),
            (ax2, sw, ORANGE, r"$\mu^{*}$ (settlements)",       lambda v: f"{v:,.0f}")]:
        y = np.arange(len(df))
        ax.barh(y, df["mu_star"], color=colour, alpha=0.8, height=0.6)
        ax.errorbar(df["mu_star"], y, xerr=df["sigma"], fmt="none", ecolor="k", elinewidth=0.9, capsize=2.5)
        for i, (val, sig) in enumerate(zip(df["mu_star"], df["sigma"])):
            ax.text(val + sig + df["mu_star"].max()*0.04, i, fmt(val), va="center", fontsize=8)
        ax.set_yticks(y)
        ax.set_yticklabels([names.get(p, p) for p in df["parameter"]], fontsize=8.5)
        ax.set_xlabel(xlab)
        ax.grid(axis="x", ls="--", alpha=0.35)
        ax.set_xlim(0, (df["mu_star"] + df["sigma"]).max() * 1.32)
    ax1.set_title(r"(a) $\Delta$LCOE", fontsize=10)
    ax2.set_title("(b) Switch count", fontsize=10)
    fig.tight_layout()
    save_fig(fig, "fig_sensitivity_morris.png")


# ── Figure 4.4 — LHS uncertainty band + full-country anchors ─────────────────
def fig_uncertainty():
    lhs = pd.read_csv(OUTDIR / "2026-08_final_lhs_uncertainty.csv")
    corr = lhs["delta_lcoe_pct_corrected"].values
    p5, p50, p95 = np.percentile(corr, [5, 50, 95])
    fig, ax = plt.subplots(figsize=(6.3, 4.0))
    ax.hist(corr, bins=35, color=BLUE, alpha=0.35, density=True,
            label="LHS sample (200 draws, anchored)")
    ax.axvline(p5,  color=BLUE, ls="--", lw=1.4, label=f"Indicative 5th percentile: +{p5:.1f}%")
    ax.axvline(p50, color=BLUE, ls="-",  lw=1.8, label=f"Median (anchored): +{p50:.1f}%")
    ax.axvline(p95, color=BLUE, ls="--", lw=1.4, label=f"Indicative 95th percentile: +{p95:.1f}%")
    fs_path = OUTDIR / "2026-08_final_lhs_fullspine_validation.csv"
    if fs_path.exists():
        fs = pd.read_csv(fs_path)
        for _, row in fs.iterrows():
            ax.scatter([row["fullspine_delta"]], [0.0015], marker="D", s=45, color="k", zorder=6,
                       label=f"Full-country re-solve, {row['label']} sample: "
                             f"+{row['fullspine_delta']:.1f}%")
    else:
        print("  NOTE fig_uncertainty: full-spine validation (s09) not found - anchors omitted")
    nm, t3, t2 = nmid_series()
    if t3 is not None:
        t3_d = t3[0]
        for v, lab in [(min(t3_d), None),
                       (t3_d[1], f"Full-country Tier-3 solves: +{min(t3_d):.1f}% to +{max(t3_d):.1f}%"),
                       (max(t3_d), None)]:
            ax.axvline(v, color=RED, ls=":", lw=1.1, alpha=0.8, label=lab)
    if t2 is not None:
        ax.axvline(t2[0][1], color=ORANGE, ls="-.", lw=1.3, alpha=0.9,
                   label=f"Full-country Tier-2 central: +{t2[0][1]:.1f}%")
    ax.set_xlabel(r"Energy-weighted $\Delta$LCOE (%), R1 relative to R0")
    ax.set_ylabel("Density")
    ax.set_xlim(max(0, corr.min() - 5), corr.max() + 12)
    ax.grid(ls="--", alpha=0.3)
    ax.legend(frameon=False, fontsize=7.8, loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2)
    save_fig(fig, "fig_headline_uncertainty.png")


# ── Figure 4.5 — Switching-settlement map (SA_PV→Grid at 2030, R0 vs R1 n20) ───
def _read_shp_polylines(path):
    """Minimal ESRI shapefile reader: returns list of (n,2) arrays for PolyLine
    records (shape types 3/13/23). Pure Python + numpy; no GDAL dependency."""
    import struct
    data = Path(path).read_bytes()
    idx, n = 100, len(data)          # 100-byte main header
    lines = []
    while idx + 8 <= n:
        _, clen = struct.unpack(">ii", data[idx:idx + 8])
        idx += 8
        content = data[idx:idx + clen * 2]
        idx += clen * 2
        if len(content) < 4:
            continue
        shptype = struct.unpack("<i", content[:4])[0]
        if shptype in (3, 13, 23):
            numparts, numpoints = struct.unpack("<ii", content[36:44])
            parts = struct.unpack(f"<{numparts}i", content[44:44 + 4 * numparts])
            pts = np.frombuffer(content, dtype="<f8", count=numpoints * 2,
                                offset=44 + 4 * numparts).reshape(-1, 2)
            for i, p in enumerate(parts):
                q = parts[i + 1] if i + 1 < numparts else numpoints
                if q - p >= 2:
                    lines.append(pts[p:q])
    return lines


def _utm35s_arc1950_to_wgs84(easting, northing):
    """Inverse transverse Mercator on Clarke 1880 (Arc 1950 / UTM 35S), then a
    3-parameter geocentric shift Arc 1950 -> WGS84 (EPSG mean for Zambia:
    dX=-143, dY=-90, dZ=-294 m; residual << 100 m, invisible at national scale)."""
    a, f = 6378249.145, 1.0 / 293.465          # Clarke 1880 (Arc)
    e2 = 2 * f - f * f
    ep2 = e2 / (1 - e2)
    k0, E0, N0, lon0 = 0.9996, 500000.0, 10000000.0, np.radians(27.0)
    M = (np.asarray(northing, float) - N0) / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - np.sqrt(1 - e2)) / (1 + np.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * np.sin(2 * mu)
               + (21 * e1**2 / 16 - 55 * e1**4 / 32) * np.sin(4 * mu)
               + (151 * e1**3 / 96) * np.sin(6 * mu)
               + (1097 * e1**4 / 512) * np.sin(8 * mu))
    sin1, cos1, tan1 = np.sin(phi1), np.cos(phi1), np.tan(phi1)
    C1 = ep2 * cos1**2
    T1 = tan1**2
    N1 = a / np.sqrt(1 - e2 * sin1**2)
    R1 = a * (1 - e2) / (1 - e2 * sin1**2)**1.5
    D = (np.asarray(easting, float) - E0) / (N1 * k0)
    lat = phi1 - (N1 * tan1 / R1) * (
        D**2 / 2
        - (5 + 3 * T1 + 10 * C1 - 4 * C1**2 - 9 * ep2) * D**4 / 24
        + (61 + 90 * T1 + 298 * C1 + 45 * T1**2 - 252 * ep2 - 3 * C1**2) * D**6 / 720)
    lon = lon0 + (D - (1 + 2 * T1 + C1) * D**3 / 6
                  + (5 - 2 * C1 + 28 * T1 - 3 * C1**2 + 8 * ep2 + 24 * T1**2) * D**5 / 120) / cos1
    # geodetic (Arc 1950) -> geocentric XYZ -> +shift -> geodetic (WGS84)
    Nrad = a / np.sqrt(1 - e2 * np.sin(lat)**2)
    X = Nrad * np.cos(lat) * np.cos(lon)
    Y = Nrad * np.cos(lat) * np.sin(lon)
    Z = Nrad * (1 - e2) * np.sin(lat)
    X, Y, Z = X - 143.0, Y - 90.0, Z - 294.0
    aw, fw = 6378137.0, 1.0 / 298.257223563    # WGS84
    e2w = 2 * fw - fw * fw
    lon_w = np.arctan2(Y, X)
    p = np.hypot(X, Y)
    lat_w = np.arctan2(Z, p * (1 - e2w))
    for _ in range(5):                          # fixed-point iteration converges fast
        Nw = aw / np.sqrt(1 - e2w * np.sin(lat_w)**2)
        h = p / np.cos(lat_w) - Nw
        lat_w = np.arctan2(Z, p * (1 - e2w * Nw / (Nw + h)))
    return np.degrees(lon_w), np.degrees(lat_w)


def fig_switching_map():
    from matplotlib.collections import LineCollection

    r0_path  = OUTDIR / "2026-08_final_lcoe_R0.csv"
    r1_path  = OUTDIR / "2026-08_final_lcoe_R1_n20.csv"
    mv_path  = (RAWDIR / "zambia" / "grid" / "mv_distribution_2023"
                / "distribution_medium_voltage_overhead_line_network"
                / "Distribution_Medium_Voltage_Overhead_Line_Network.shp")
    adm0_path = RAWDIR / "zambia" / "admin" / "geoboundaries" / "geoBoundaries-ZMB-ADM0.geojson"

    if not (r0_path.exists() and r1_path.exists() and mv_path.exists()):
        print("  SKIP fig_switching_map: required input files not found")
        return

    r0 = pd.read_csv(r0_path)
    r1 = pd.read_csv(r1_path)

    # ── Gate: switcher count ─────────────────────────────────────────────
    sw_mask = (r0["MinimumOverall2030"] == "SA_PV2030") & (r1["MinimumOverall2030"] == "Grid2030")
    switchers = r0[sw_mask]
    n_sw = len(switchers)
    if n_sw != EXPECTED_SWITCHES:
        print(f"  GATE FAIL: switcher count = {n_sw:,}, expected {EXPECTED_SWITCHES:,}. Stopping.")
        return
    print(f"  Gate passed: {n_sw:,} switching settlements (SA_PV→Grid at 2030)")

    # ── Coordinate columns ───────────────────────────────────────────────
    x_col, y_col = "X_deg", "Y_deg"
    all_x = r0[x_col].values
    all_y = r0[y_col].values
    sw_x  = switchers[x_col].values
    sw_y  = switchers[y_col].values
    print(f"  Coordinate columns: {x_col} / {y_col}")

    # ── Bbox validation ──────────────────────────────────────────────────
    bbox_x = (21.9, 33.8)
    bbox_y = (-18.2, -8.2)
    oob = r0[(r0[x_col] < bbox_x[0]) | (r0[x_col] > bbox_x[1]) |
              (r0[y_col] < bbox_y[0]) | (r0[y_col] > bbox_y[1])]
    print(f"  Points outside Zambia bbox: {len(oob)} / {len(r0)}")

    # ── Verify switchers are a subset of the background cloud ────────────
    sw_ids  = set(switchers.index)
    all_ids = set(r0.index)
    assert sw_ids.issubset(all_ids), "Switcher indices not a subset of all settlements"

    # ── MV lines (pure-Python SHP read + in-script reprojection) ─────────
    mv_lines_utm = _read_shp_polylines(mv_path)
    print(f"  MV layer CRS (original, per .prj): Arc 1950 / UTM zone 35S")
    all_pts = np.concatenate(mv_lines_utm)
    lon, lat = _utm35s_arc1950_to_wgs84(all_pts[:, 0], all_pts[:, 1])
    pts_ll = np.column_stack([lon, lat])
    offsets = np.cumsum([len(s) for s in mv_lines_utm])[:-1]
    mv_lines = np.split(pts_ll, offsets)
    print(f"  MV layer reprojected in-script to WGS84 (EPSG:4326)")
    print(f"  MV polylines plotted: {len(mv_lines):,}")

    # ── Admin boundary (GeoJSON, pure json) ──────────────────────────────
    import json
    adm0_rings = []
    if adm0_path.exists():
        gj = json.loads(adm0_path.read_text())
        for feat in gj["features"]:
            geom = feat["geometry"]
            polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            for poly in polys:
                for ring in poly:
                    adm0_rings.append(np.asarray(ring, float))
        print(f"  ADM0 boundary: {len(adm0_rings)} rings (WGS84 GeoJSON)")

    # ── Build the map (colour + B&W); no in-image title/footer (LaTeX caption) ──
    for variant in ("colour", "bw"):
        if variant == "colour":
            bg_col  = "#888888"
            mv_col  = "#1a1a1a"
            sw_col  = RED       # "#d73027"
            bd_col  = "#444444"
            sw_mrkr = "o"
            figname = "fig_results_switching_map.png"
        else:
            bg_col  = "#cccccc"
            mv_col  = "#555555"
            sw_col  = "#000000"
            bd_col  = "#222222"
            sw_mrkr = "s"       # filled square — distinguishable from circle background dots
            figname = "fig_results_switching_map_bw.png"

        fig, ax = plt.subplots(figsize=(10, 9))

        # Layer 1 — all settlements (faint background context)
        ax.scatter(all_x, all_y, s=0.4, c=bg_col, alpha=0.12, linewidths=0,
                   rasterized=True, zorder=1)

        # Layer 2 — ZESCO MV network
        ax.add_collection(LineCollection(mv_lines, colors=mv_col, linewidths=0.35,
                                         zorder=2, rasterized=True))

        # Layer 3 — switching settlements
        ax.scatter(sw_x, sw_y, s=4, c=sw_col, alpha=0.75, marker=sw_mrkr,
                   linewidths=0, rasterized=True, zorder=3)

        # Admin boundary
        if adm0_rings:
            ax.add_collection(LineCollection(adm0_rings, colors=bd_col,
                                             linewidths=0.9, zorder=4))

        ax.set_xlabel("Longitude (°E)", fontsize=10)
        ax.set_ylabel("Latitude (°)", fontsize=10)

        # Legend — manual patches so counts appear
        legend_handles = [
            mpatches.Patch(color=bg_col, alpha=0.6,
                           label="All settlements (n = 270,526)"),
            Line2D([0], [0], color=mv_col, linewidth=1.2,
                   label=f"ZESCO MV network ({len(mv_lines):,} lines)"),
            mpatches.Patch(color=sw_col,
                           label=f"Switching settlements (n = {len(switchers):,})\n(stand-alone PV → grid, 2030)"),
        ]
        ax.legend(handles=legend_handles, loc="lower left", fontsize=9,
                  framealpha=0.85, edgecolor="#bbbbbb")

        ax.grid(False)
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout()
        save_fig(fig, figname)

    print(f"  Switcher coordinate subset check: PASSED")
    print(f"  Bounding box used: lon {bbox_x}, lat {bbox_y}")


def main():
    t0 = time.time()
    print("Publication figure build (STIX serif, no in-image titles/footers, PNG 300 dpi + PDF vector)")
    fig0_workflow()
    fig_curve()
    fig_validation()
    fig_distribution()
    fig_techsplit()
    fig_nmid_sweep()
    fig_morris()
    fig_uncertainty()
    fig_switching_map()
    print(f"Done in {time.time()-t0:.1f}s")
    for e in log_entries:
        print(e)


if __name__ == "__main__":
    main()
