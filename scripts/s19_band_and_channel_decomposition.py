"""
s19_band_and_channel_decomposition.py

Post-hoc decompositions of the explicit-peak effect, computed from the canonical
2026-08_final outputs. NO model re-solve: every quantity below is derived from the
already-written per-settlement result files.

Produces, with the definition of each stated explicitly:
  (1) the number of settlements crossing the 1 kW step in OnSSET's size-banded
      stand-alone capital-cost schedule, under several candidate definitions;
  (2) delta LCOE% with each settlement's stand-alone capital-cost BAND held at its
      R0 value (isolating the smooth capacity response from the discrete step);
  (3) delta LCOE% with the stand-alone channel frozen at its R0 levelised cost
      (isolating how much of the effect is transmitted through stand-alone supply).

Basis for the levelised-cost aggregate is the same as scripts/s14_paper_numbers.py:
  delta = (sum_i LCOE_R1,i * E_i - sum_i LCOE_R0,i * E_i) / (sum_i LCOE_R0,i * E_i)
with E_i = EnergyPerSettlement2030, which is bit-identical between the two arms.

Usage:  python scripts/s19_band_and_channel_decomposition.py
"""

from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "data" / "onsset_outputs"
SUM = REPO / "results" / "summary"
R0_PATH = OUT / "2026-08_final_lcoe_R0.csv"
R1_PATH = OUT / "2026-08_final_lcoe_R1_n20.csv"

SA_PV = 3          # FinalElecCode for stand-alone PV
GRID = 1

# OnSSET size-banded stand-alone capital cost, USD/kW, keyed on kW per household.
# scripts/onsset_helpers.py: capital_cost={inf:6950, 1:4470, 0.100:6380, 0.050:8780, 0.020:9620}
BANDS = [(0.020, 9620.0), (0.050, 8780.0), (0.100, 6380.0), (1.0, 4470.0),
         (float("inf"), 6950.0)]


def band_price(kw_per_hh):
    """Vectorised band lookup: the first threshold the system does not exceed."""
    price = np.full(len(kw_per_hh), BANDS[-1][1], dtype=float)
    assigned = np.zeros(len(kw_per_hh), dtype=bool)
    for thresh, p in BANDS[:-1]:
        take = (~assigned) & (kw_per_hh <= thresh)
        price[take] = p
        assigned |= take
    return price


COLS = ["id", "Pop2030", "NumPeoplePerHH", "NewCapacity2030",
        "MinimumOverallLCOE2030", "EnergyPerSettlement2030", "FinalElecCode2030"]


def energy_weighted_delta(lcoe_r0, lcoe_r1, energy):
    c0 = float((lcoe_r0 * energy).sum())
    c1 = float((lcoe_r1 * energy).sum())
    return (c1 - c0) / c0 * 100.0


