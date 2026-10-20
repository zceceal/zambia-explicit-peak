# Dimensional / unit-consistency audit of the cost and energy calculations (2026-10-20)

**Scope.** Every cost and energy calculation in `onsset.py` and `hybrids.py` (vendored OnSSET,
`c154ece` plus the repository patch `cd64900`), `onsset_helpers.py`, and the pipeline scripts. For
each input, the unit was traced from where it is computed (not inferred from its name) to the unit
the consumer expects. Style, performance and general review are out of scope.

**Method.** Code tracing, then a hand check on a real settlement of the corrected baseline
(`mg-fuel-units-fix`, `e88520f`) for every flag. No flag was cleared or confirmed on code-reading
alone. Read-only: no code was changed. Hand-check log: `_claude_workspace/logs/` and
`audit_checks.py` in the session scratchpad.

**Outcome.**

- **Three findings are confirmed**, each with a hand check. All are upstream OnSSET behaviour, and
  each could move a paper number:
  - F-A, about −0.5 pp on the headline;
  - F-B, investment only;
  - F-C, about +0.04 pp.
- **None has been fixed.** They are reported for a decision.
- Three name/label mismatches carry correct values and are harmless.
- Everything else examined is consistent.

## 1. Confirmed findings (decision needed)

### F-A — energy bought or generated is the delivered energy; losses enter capacity only

**Pattern.** This is the same failure pattern as the mini-grid fuel bug: a quantity used in a
different meaning from the one it was computed for.

**Where.** `Technology.distribution_network` (`onsset.py:565–625`) computes three quantities:

- `average_load = consumption / (1 − distribution_losses) / 8760` (kW);
- `peak_load = average_load / ATR`;
- it returns **`consumption`**, the delivered demand, in the slot that `td_network_cost` and
  `get_lcoe` call **`generation_per_year`** (`onsset.py:300–312`).

`get_lcoe` then builds `el_gen` from it, and charges both the fuel term
(`fuel[:, p] = el_gen × fuel_cost`, `onsset.py:389–390`) and the LCOE denominator on delivered kWh.
Capacity and the grid capacity investment are sized on the loss-inflated peak. Energy is not.

**Hand check: grid settlement id 563** (R0, grid-connected in 2030, unelectrified in 2020,
0.689 km from the grid).

| Item | Value |
|---|---|
| `get_lcoe` recomputed with the real `grid_calc` | 0.804575 USD/kWh, **identical** to the committed `Grid2030` |
| Demand E | 5,621.0 kWh/yr |
| Returned `generation_per_year` | **5,621.0 kWh/yr**, i.e. equal to demand |
| Peak | 1.510 kW, which equals E / (1 − 0.15) / 8760 / 0.5 (losses included) |
| LCOE with `grid_price` 0.013 minus LCOE with `grid_price` 0 | **0.013000 USD per delivered kWh** |
| The same if the 15 % grid losses had to be generated | 0.015294 USD per delivered kWh |

**Mini-grids.** The same applies with 5 % losses. The hybrid lookup is scaled by delivered demand
(`apply_pv_hybrid_lookup`, `scale = E / 10000`) and its generation LCOE is added per delivered kWh,
so a mini-grid generates no allowance for its own distribution losses.

**Contrast.** OnSSET's own hydro capacity check (`limit_hydro_usage`, `onsset.py:2737`) does divide
energy by `(1 − losses)`.

**Estimated effect, first-order, allocation held fixed.** Corrected baseline energy shares are grid
72.0 / 73.2 % and MG 10.5 %.

| Channel | Change in delivered-energy cost | Effect on ΔLCOE |
|---|---|---|
| Grid | +0.00229 USD/kWh | −0.25 pp |
| Mini-grid | about +0.0147 USD/kWh (0.279 × 0.05/0.95) | −0.24 pp |
| **Both** | | **about −0.49 pp**: central +44.67 % → about +44.2 % |

The allocation might also shift slightly at the grid / SA_PV margin. Not recomputed.

**Status.** This is upstream OnSSET behaviour (the patch does not touch these lines), shared with
GEP-style runs. Whether `generation_cost_usd_kwh` (Egli et al. 2023, Table S8) is meant per kWh
generated or per kWh delivered decides whether this is an error or a convention. That source was
not checked [TODO: verify]. **Not fixed.**

### F-B — mini-grid investment adds a discounted sum to undiscounted ones

**Where.**

- `hybrids.calculate_hybrid_lcoe` accumulates `investment += (…)/(1 + r)**year`, which is
  **discounted** (`hybrids.py:316`).
- `apply_pv_hybrid_lookup` scales it, and `get_lcoe`'s hybrid branch adds it to the network
  investment, which is an **undiscounted** sum (`onsset.py:408, 433`).
- Grid, SA_PV and hydro investment are all undiscounted, including reinvestment.
- `InvestmentCost2030` therefore mixes the two bases, but only for mini-grids.

