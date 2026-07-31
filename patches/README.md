# Patch to the OnSSET core

The allocation engine is used unmodified except for the two-line change in
`onsset-explicit-peak.patch`. It must be applied for the results to reproduce.

Base version: OnSSET at upstream commit `c154ece` (installed as `onsset 2.1.dev24+gc154ece12`).

## What the patch does

**`onsset.py` line ~2591 — the substantive change.**
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

## Applying it

Clone into `data/onsset_repo`, where `test/test_onsset_install.py` looks for its fixtures:

```bash
mkdir -p data
git clone https://github.com/onsset/OnSSET.git data/onsset_repo
cd data/onsset_repo && git checkout c154ece
git apply ../../patches/onsset-explicit-peak.patch
pip install -e . && cd ../..
```
