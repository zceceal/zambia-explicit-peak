# Patch to the OnSSET core

The allocation engine is used unmodified except for the changes in
`onsset-explicit-peak.patch`. It must be applied for the results to reproduce. There are three:
one correctness fix, one guard against that fix being undone, and one symmetry fix.

Base version: OnSSET at upstream commit `c154ece` (installed as `onsset 2.1.dev24+gc154ece12`).

## What the patch does

**`onsset.py` line ~909 — the correctness fix (added 2026-08-16).**
`condition_df()` ends by sorting the settlements on latitude and longitude. It did not reset the
index, so from that point the frame's row *positions* and its index *labels* were two different
orderings of the same settlements. Inside `Technology.get_lcoe()` that matters, because two kinds of
object are combined: `peak_load`, built from a numpy array and therefore labelled 0…N−1 by position,
and `capacity_factor`, passed in as `self.df[SET_GHI] / HOURS_PER_YEAR` and therefore labelled by the
frame's index. Pandas aligns on labels, so every settlement's peak load was divided by a *different*
settlement's capacity factor.

Upstream this never surfaces, because `condition_df()` is normally followed by a CSV write and
re-read, which silently repairs the index. This study passes the frame in memory, which exposed it.

It is hard to notice because for stand-alone PV the T&D cost is zero, so the levelised cost reduces to
`cap_cost × (A + om·D) / (ATR × GHI × D)` and the energy term cancels top and bottom: levelised cost
stayed plausible while capacity and investment were wrong by orders of magnitude. Measured on the
Zambian run, the closed form `capacity = E / (ATR × GHI)` reproduced OnSSET's own `NewCapacity2030`
for **14.137%** of stand-alone settlements before the fix and **100.000%** after.

The correction is one line: `self.df.reset_index(drop=True, inplace=True)`.

**`onsset.py` line ~2519 — the guard (added 2026-08-16).**
`SettlementProcessor._assert_positional_index()` raises if row positions and index labels ever
diverge, and is called at the start of `calculate_off_grid_lcoes` and of
`calculate_investments_and_capacity`. Its purpose is that this class of defect can never again fail
silently: it becomes a crash with an explanatory message rather than a plausible wrong number.
`test/test_index_alignment.py` is the matching regression test.

**`onsset.py` line ~2591 — the symmetry fix.**
Stand-alone PV was the one technology that ignored the per-settlement peak: it received a hard-coded
`base_to_peak_load_ratio` from its own class attribute, while grid extension, hydro, PV-hybrid and
wind mini-grids all read the per-settlement `SET_AVERAGE_TO_PEAK` column. The patch makes stand-alone
PV read the same column as every other technology.

Without it the comparison is not symmetric across technologies, and the explicit-peak effect is
suppressed rather than measured — applying it moved the number of settlements changing technology
from 22 to over 11,000 in the run where it was first tested.

**`onsset.py` line ~301 — a type fix.**
`cap_cost` was initialised as an integer array, which truncated non-integer capital-cost values. Cast
to float. This affects both arms identically and does not influence the treatment effect.

## Worth reporting upstream

The first two items are not specific to this study. A widely used electrification model can, under a
supported usage pattern, misalign its capacity and investment accounting while leaving levelised cost
plausible — which is the combination least likely to be caught by inspection. Both the fix and the
guard are small and self-contained, and would apply unchanged to any OnSSET application that keeps the
frame in memory between calibration and solve.

## Applying it

Clone into `data/onsset_repo`, where `test/test_onsset_install.py` looks for its fixtures:

```bash
mkdir -p data
git clone https://github.com/onsset/OnSSET.git data/onsset_repo
cd data/onsset_repo && git checkout c154ece
git apply ../../patches/onsset-explicit-peak.patch
pip install -e . && cd ../..
```