**Hand check: settlement id 46780** (mini-grid; corrected configuration PV 9.822 kW, battery
27.052 kWh, no genset, battery life 12 yr per 10 MWh reference; capacity check matches
`NewCapacity2030` exactly).

| Item | USD |
|---|---|
| Committed `InvestmentCost2030` | 584,020 |
| Hybrid part as reported (discounted at 8 %) | 320,971 |
| Network part (undiscounted) | 263,049 |
| Hybrid part undiscounted, same items and years | **384,712** (×1.199) |

**Effect.** LCOE is unaffected; this is investment reporting only. First-order, mini-grid
investment would rise about **+USD 0.24 bn in each arm**: R0 total 16.33 → about 16.57 bn.
ΔInvestment in USD is unchanged, and ΔInvestment % falls slightly. **Not fixed.**

### F-C — hybrid LCOE charges running costs in a year with no generation, on a shorter horizon than the rest of the LCOE

**Where.** `calculate_hybrid_lcoe` uses `project_life = end − start = 15`, loops years 0…15, and
sets `generation[0] = 0`. Fuel and O&M are charged in all 16 years, but generation is credited in
years 1…15 only (`hybrids.py:260–262, 284–327`). At 8 % that inflates running costs by
Σ₀…₁₅ / Σ₁…₁₅ = 9.5595 / 8.5595 = ×1.117.

The network part of the same mini-grid LCOE (`get_lcoe`) uses `end − start + 1 = 16` years, with
generation in every year.

**Hand check: settlement 46780.** A Python replica of `calculate_hybrid_lcoe` reproduces the
compiled LCOE exactly (0.279040138).

| Configuration | LCOE as run | Without year-0 fuel and O&M |
|---|---|---|
| Corrected (O&M only) | 0.279040 | 0.276630 (−0.0024 USD/kWh) |
| Pre-fix, diesel-heavy (at the pre-fix price) | 0.235097 | 0.222839 (−0.0123) |

**Effect.** First-order about **+0.04 pp** on the corrected headline. It matters more where
mini-grid diesel use is high. **Not fixed.**

## 2. Name or label mismatches (values correct, no numeric effect)

