# Diesel-price sensitivity rerun on the corrected baseline (2026-10-23)

- **Branch:** `diesel-sensitivity-rerun-audit`, cut from `mg-fuel-units-fix` (`e88520f`). It carries
  `s08`'s diesel-keyed cache and `s26` from `diesel-sensitivity-followup` (`9890d88`).
- **Method:** the same as the 2026-10-19 Task A/B. Same seeds (42, LHS 43), same subsample
  (50,000), Morris r = 8 / k = 6 / p = 4, LHS N = 200 (all full-OnSSET), OAT at 0.95 / 0.38 /
  0.10 USD/L.
- **Isolation:** the run used a separate worktree whose `s06` inputs are clones of the corrected
  baseline.
- **Scope:** no `.tex`/`.bib` edits; nothing pushed.

> **Stop-and-report finding.** The Morris and LHS diesel results, **both the numbers already in the
> paper and this rerun's**, are dominated by a cache artefact, not by diesel price. The diesel-keyed
> PV-hybrid cache in `s08` stores each table under (year, pump-price bin) only. Each table is built
> once, **at the discount rate of whichever arm first needs it**, and reused by every later arm in
> that bin whatever their own discount rate. This is confirmed exactly on a real LHS sample (§3).
>
> The full-dataset OAT (`s26`) rebuilds the table in every arm and is **unaffected**: it is the clean
> diesel result. Nothing has been fixed. Correcting the Morris and LHS numbers needs a decision (§5).

## 1. Gates

| Gate | Reference | Result |
|---|---|---|
| `s08` reads the corrected full-dataset headline | +44.6653 %, 33,669 | +44.6653 %, 33,669 ✓ |
| `s08` subsample central (took-effect file) | corrected baseline +49.2976726510074 %, 4,183 | **identical** ✓ |
| `s26` central vs corrected `s06` | +44.6653 %, 33,669; exact allocation | +44.6653 %, 33,669; `FinalElecCode2030` and `MinimumOverallLCOE2030` identical on all 270,526 rows (max \|diff\| 0) ✓ |
| `s26` at 0.10 USD/L, old vs new | must agree: the mini-grid diesel bin rounds to 0.0, so fuel is free under either unit convention | +47.33968299839 % **both**; identical tech mix ✓ |

## 2. Results, old (paper, pre-fix costing) vs new (corrected costing)

### 2.1 Full-dataset OAT (`s26`): clean

| Diesel (USD/L) | ΔLCOE % old → new | Shift vs own central, old → new | SA_PV→Grid | MG_PVHybrid R0 / R1 | MG settlements burning diesel (R0) |
|---|---|---|---|---|---|
| 1.90 (central) | +45.38 → **+44.67** | — | 33,665 → 33,669 | 1,625 / 1,625 | 1,625 → **181** |
| 0.95 | +46.35 → **+44.97** | +0.98 → **+0.31** pp | 33,673 → 33,669 | 1,629 → 1,625 / 1,625 | 1,629 → 1,625 |
| 0.38 | +47.00 → **+46.24** | +1.62 → **+1.57** pp | 33,674 → 33,674 | 1,629 → 1,628 / 1,625 | 1,629 → 1,628 |
| 0.10 | +47.34 → **+47.34** | +1.96 → **+2.67** pp | 33,676 → 33,676 | 1,630 / 1,625 | not detectable (fuel cost 0) |

**Slope near central:** **−0.32 pp per USD/L** (old −1.03). That is about 0.3× the old slope, which
matches the earlier optimiser-probe prediction.

**Why the response is non-linear.** At the correct fuel price most mini-grids run without a genset
(181 of 1,625 burn diesel), so modest price changes barely matter. Cheap diesel brings gensets back
(all 1,625 burn diesel at 0.95 USD/L), and the effect grows at deep cuts.

**Movers vs central.** No settlement changes technology at 0.95 USD/L. At 0.38 and 0.10 USD/L, 17–39
(R0) and 13–23 (R1) do, all grid-margin moves. Tables:
`2026-10_mgfuel_dsens_movers_diesel-*.csv`.

### 2.2 Morris and LHS (`s08`): numbers as computed, artefact-dominated (see §3)

