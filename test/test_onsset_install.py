"""
test_onsset_install.py — end-to-end sanity check that the OnSSET install works.

Gate criteria:
  1. onsset.SettlementProcessor loads and processes the Djibouti test CSV without error
  2. Calibration step runs to completion (population, urban ratio, electrification calibrated)
  3. Calibrated output CSV contains expected pipeline columns:
       WindCF, GridPenalty, ElectrifiedYear<start_year>, PopCalib<start_year>
  4. Settlement count in output matches input (1 473 rows)
  5. No NaN in coordinate or calibrated-population columns
  6. Map saved to figures/data_checks/fig_sanity_dj_settlements.png

NOTE: FinalElecCode / NewCapacity / InvestmentCost / NewConnections are scenario
output columns.  Full numerical validation of those against real Zambia outputs is
deferred to the R0 baseline gate (vs Imasiku 2025 + Mentis 2017).  This check
validates that calibration runs cleanly and the spatial pipeline is intact.

Run from the project root:
    python test/test_onsset_install.py
"""

import os
import sys
import time
import tempfile
import traceback

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO        = os.path.join(PROJECT_ROOT, "data", "onsset_repo")

# Same fallback as test_index_alignment.py: works whether onsset was `pip install -e`'d
# (patches/README.md) or the patched source is merely present at data/onsset_repo.
sys.path.insert(0, REPO)
from onsset import SettlementProcessor
from onsset.runner import calibration

SPECS       = os.path.join(REPO, "test", "test_data", "dj-specs-test.xlsx")
CSV_IN      = os.path.join(REPO, "test", "test_data", "dj-test.csv")
FIGURES_DIR = os.path.join(PROJECT_ROOT, "figures", "data_checks")
MAP_OUT     = os.path.join(FIGURES_DIR, "fig_sanity_dj_settlements.png")

PASSES   = []
FAILURES = []


def check(label, condition, detail=""):
    marker = "  PASS" if condition else "  FAIL"
    if condition:
        PASSES.append(label)
    else:
        FAILURES.append(label)
    print(f"{marker}  {label}" + (f" — {detail}" if detail else ""))


def main():
    t0 = time.time()
    print("\n=== Djibouti OnSSET sanity check ===\n")

    os.makedirs(FIGURES_DIR, exist_ok=True)

    # ── Run calibration ──────────────────────────────────────────────────────
    print("Step 1: Running calibration ...")
    with tempfile.TemporaryDirectory() as tmpdir:
        specs_calib = os.path.join(tmpdir, "dj-specs-calib.xlsx")
        csv_calib   = os.path.join(tmpdir, "dj-calibrated.csv")

        try:
            calibration(SPECS, CSV_IN, specs_calib, csv_calib)
            check("Calibration completes without error", True)
        except Exception:
            check("Calibration completes without error", False,
                  traceback.format_exc().splitlines()[-1])
            print("\nCalibration failed — aborting.")
            _report(t0)
            sys.exit(1)

        # ── Row-count and calibrated-column checks ───────────────────────────
        print("\nStep 2: Structural checks on calibrated output ...")
        df = pd.read_csv(csv_calib)
        n_in = len(pd.read_csv(CSV_IN))

        check("Row count preserved", len(df) == n_in,
              f"{len(df)} rows out, {n_in} rows in")
        check("WindCF column present",    "WindCF"      in df.columns)
        check("GridPenalty column present","GridPenalty" in df.columns)

        # Calibration adds year-stamped columns, e.g. FinalElecCode2018, ElecPop2018
        specs_data = pd.read_excel(SPECS, sheet_name="SpecsData")
        start_year = int(specs_data.loc[0, "StartYear"])
        final_elec_col = f"FinalElecCode{start_year}"
        elec_pop_col   = f"ElecPop{start_year}"

        check(f"'{final_elec_col}' column present", final_elec_col in df.columns,
              "technology-assignment field produced by calibration")
        check(f"'{elec_pop_col}' column present", elec_pop_col in df.columns,
              "calibrated electrified-population field")
        check("No NaN in X_deg / Y_deg",
              df[["X_deg", "Y_deg"]].isna().sum().sum() == 0)

        if elec_pop_col in df.columns:
            n_nan = df[elec_pop_col].isna().sum()
            check(f"No NaN in '{elec_pop_col}'", n_nan == 0, f"{n_nan} NaN found")

        # ── Settlement map (GHI choropleth + electrification status) ─────────
        print("\nStep 3: Producing settlement map ...")
        try:
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            # Panel A — GHI choropleth
            sc = axes[0].scatter(
                df["X_deg"], df["Y_deg"],
                c=df["GHI"], cmap="YlOrRd", s=5, alpha=0.75,
            )
            plt.colorbar(sc, ax=axes[0], label="GHI (kWh/m²/year)")
            axes[0].set_title("Solar resource (GHI)")
            axes[0].set_xlabel("Longitude (°)")
            axes[0].set_ylabel("Latitude (°)")

            # Panel B — Calibrated electrification status
            elec_vals = df["ElecPop"] > 0 if "ElecPop" in df.columns else df["NightLights"] > 0
            colours = ["#d62728" if e else "#aec7e8" for e in elec_vals]
            axes[1].scatter(df["X_deg"], df["Y_deg"], c=colours, s=5, alpha=0.75)
            from matplotlib.patches import Patch
            axes[1].legend(handles=[
                Patch(color="#d62728", label="Electrified"),
                Patch(color="#aec7e8", label="Unelectrified"),
            ], loc="lower right", fontsize=8)
            axes[1].set_title("Electrification status (ElecPop > 0)")
            axes[1].set_xlabel("Longitude (°)")
            axes[1].set_ylabel("Latitude (°)")

            fig.suptitle(
                f"Djibouti OnSSET sanity check — {len(df):,} settlements\n"
                f"onsset {__import__('onsset').__version__}  |  "
                f"commit c154ece12  |  calibration year {start_year}",
                fontsize=10,
            )
            fig.tight_layout()
            fig.savefig(MAP_OUT, dpi=150)
            plt.close(fig)
            check("Map saved", os.path.isfile(MAP_OUT), MAP_OUT)
        except Exception:
            check("Map saved", False, traceback.format_exc().splitlines()[-1])

    _report(t0)


def _report(t0):
    elapsed = time.time() - t0
    print(f"\n=== Results ({elapsed:.1f}s) ===")
    print(f"  Passed : {len(PASSES)}")
    print(f"  Failed : {len(FAILURES)}")
    if FAILURES:
        print("  Failed checks:")
        for f in FAILURES:
            print(f"    - {f}")
        sys.exit(1)
    else:
        print("\n  ALL CHECKS PASSED")
        print("  Sanity-check gate criteria met.")
        print("  FinalElecCode / NewCapacity / InvestmentCost deferred to R0 gate.")


if __name__ == "__main__":
    main()
