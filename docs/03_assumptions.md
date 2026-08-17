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
  1.24 kW, so about 200,000 settlements cross that step. Holding the band fixed at its R0 value puts
  the headline at +22.8% rather than +49.9% — more than half the effect is the discontinuity rather
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
- **Result:** the Tier-3 cost effect moves only about ±2 percentage points across the decade. The
  global sensitivity screen ranked `N_mid` a comparatively minor factor, below the discount rate.
- **Why not measured:** no metered multi-site Zambian mini-grid load dataset is public. The one
  commercial dataset is proprietary. This is stated as future work.

### 2.3 Borrowed load shapes

The peak anchors come from 61 mini-grids worldwide, not from Zambia.

- **Test:** the calibrated curve was checked against three independently measured systems — two
  Ethiopian mini-grids (443 and 450 connections) and the Zambian national residential system
  (~1.3 million). At **every** tested point the measured value sat on or above the model curve.
- **Consequence:** the borrowed anchors behave **conservatively** in Zambia. The transfer error runs
  in the direction that weakens the finding, not strengthens it.
- **Gap:** the small-settlement regime that dominates the country is not directly metered. It rests on
  the measured single-household archetype plus the physical argument.

### 2.4 Demand level

Rural households are assigned MTF Tier 3 (~803 kWh/household/year), matching the published Zambia
study and the universal-access framing. This is aspirational for rural Zambia.

- **Test:** the whole comparison is repeated at Tier 2, a 73% reduction.
- **Result:** the cost increase persists (+28.5% to +35.5%). The technology reallocation largely
  disappears. So the cost finding is demand-robust; the reallocation finding requires Tier 3+.

### 2.5 Absolute cost level

The modelled cost per person sits roughly 3–4× above continental averages for Tier-3 access.

- **Why:** partly because the model covers the hardest-to-reach remote settlements; partly because the
  inherited OnSSET/GEP cost defaults sit at the high end.
- **Why it is not "fixed":** those defaults are the field's reference set, identical to the benchmarks
  the study compares against. Re-tuning them would be over-fitting.
- **Why it does not matter for the finding:** the paper's claims are all **relative** (R1 versus R0), so
  a level offset cancels in the contrast.

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
| Hydro mini-grids allocate to zero | 195 settlements sit within 5 km of hydro but fall below the 100-connection viability threshold |
| Single diesel price bin | Diesel is never least-cost in any reported outcome |
| Coarse grid in dispersed rural areas | Creates a single-household tail; excluding it moves the headline by 0.6 pp |

---

## Assumptions specific to the 2050 run

The 2050 comparison holds technology costs, the cost dictionary and the discount rate **fixed at
present-day values**, changing only the population and its urban/rural split.

Real 2050 conditions would very likely include further solar and battery cost declines, which would
push more settlements toward peak-tolerant technologies and **erode the peak penalty further**. The
measured ~35% erosion is therefore a **lower bound**, not a central estimate.

---

## One-line summary

The model's direction rests on physics and survives every test applied. Its magnitude rests on a
sizing convention inherited from the standard tool, and is reported as a range for that reason. Its
one unmeasured parameter is swept across a full decade and ranks as a minor factor.
