# Assumptions

What the model takes on trust, why, and how each one is tested.

They are grouped by how much they matter. The first group could in principle change the answer; the
second changes the size of the answer; the third does not affect the comparison at all.

---

## Group 1 — Assumptions that could threaten the finding

**None were found.** This is the honest summary of the robustness work: no combination of tested
assumptions makes explicit peaks *cheaper*, or leaves the technology allocation untouched at
aspirational service levels. The direction of the result follows from a physical fact — small
settlements do not diversify their peaks — rather than from any parameter choice.

---

## Group 2 — Assumptions that affect the size of the result

### 2.1 The peak-to-capacity sizing convention  ← the biggest one

OnSSET sizes installed capacity as peak divided by capacity factor, and scales the **whole** capital
schedule with it. Physically, for a battery-based stand-alone system only the battery, inverter and
balance-of-system should scale with peak; the solar panels scale with energy.

- **Effect:** the headline is an **upper bound**. Scaling only a fraction `f` of stand-alone capital
  with peak gives **+21.0% at `f = 0.4` and +30.6% at `f = 0.6`, against +49.9% at `f = 1.0`**
  (`s10`, run of 2026-08-16). Measured African solar-home-system cost structures suggest
  `f ≈ 0.4–0.45`.
- **A second, related convention.** OnSSET prices stand-alone PV from a five-step schedule keyed on
  system size per household, and that schedule is non-monotonic: \$4,470/kW between 100 W and 1 kW,
  rising to \$6,950/kW above 1 kW. Explicit peaks lift the median household system from 0.80 kW to
  1.24 kW, so about 153,000 settlements cross that step. Holding the band fixed at its R0 value puts
  the headline at +23.6% rather than +49.9% — more than half the effect is the discontinuity rather
  than the smooth capacity response. `scripts/s15_run_capex_curve_sensitivity.py` re-solves the
  central case against a continuous curve to measure this directly.
- **Why it is kept:** it is unmodified OnSSET behaviour, shared with the GEP and Imasiku benchmarks.
  Changing it would break comparability.
- **Consequence:** the *direction* is convention-independent; the *magnitude* is not, and is reported
  as an envelope rather than a point.

### 2.2 `N_mid` — the one free parameter in the peak sub-model

The measured anchors report peak-to-energy by *load-shape archetype*, not by *connection count*. So
mapping them onto settlement sizes requires assuming at what connection count a load looks like the
intermediate archetype. That is `N_mid`.

- **Handling:** central value 20 households, swept over a full decade {10, 20, 50}, with the entire
  pipeline re-solved at each. Every headline is reported as a band.
- **Result:** the Tier-3 cost effect spans **+34.1% (`N_mid`=10) to +70.6% (`N_mid`=50)** around the
  central-case +49.9% (`N_mid`=20) — a wide band, not a tight one. The corrected global sensitivity
  screen ranks `N_mid` **2nd of six factors** (μ\* = 14.5, behind only the rural demand tier), **above**
  the discount rate (5th, μ\* = 2.2). `N_mid` is one of the more influential parameters in the model,
  which is the reason it is swept over a full decade rather than fixed.
- **Why not measured:** no metered multi-site Zambian mini-grid load dataset is public. The one
  commercial dataset is proprietary. This is stated as future work.

### 2.3 Borrowed load shapes

The peak anchors come from 61 mini-grids worldwide, not from Zambia.

- **Test:** the calibrated curve was checked against two metered Ethiopian mini-grids (443 and 450
  connections) and one national planning parameter, **not** a third measurement — Zambia's own IRP
  assumes a constant 68.5% residential load factor nationally (Demand Assessment and Forecast
  Report). Table 3.01's 769 MW and 4,618 GWh (2020) are both generated from that one assumption, not
  measured independently of each other, giving rho = 769 / (4,618,000 / 8,760) = 1.4587 at
  ~1.0 million meter points — the table's own peak over its own mean, not 1/0.685 (which gives
  1.4599; the two differ only because 769 MW is itself rounded in the source table). The comparison is still informative — it shows what this model implies at national scale
  next to what Zambia's own planner assumes — but it is not external validation by measurement, and
  should not be called one. The Omorate mini-grid (443 connections, 2.88) sits well above the central
  curve (1.818); the Tum mini-grid (450 connections, 1.80) and the Zambian load-factor point both sit
  fractionally **below** it (central curve 1.816 and 1.482 respectively) — not "on or above" at every
  point, as an earlier, misattributed version of the national figure (rho ≈ 1.67, pairing a 2020 IRP
  peak with 2019 ERB energy) had implied.
- **Consequence:** of the two metered systems, one sits essentially on the curve (Tum, within ~1%)
  and one sits materially above it (Omorate); the national load-factor point also sits close to the
  curve. The borrowed anchors are not uniformly conservative in Zambia the way an earlier draft of
  this document stated. The direction of the headline result does not depend on this — see Group 1 —
  but the calibration should not be described as one-sidedly conservative, and the national point
  should not be described as measured.
