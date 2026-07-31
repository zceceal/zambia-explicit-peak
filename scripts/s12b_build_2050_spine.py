#!/usr/bin/env python3
"""
Build the R1 (explicit-peak) settlement spine for the 2050 horizon.

WHY THIS IS RIGOROUS (not an approximation):
OnSSET projects settlement population by simple differential growth with FIXED urban/rural
classification. This was verified against the existing 2035 run: every urban settlement has
Pop2035/Pop2020 = 1.8938 and every rural one = 1.2613, with ZERO variance, and those factors equal
(PopEndYear * UrbanShare)/(urban base pop) etc. exactly. So we can reproduce OnSSET's Pop2050 offline
and recompute P/E on it. The script self-checks by reproducing the 2035 factors before doing 2050.

Only the PE_ratio column changes vs the existing 2035 R1 spine; everything else (incl. base-year Pop)
is identical — OnSSET re-projects Pop internally using the 2050 specs, matching this projection.

Confirmed inputs (WPP-2024 medium variant; see SOURCES_WPP2050.md):
  Pop 2050 = 38,083,385   urban share 2050 = 0.672
  (2035 was 28,266,892 / 0.538; 2020 is 0.437 — all match the specs, validating the series.)

Run from anywhere; paths resolve relative to the repository root:
  python build_r1_spine_2050.py
Outputs: zambia_grid3_spine_pe_2050_n20.csv  (+ _n10 / _n50 for the sweep)
"""
import pandas as pd, numpy as np, sys, os
from pathlib import Path

PROC = str(Path(__file__).resolve().parent.parent / "data" / "processed")
CALIB = os.path.join(PROC, "zambia_grid3_calib_distgate.csv")

# --- confirmed WPP-2024 2050 targets ---
POP2050, URBAN2050 = 38_083_385, 0.672
# --- 2035 targets, used only for the self-check ---
POP2035, URBAN2035 = 28_266_892, 0.538
HH_SIZE = 5.0                                   # NumPeoplePerHH (specs = 5/5)
PE_P1, PE_PINF, PE_PSTEP = 3.98, 1.45, 2.43     # Lorenzoni anchors

def pe_curve(N, nmid):
    beta = -np.log((PE_PSTEP - PE_PINF) / (PE_P1 - PE_PINF)) / np.log(nmid)
    return PE_PINF + (PE_P1 - PE_PINF) * np.power(np.maximum(N, 1.0), -beta)

def growth_factors(pop_future, urban_future, up, rp):
    return (pop_future * urban_future) / up, (pop_future * (1 - urban_future)) / rp

def main():
    c = pd.read_csv(CALIB, usecols=['id', 'Pop', 'IsUrban'])
    urb = (c['IsUrban'] == 2).values
    p20 = c['Pop'].values
    up, rp = p20[urb].sum(), p20[~urb].sum()

    # self-check: reproduce OnSSET's 2035 factors (must be ~1.8938 / 1.2613)
    gu35, gr35 = growth_factors(POP2035, URBAN2035, up, rp)
    assert abs(gu35 - 1.8938) < 1e-3 and abs(gr35 - 1.2613) < 1e-3, \
        f"self-check FAILED: 2035 factors {gu35:.4f}/{gr35:.4f} != 1.8938/1.2613 — spine/urban flag mismatch"
    print(f"[self-check OK] 2035 factors urban {gu35:.4f} rural {gr35:.4f} reproduce OnSSET exactly")

    gu, gr = growth_factors(POP2050, URBAN2050, up, rp)
    pop2050 = p20 * np.where(urb, gu, gr)
    Nhh2050 = np.maximum(pop2050 / HH_SIZE, 1.0)
    print(f"[2050] growth urban x{gu:.4f} rural x{gr:.4f}; "
          f"total {pop2050.sum()/1e6:.3f}M urban {pop2050[urb].sum()/pop2050.sum()*100:.1f}%")

    id_order = c['id'].values
    for nmid, tag in [(20, 'n20'), (10, 'n10'), (50, 'n50')]:
        spine = os.path.join(PROC, f"zambia_grid3_spine_pe_{tag}.csv")
        r1 = pd.read_csv(spine)
        # align to calib id order used for the projection
        m = dict(zip(id_order, pe_curve(Nhh2050, nmid)))
        r1['PE_ratio'] = r1['id'].map(m).values
        out = os.path.join(PROC, f"zambia_grid3_spine_pe_2050_{tag}.csv")
        r1.to_csv(out, index=False)
        med = np.nanmedian(r1['PE_ratio'].values)
        print(f"  wrote {out}  (n_mid={nmid}, median P/E {med:.3f})")
    print("done. Run R1 2050 with these spines; R0 2050 uses the same specs template (uniform BaseToPeak).")

if __name__ == "__main__":
    main()
