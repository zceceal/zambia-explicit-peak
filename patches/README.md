# Patch to the OnSSET core

The allocation engine is used unmodified except for the changes in
`onsset-explicit-peak.patch`. It must be applied for the results to reproduce. There are six:
one correctness fix, one guard against that fix being undone, one medium-voltage line-count
correction, one symmetry fix, one type fix, and one reinvestment-schedule convention switch.

Base version: OnSSET at upstream commit `c154ece` (installed as `onsset 2.1.dev24+gc154ece12`). The
exact result of applying this patch is also recorded as commit
`cd64900445feb6a41c03c86cfe3d46c2d30cfee8` on the `explicit-peak-thesis` branch of the vendored copy
at `data/onsset_repo` (local only, not pushed) — verified byte-identical to applying the patch fresh
(see `REPRODUCING.md` §2).

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

**`onsset.py` lines ~504 and ~1493 — the medium-voltage line-count correction (added 2026-08-16).**
`no_of_mv_lines` was computed against `mv_amperage = service_transf_type / mv_line_type`, which
algebraically reduces to `ceil(peak_load / service_transf_type)` — i.e. it counted parallel
MEDIUM-VOLTAGE feeders against the rating of a 75 kVA distribution *transformer*, not against the MV
*line's* own rating (`mv_line_amperage_limit`). A 33 kV line at its 275 A limit carries 9,075 kVA, so
the original over-counted by up to 121x for settlements above that threshold. The upstream code
itself flagged the line with `# ToDo check`. The same correction is applied at both call sites
(`Technology.get_lcoe`'s transmission-network branch, and the standalone grid-extension calculation)
so both use one convention.

Measured exposure on this dataset: the two expressions differ for 371 of 270,526 settlements
(0.137%) — only those with peak load above 75 kW — of which 190 are grid-served with a median
connection distance of 0 km, so the correction changes total MV line length by about 1,562 km,
roughly 0.09% of aggregate investment. It is made because it is right, not because it is large; it
is not the source of the headline effect.

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
to float. This affects both arms identically and does not influence the explicit-peak effect.

**`onsset.py` lines ~117–133 and ~348–377 — the reinvestment-schedule convention switch.**
OnSSET books at most one reinvestment, at year `tech_life`, however long the project horizon, and
compensates with a salvage term that goes negative to correct for it. Over a 16-year horizon a 5-year
asset is therefore installed at years 0 and 5 only, while generation is credited for all 16 years —
understating stand-alone PV capital by 7.19% relative to installing at 0, 5, 10 and 15 with the unused
life of the last asset credited. This is technology-asymmetric: grid has `tech_life` 30 > 16 and is
unaffected under either convention, while stand-alone PV — the channel this study's whole measured
effect travels through — is the technology understated.

The new module-level dict `CORRECTED_CONVENTIONS = {"full_reinvestment": False}` defaults to
reproducing unmodified OnSSET (the central case and every other reported number). Setting
`onsset.CORRECTED_CONVENTIONS["full_reinvestment"] = True` — as `scripts/s16_run_corrected_conventions.py`
does — switches to the full schedule for a labelled robustness variant. This dict and the branch it
takes are part of the engine this patch produces; `s16` requires them.

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