| Item | What the name or comment says | What it contains (checked) |
|---|---|---|
| `SET_GHI` comment (`onsset.py:38`) | "kWh/m2/day" | kWh/m²/**yr** (data 1,798–2,133). Every consumer treats it as annual: SA_PV CF = GHI/8760 = 0.205–0.243; the hybrid profile is scaled to GHI × 1,000 Wh/m²/yr |
| `SET_NEW_CONNECTIONS` comment (`onsset.py:59`) | "new **people**" | new **households**, `round(Pop/hh − ElecPop/hh)` (`onsset.py:2020`). Checked on ids 46780 (156), 9319 (42) and 1 (3), and demand = 803 kWh/hh × households exactly. All consumers (`td_network_cost`, demand, extension filters) use it as households |
| `generation_per_year` (`distribution_network`, `get_lcoe`) | generation | delivered consumption (see F-A) |

## 3. Examined and consistent

- **`_diesel_fuel_cost_calculator`** (Szabo). (price + 2·price·L/h·h/L)/(kWh/L)/eff gives USD/kWh.
  The delivered price in USD/L is recovered exactly (1.906972 for id 46780).
- **`compute_diesel_cost`, `diesel_cost_columns`.** SA and MG columns are written in USD/kWh.
  Consumers: the hybrid lookup (fixed on `mg-fuel-units-fix`), the grid diesel backup (kWh × USD/kWh,
  inactive), and wind (same issue, disabled).
- **`transmission_network`.** HV/MV switch by cost ratio × kVA. kW is divided by kVA with no power
  factor, an upstream convention. MV patch already documented.
- **`distribution_network`.** Average/peak kW, kVA vs transformer kVA, LV load moment in kW·m, km
  geometry. Consistent, apart from F-A's energy return.
- **`td_network_cost`.** Households − households (see §2); line costs USD/km × km; transformers;
  connection cost USD/hh × households; mini-grid powerhouse lump sum.
- **`get_lcoe`.** Installed kW = peak/CF; capital USD/kW × kW (stand-alone banded on kW per
  household); O&M = % of capital; grid capacity USD/kW × peak kW; discounting and reinvestment
  (reinvestment convention already disclosed, `CORRECTED_CONVENTIONS`); salvage.
- **`get_lcoe_backup`.** Inactive (`grid_reliability_option = "None"`).
- **`calculate_demand` / `set_residential_demand` / `calculate_total_demand_per_settlement`.**
  Tiers are kWh per household per year (`TIERS` = GEP per-capita × 5); demand = tier × households.
  ATR by tier.
- **`calculate_off_grid_lcoes`.** SA_PV CF = GHI/8760; MG eligibility counts households.
- **`calculate_investments_and_capacity`, `results_columns`, `choose_minimum_off_grid_tech`.**
  Selection and summation. The chosen LCOE equals the chosen technology's LCOE in every row except
  the 115 zero-demand rows (see §4).
- **`limit_hydro_usage`.** Required kW = E/(8760·CF·ATR·(1−losses)) against site kW.
- **`hybrids.pv_generation`.** kW × 0.9 × W/m² ÷ 1000 gives kWh/h, with temperature derating.
- **`year_simulation` / `hour_simulation`.** Battery in kWh and state-of-charge fractions; dispatch
  in kWh/h; fuel in L; battery life in years from equivalent full cycles.
- **`calc_load_curve`.** Hourly shares sum to 1/day × 365, so the curve sums to the annual demand.
- **`calculate_hybrid_lcoe`.** Component costs USD/kW and USD/kWh × kW and kWh. Consistent, apart
  from the fuel price units (fixed) and F-B/F-C.
- **`onsset_helpers.build/apply_pv_hybrid_lookup`.** Inv and cap scaled linearly by E/10,000;
  LCOE not scaled. The documented population-vs-household eligibility test has no effect.
- **`build_tech_objects`, `build_mg_pv_hybrid_params`.** Every parameter's unit matches its
  consumer.
- **Pipeline scripts.** `s06`/`s08`/`s09`/`s26` `sa_diesel_cost`/`mg_diesel_cost` dicts are
  identical; grid generation and capacity costs pass in USD/kWh and USD/kW; `s08` and `s09` diesel
  overrides pass through cfg in USD/L.
- **Not used by this pipeline, so out of the numeric path.** `pv_hybrids_lcoe` and
  `pv_hybrids_lcoe_lookuptable` (with their emission-factor lines), the wind-hybrid path (same fuel
  units issue; MG_Wind disabled at LCOE 99), and the `MG_Diesel`/`SA_Diesel` candidates (not in
  `techs`).

## 4. Sanity pass on the corrected baseline outputs (2030; R0 and R1 at `N_mid` 20)

| Check | Result |
|---|---|
| Negative values in any cost, energy, capacity or LCOE column | none |
| inf values | none |
| NaN | `Grid2030` only, in 115 rows (below) |
| LCOE range, Grid (R0) | 0.013–0.54 (median)–99 USD/kWh |
| LCOE range, SA_PV (R0) | 0.99 / 1.05 / 2.47 USD/kWh |
| LCOE range, MG (R0) | 0.31 / 0.50 / 0.77 USD/kWh |
| LCOE range, SA_PV (R1) | up to 4.92 USD/kWh, as expected from peak sizing |
| Energy ÷ (capacity × 8760), SA_PV | 0.115 = GHI-CF 0.23 × ATR 0.5 |
| Energy ÷ (capacity × 8760), grid | ≤ 0.425 = ATR 0.5 × (1 − 0.15), consistent with F-A |
| Energy ÷ (capacity × 8760), MG | 0.116–0.142 |
| Delivered diesel | MG 0.579–0.620 USD/kWh (1.90–2.03 USD/L); SA 0.682–1.680 USD/kWh (1.90–4.68 USD/L) |
| Investment per new connection | SA_PV 6.7k–12k USD (R0; includes the year-5 reinvestment); MG 2.7k–8k; grid 0.6k–12.6k |
| Diesel use where diesel is selected | no diesel technology is selected (SA_Diesel and MG_Diesel are not candidates); corrected-baseline mini-grids mostly run without a genset |
| LCOE = 99 or NaN rows | 115 grid settlements electrified in the base year with **zero new demand**; contribute 0 kWh and exactly 0 to the energy-weighted cost; identical in the committed run |
| Zero-demand rows | 11,697 settlements (median 0.4 household; household count rounds to 0 new connections) carry about 10⁻¹⁵ kW capacity and 0 USD investment. Harmless to the totals. They are settlements below one household that receive no connection; a modelling convention, outside this audit |

## 5. Other observations (outside units scope; noted, not investigated)

- `hybrids.hour_simulation`: the statement `soc - 0.0002 * soc` has no assignment, so battery
  self-discharge is counted in battery use but never applied to the state of charge.
- The battery-life formula carries an upstream `ToDo` on its depth-of-discharge factor.
- `TotalEnergyPerCell` on zero-household rows (803 kWh where `round(Pop/hh)` = 0) does not reach
  any cost on these rows (their base-year code is 99).

## 6. Decisions needed

Each finding needs one decision: fix (and re-run), disclose as an upstream convention, or leave.

| Finding | First-order effect on corrected baseline | What a fix would touch |
|---|---|---|
| F-A energy basis | headline about −0.49 pp; capacity unchanged | `distribution_network` / `get_lcoe` energy, or the price inputs ÷ (1 − losses), in vendored OnSSET or at the boundary |
| F-B investment basis | MG investment about +0.24 bn per arm; LCOE none | hybrid investment summation (vendored `hybrids.py`) or an undiscounted recomputation at the boundary |
| F-C hybrid horizon | about +0.04 pp | vendored `hybrids.py` year loop |