def main():
    print("Reading canonical outputs (no model re-solve) ...")
    r0 = pd.read_csv(R0_PATH, usecols=COLS).sort_values("id").reset_index(drop=True)
    r1 = pd.read_csv(R1_PATH, usecols=COLS).sort_values("id").reset_index(drop=True)
    assert (r0["id"].values == r1["id"].values).all(), "id mismatch between arms"
    assert np.allclose(r0["EnergyPerSettlement2030"], r1["EnergyPerSettlement2030"]), \
        "energy differs between arms"

    energy = r0["EnergyPerSettlement2030"].values
    l0 = r0["MinimumOverallLCOE2030"].values
    l1 = r1["MinimumOverallLCOE2030"].values
    code0 = r0["FinalElecCode2030"].values
    code1 = r1["FinalElecCode2030"].values

    print(f"\nSanity: as-run delta LCOE% = {energy_weighted_delta(l0, l1, energy):.6f}"
          "   (must equal the s06 central headline)")

    # households, on the same basis as the reported median system sizes
    hh = r0["Pop2030"].values / r0["NumPeoplePerHH"].values
    kw0 = r0["NewCapacity2030"].values / hh
    kw1 = r1["NewCapacity2030"].values / hh

    sa0 = code0 == SA_PV
    sa1 = code1 == SA_PV
    both = sa0 & sa1
    switch = sa0 & (code1 == GRID)

    print("\n" + "=" * 72)
    print("(0) BASIS CHECKS")
    print("=" * 72)
    print(f"  settlements                         : {len(r0):,}")
    print(f"  stand-alone in R0                   : {sa0.sum():,}")
    print(f"  stand-alone in R1                   : {sa1.sum():,}")
    print(f"  stand-alone in both                 : {both.sum():,}")
    print(f"  stand-alone -> grid switchers       : {switch.sum():,}")
    print(f"  median kW/household, R0 stand-alone : {np.median(kw0[sa0]):.4f}")
    print(f"  median kW/household, R1 stand-alone : {np.median(kw1[sa1]):.4f}")

    print("\n" + "=" * 72)
    print("(1) SETTLEMENTS CROSSING THE 1 kW STEP  (4,470 -> 6,950 USD/kW)")
    print("=" * 72)
    defs = {
        "a. stand-alone in BOTH arms, kW/hh <=1 in R0 and >1 in R1":
            (both & (kw0 <= 1.0) & (kw1 > 1.0)).sum(),
        "b. stand-alone in R0, kW/hh <=1 in R0 and >1 in R1 (as written)":
            (sa0 & (kw0 <= 1.0) & (kw1 > 1.0)).sum(),
        "c. all settlements, kW/hh <=1 in R0 and >1 in R1":
            ((kw0 <= 1.0) & (kw1 > 1.0)).sum(),
        "d. stand-alone in BOTH arms, any change of cost band":
            (both & (band_price(kw0) != band_price(kw1))).sum(),
        "e. stand-alone in R1, kW/hh >1 in R1 (level, not crossing)":
            (sa1 & (kw1 > 1.0)).sum(),
        "f. stand-alone in R0, kW/hh >1 in R1 incl. switchers (level)":
            (sa0 & (kw1 > 1.0)).sum(),
    }
    for k, v in defs.items():
        print(f"  {k:<62} {v:>9,}")
    print("\n  Paper currently states 148,562.")

    print("\n" + "=" * 72)
    print("(2) COST BAND HELD FIXED AT ITS R0 VALUE")
    print("=" * 72)
    print("  Stand-alone LCOE is proportional to the banded capital cost per kW")
    print("  (capacity = E/(ATR*GHI); every stand-alone cost term scales with capital).")
    print("  So the band-frozen LCOE is LCOE_R1 * price(band_R0)/price(band_R1).")
    p0 = band_price(kw0)
    p1 = band_price(kw1)
    ratio = p0 / p1

    # (2a) allocation held at R1; only stand-alone settlements re-priced
    l1_bandfix = l1.copy()
    l1_bandfix[sa1] = l1[sa1] * ratio[sa1]
    d_2a = energy_weighted_delta(l0, l1_bandfix, energy)

    # (2b) as 2a, but switchers also re-priced as if they had stayed stand-alone
    #      (they only switched because stand-alone became dear; if the band is frozen
    #       the comparison is cleaner on the settlements that did not move)
    l1_bandfix_both = l1.copy()
    l1_bandfix_both[both] = l1[both] * ratio[both]
    d_2b = energy_weighted_delta(l0, l1_bandfix_both, energy)

    print(f"\n  (2a) R1 allocation, all R1 stand-alone re-priced : {d_2a:+.4f}%")
    print(f"  (2b) R1 allocation, only never-switching stand-alone re-priced : {d_2b:+.4f}%")
    print(f"  as run                                          : "
          f"{energy_weighted_delta(l0, l1, energy):+.4f}%")
    print(f"\n  Share of the effect carried by the discrete step (2a): "
          f"{(1 - d_2a / energy_weighted_delta(l0, l1, energy)) * 100:.1f}%")
    print(f"  Band-frozen headline (2a), the figure the paper reports: {d_2a:+.1f}%")

    print("\n" + "=" * 72)
    print("(3) STAND-ALONE CHANNEL FROZEN AT R0")
    print("=" * 72)
    # (3a) R1 allocation, stand-alone settlements pay their R0 levelised cost
    l1_freeze_a = l1.copy()
    l1_freeze_a[sa1] = l0[sa1]
    d_3a = energy_weighted_delta(l0, l1_freeze_a, energy)

    # (3b) R0 allocation retained everywhere (no settlement is allowed to switch),
    #      stand-alone frozen at R0: isolates the non-stand-alone response alone
    l1_freeze_b = np.where(sa0, l0, l1)
    d_3b = energy_weighted_delta(l0, l1_freeze_b, energy)

    # (3c) R1 allocation, stand-alone frozen at R0 AND switchers held at R0 too
    l1_freeze_c = l1.copy()
    l1_freeze_c[sa0] = l0[sa0]
    d_3c = energy_weighted_delta(l0, l1_freeze_c, energy)

    print(f"  (3a) R1 allocation, R1 stand-alone at R0 LCOE (switchers keep R1 grid) : {d_3a:+.4f}%")
    print(f"  (3b) R0 allocation retained, stand-alone at R0 LCOE                    : {d_3b:+.4f}%")
    print(f"  (3c) R1 allocation, every R0 stand-alone settlement at R0 LCOE         : {d_3c:+.4f}%")
    print("  Paper currently states -0.5%.")

    SUM.mkdir(parents=True, exist_ok=True)
    rows = [{"quantity": k, "value": v, "unit": "settlements"} for k, v in defs.items()]
    rows += [
        {"quantity": "band_frozen_delta_lcoe_pct_R1alloc", "value": d_2a, "unit": "%"},
        {"quantity": "band_frozen_delta_lcoe_pct_nonswitchers", "value": d_2b, "unit": "%"},
        {"quantity": "sa_frozen_delta_lcoe_pct_R1alloc", "value": d_3a, "unit": "%"},
        {"quantity": "sa_frozen_delta_lcoe_pct_R0alloc", "value": d_3b, "unit": "%"},
        {"quantity": "sa_frozen_delta_lcoe_pct_all_R0sa", "value": d_3c, "unit": "%"},
        {"quantity": "delta_lcoe_pct_as_run", "value": energy_weighted_delta(l0, l1, energy),
         "unit": "%"},
        {"quantity": "median_kw_per_hh_R0_standalone", "value": float(np.median(kw0[sa0])),
         "unit": "kW"},
        {"quantity": "median_kw_per_hh_R1_standalone", "value": float(np.median(kw1[sa1])),
         "unit": "kW"},
    ]
    out_csv = SUM / "2026-08_final_band_and_channel_decomposition.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"\nWritten: {out_csv}")


if __name__ == "__main__":
    main()