| Quantity | Old (paper) | New (rerun) | Corrected baseline with year-only cache (diesel frozen at central) |
|---|---|---|---|
| Diesel μ\* ΔLCOE, bias-corrected | 0.915 | 0.916 | 0.000 |
| Diesel σ | 0.649 | **1.129** | 0.000 |
| Diesel μ | −0.915 | −0.842 | 0.000 |
| Diesel μ\* switch count (σ) | 23.1 (34.1) | 20.3 (39.3) | 0 |
| Diesel rank | 6 of 6 | 6 of 6 | 6 of 6 |
| Took-effect probe, +0.38 USD/L at central discount rate | −0.41 pp | **−0.02 pp** | 0 |
| LHS 5th / 50th / 95th (bias-corrected) | +21.0 / +51.3 / +75.6 % | +20.6 / +50.4 / +73.6 % | +20.7 / +50.5 / +74.0 % |
| LHS switches 5th / 50th / 95th | 3,657 / 4,421 / 5,292 | 3,657 / 4,415 / 5,283 | 3,658 / 4,419 / 5,282 |
| Bias-correction factor | 0.9011 | 0.9060 | 0.9060 |
| Emulator | rejected | rejected (RMSE 11.29 pp) | rejected (11.32) |

**Other parameters, new run.** μ\* is 55.98 / 14.70 / 9.65 / 6.00 / 1.90 for Rural_tier / N_mid /
MaxGridDist / SA_PV_capex / Discount_rate. The ranking is unchanged in every run.

## 3. The cache artefact: evidence

**Mechanism.** `run_arm_subsample` keys the PV-hybrid cache on `(year, round(pump price, 1))`. The
table's entries depend on two more things the key does not include:

- the **lookup's own diesel axis**, which is `MGDieselFuelCost` at 0.1 USD/kWh resolution, about
  0.33 USD/L;
- the mini-grid **discount rate** (`build_mg_pv_hybrid_params`).

The cache persists across the whole run: validation → took-effect probes → Morris → LHS. A
reconstruction of `s08`'s exact arm order shows which arm built each table first, and at what
discount rate:

| Pump bin | Built first by | Discount rate baked in |
|---|---|---|
| 1.5 | Morris t1 p1 | 0.0867 |
| 1.6 | LHS 12 | 0.0922 |
| 1.7 | LHS 1 | 0.0841 |
| 1.8 | Morris t2 p1 | 0.0867 |
| 1.9 | validation | 0.0800 |
| **2.0** | **Morris t1 p6** | **0.1400** |
| 2.1 | LHS 17 | 0.0881 |
| 2.2 | LHS 7 | 0.0734 |
| 2.3 | diesel took-effect probe | 0.0800 |

**LHS evidence.** Shift per sample = new run minus the corrected year-cache run, which has the same
samples but every table built at 0.08:

| Pump bin (baked discount rate) | n | Mean shift (pp) |
|---|---|---|
| 1.9 (0.08, cache reused) | 26 | **0.000** (exactly) |
| 2.0 (**0.14**) | 26 | **−2.00** (min −3.32) |
| 2.2 (0.0734) | 26 | +0.24 |
| other bins (0.084–0.092) | 122 | −0.03 to −0.29 |

The shift correlates **−0.93** with the *baked* discount rate. It correlates only −0.07 with each
sample's own discount rate, and −0.07 with its diesel offset. For the **paper's** run (pre-fix
costing, same arm order, so the same baked rates), the shift against the committed year-cache LHS
correlates −0.72 with the baked rate and −0.03 with the sample's own rate. Its bin-2.0 samples shift
by −1.08 pp on average.

**Morris evidence.** The diesel elementary effects are large exactly in the trajectories whose diesel
step lands in the bin-2.0 table baked at 0.14. Bias-corrected EEs, trajectories 1–8:

| | t1 | t2 | t3 | t4 | t5 | t6 | t7 | t8 |
|---|---|---|---|---|---|---|---|---|
| New | −2.30 | +0.02 | +0.12 | +0.12 | −2.50 | −0.17 | −2.07 | +0.03 |
| Old | −1.57 | −0.11 | −1.07 | −1.03 | −1.79 | −0.11 | −1.47 | −0.18 |

Trajectories 1, 5 and 7 step 1.52 → 2.03 (into the 0.14 table) at their own discount rates of 0.14,
0.06 and 0.06.