- **Gap:** the small-settlement regime that dominates the country is not directly metered. It rests on
  the measured single-household archetype plus the physical argument.

### 2.4 Demand level

Rural households are assigned MTF Tier 3 (~803 kWh/household/year), matching the published Zambia
study and the universal-access framing. This is aspirational for rural Zambia.

- **Test:** the whole comparison is repeated at Tier 2, a 73% reduction.
- **Result:** the cost effect does **not** simply persist at reduced magnitude — it reverses sign at
  `N_mid`=10: **−2.2% (n10), +3.3% (n20), +8.4% (n50)**, against +34.1%/+49.9%/+70.6% at Tier 3. The
  technology reallocation largely disappears (12/72/436 SA_PV→Grid switches at Tier 2, versus ~34,000
  at Tier 3). So the cost finding is Tier-3-dependent — it does not survive the demand reduction as a
  fixed-sign effect — while the reallocation finding requires Tier 3+ regardless.

### 2.5 Absolute cost level

The modelled cost per person sits roughly 3–4× above continental averages for Tier-3 access.

- **Why:** partly because the model covers the hardest-to-reach remote settlements; partly because the
  inherited OnSSET/GEP cost defaults sit at the high end.
- **Why it is not "fixed":** those defaults are the field's reference set, identical to the benchmarks
  the study compares against. Re-tuning them would be over-fitting.
- **Why it does not matter for the finding:** the paper's claims are all **relative** (R1 versus R0), so
  a level offset cancels in the contrast.

### 2.6 Mean household size

Household size is a measured 2022 census enumeration (ZamStats 2022, Section 4.3), not an assumed or
borrowed value: urban 4.6, rural 5.0, applied identically to both cases. It sits in Group 2 not
because the figure is uncertain, but because it feeds an asymmetric channel: the demand-side effect
(fewer, larger households means less energy per settlement) is common to both R0 and R1 and cancels
out of the stand-alone levelised cost, while the connection count N = max(1, Pop/s), which it also
sets, feeds the coincidence model, which only the explicit-peak case uses. A change in household size
can therefore move the R1–R0 contrast even though its demand-side effect cancels.

- **Handling:** as a stress test far wider than the real uncertainty in an enumerated census figure,
  the rural value is perturbed by ±10% (4.5 and 5.5 against the census 5.0) and both cases re-solved
  at `N_mid` = 20 (`s18`).
- **Result:** +48.10% at 4.5 persons (33,605 stand-alone-to-grid switches) and +51.62% at 5.5
  (34,694 switches), against +49.9% at the census value — a band narrower than the `N_mid` sweep
  already reported (Section 2.2).

---

## Group 3 — Assumptions shared by both runs (they cancel out)

Because every shared input is identical across R0 and R1, these bias the absolute numbers but cancel
in the comparison that carries the contribution.

| Assumption | Note |
|---|---|
| Grid build rate unconstrained | Overstates the absolute grid share versus a rate-limited plan. Common to both runs |
| 100% electrification by 2030 | A scenario choice, not a model error — it is the universal-access frame |
| Grid reliability at OnSSET default (0.963) | No cost of non-served energy |
| Residential demand only | Productive and institutional loads not separately modelled |
| Per-household demand held flat | Total demand grows only through population |
| Wind mini-grids disabled | A one-line bug in the OnSSET core. Zambian wind capacity factor ≈ 0.10, so immaterial |
| Hydro mini-grids allocate to zero | 162 settlements sit within 5 km of hydro; most (156) fall below the 100-connection viability threshold |
| Single diesel price bin | Diesel is never least-cost in any reported outcome |
| GRID3 natural-cluster settlement geometry | Inherits a single-household tail (55,157 settlements, N_hh<=1) from the published GRID3 building-footprint product — 50,880 of the 55,157 (92%) are GRID3 clusters (chiefly the Hamlet class), not cells of the model's own dispersed-rural grid; the tail is a property of the source data, not manufactured by the aggregation choice. Excluding it moves the headline by −2.5 pp (+49.9% -> +47.4%) |

---

## Assumptions specific to the 2050 run

The 2050 comparison holds technology costs, the cost dictionary and the discount rate **fixed at
present-day values**, changing only the population and its urban/rural split.

Real 2050 conditions would very likely include further solar and battery cost declines, which would
push more settlements toward peak-tolerant technologies and **erode the peak penalty further**. The
measured ~33% erosion is therefore a **lower bound**, not a central estimate.

---

## One-line summary

The model's direction rests on physics and survives every test applied. Its magnitude rests on a
sizing convention inherited from the standard tool, and is reported as a range for that reason. Its
one unmeasured parameter is swept across a full decade and ranks as a minor factor.