**Hand check: LHS sample 141** (diesel 2.024, discount rate 0.083, N_mid 30.2), re-solved on the
real 50,000-settlement subsample under three cache states:

| Cache state | Raw ΔLCOE % | Bias-corrected | Match to stored value |
|---|---|---|---|
| (a) bin-2.0 table baked at discount rate 0.14 | 81.0784 | 73.46 | **reproduces the rerun's stored value exactly** |
| (b) clean rebuild at the sample's own rate 0.083 | 84.5602 | 76.61 | — |
| (c) central table, rate 0.08 (year-only key) | 84.7435 | 76.78 | **reproduces the year-cache stored value exactly** |

For this sample the artefact is **−3.16 pp** (a − b). The genuine diesel plus own-discount-rate
effect is −0.17 pp (b − c).

**What it is not.**

- **Not diesel price.** At the central discount rate, pump 1.90 against 2.00 USD/L on the same
  subsample gives +49.2977 % against +49.3032 %, i.e. +0.006 pp.
- **Not optimiser noise.** Re-optimising each in-use lookup entry with 10 seeds varies LCOE by at
  most 0.006 USD/kWh (about 0.1 pp of ΔLCOE), with no infeasible results.

**Consequences.**

- The paper's corrected Morris diesel μ\* (0.92, σ 0.65) and its LHS band (+21.0 / +51.3 / +75.6 %)
  are contaminated by a stale discount rate, not just a stale diesel price.
- This rerun's diesel μ\* (0.916) and σ (1.13) are mostly the same artefact. Its LHS band includes it
  too, though band percentiles move only by about 0.1–0.5 pp.
- The other five Morris parameters can sit on a contaminated table at some trajectory points. But
  each of their steps holds diesel fixed, so both ends of the step use the **same** table and the
  artefact largely cancels in their elementary effects. Their μ\* values move only 0.1–0.6 against
  the year-cache run.
- **The 2026-10-19 report** said the old cache "removed the diesel channel" and the new key restored
  it. Its "μ\* = 0.92" verdict and its cross-method agreement (Morris and LHS slopes of about
  −1.2 pp per USD/L against OAT −1.03) are **not supported**: the Morris and LHS parts were largely
  this artefact. That the slopes matched was partly coincidence, because the OAT run had a genuine
  slope on the pre-fix costing.

## 4. Clean diesel result on the corrected baseline

The only artefact-free diesel numbers here are the full-dataset OAT (§2.1):

- Over the realistic ±20 % range, the implied ΔLCOE change is about 0.32 × 0.76 ≈ **0.24 pp end
  to end**. That is first-order from the OAT slope; the ±20 % points were not solved directly.
- Sample 141's clean diesel-plus-discount-rate effect (−0.17 pp at +0.12 USD/L) is consistent with
  that.

A clean Morris μ\* would need §5's fix. On the OAT slope it would be of order 0.2: still last, below
Discount_rate (1.90). That is an estimate, not a result.

## 5. Decision needed (nothing fixed)

To get clean Morris and LHS diesel numbers, `s08`'s cache key must cover every input of the table:
year, the lookup's own diesel bins (or the delivered-price range), and the mini-grid discount rate.
The alternative is no cache (`pv_lut_cache=None`, as `s09` and `s26` do), which costs a table build
per arm, about 15 s on the subsample.

Either way, `s08` would need re-running (about 45–60 min). The paper's diesel Morris and LHS
sentence would then change. Until then the defensible diesel statement rests on the full-dataset
OAT.

## 6. Outputs

- `data/onsset_outputs/2026-10_mgfuel_dsens_*`: `s08` Morris/LHS/took-effect; `s26` OAT, movers, and
  SA_Diesel shadow files. The shadow files are still **parked**; see
  `2026-10_PARKED_sadiesel_shadow_cost.md` on `diesel-sensitivity-followup`.
- `results/summary/2026-10_mgfuel_dsens_*.csv`: summary copies.
- Diagnostics are in `_claude_workspace/logs/2026-10-23_dsens_rerun_diagnostics/`: `cache_order.log`, `hand_141.log`, `de_noise.log`,
  `subsample_lut.log`, `dsens_s08_cmp.txt`, `dsens_oat_cmp.txt`.
- Compute: `s08` 46.0 min, `s26` 13.4 min.
