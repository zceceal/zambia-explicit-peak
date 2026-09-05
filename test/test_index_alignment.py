"""
test_index_alignment.py — regression test for the 2026-08-16 index-alignment defect.

`SettlementProcessor.condition_df()` sorted the frame without resetting the index, so inside
`Technology.get_lcoe()` a positionally-labelled `peak_load` met a label-indexed `capacity_factor`
and every settlement's peak load was divided by a different settlement's capacity factor.
REPRODUCING.md §7 sets out the mechanism, why it stayed hidden, and what it cost.

The three checks below pin, in order: the pandas behaviour that caused it, that `condition_df()`
now leaves a clean RangeIndex, and that the model's own `NewCapacity2030` satisfies the closed
form `capacity = E / (ATR * GHI)`.

Run from the project root:
    python test/test_index_alignment.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUTDIR = REPO / "data" / "onsset_outputs"
RUN_LABEL = "2026-08_final_lcoe"
YEAR = 2030


def test_pandas_alignment_trap():
    """The exact pandas behaviour that caused the defect, pinned so it cannot be forgotten."""
    df = pd.DataFrame({"ghi": [2000.0, 2100.0, 2200.0], "y": [3.0, 1.0, 2.0]})
    df.sort_values("y", inplace=True)                 # permuted index, as condition_df did
    positional = pd.Series(np.array([10.0, 20.0, 30.0]))   # a numpy result, labelled by position

    wrong = positional / df["ghi"]                    # aligns on LABEL -> silently mispaired
    assert list(wrong.index) == [0, 1, 2]
    assert wrong.iloc[0] != positional.iloc[0] / df["ghi"].iloc[0], \
        "expected label-alignment to mispair the first row"

    df.reset_index(drop=True, inplace=True)           # the fix
    right = positional / df["ghi"]
    assert np.isclose(right.iloc[0], positional.iloc[0] / df["ghi"].iloc[0]), \
        "after reset_index, position and label must agree"
    print("  PASS  pandas alignment trap reproduced and shown to be closed by reset_index")


def test_condition_df_resets_index():
    """condition_df must leave a clean RangeIndex; skipped if onsset cannot be imported."""
    sys.path.insert(0, str(REPO / "data" / "onsset_repo"))
    try:
        from onsset import SettlementProcessor
    except Exception as exc:                                    # pragma: no cover
        msg = f"onsset not importable in this environment ({type(exc).__name__})"
        print(f"  SKIP  {msg}")
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:   # under pytest, report a real skip,
            import pytest                         # not a green pass for a check that
            pytest.skip(msg)                      # never executed
        return
    assert hasattr(SettlementProcessor, "_assert_positional_index"), \
        "the positional-index guard is missing from SettlementProcessor"
    import inspect
    src = inspect.getsource(SettlementProcessor.condition_df)
    assert "reset_index" in src, "condition_df no longer resets the index after sorting"
    print("  PASS  condition_df resets the index and the guard method is present")


def test_stand_alone_capacity_closed_form():
    """OnSSET sizes stand-alone PV as E / (ATR * GHI); the outputs must satisfy it."""
    path = OUTDIR / f"{RUN_LABEL}_R0.csv"
    assert path.exists(), (
        f"{path.name} not present. This test must FAIL, not skip, on a clean checkout: "
        f"a reviewer who has not run s06 must not see a green test suite for a check that "
        f"never executed. Run `python scripts/s06_run_arms.py` first.")
    df = pd.read_csv(path, usecols=[f"EnergyPerSettlement{YEAR}", "AverageToPeakLoadRatio",
                                    "GHI", f"FinalElecCode{YEAR}", f"NewCapacity{YEAR}"])
    predicted = df[f"EnergyPerSettlement{YEAR}"].to_numpy() / (
        df["AverageToPeakLoadRatio"].to_numpy() * df["GHI"].to_numpy())
    sa_pv = df[f"FinalElecCode{YEAR}"].to_numpy() == 3
    share = 100.0 * np.isclose(predicted[sa_pv], df[f"NewCapacity{YEAR}"].to_numpy()[sa_pv],
                               rtol=1e-6).mean()
    assert share > 99.0, (
        f"only {share:.3f}% of {int(sa_pv.sum()):,} stand-alone settlements satisfy "
        "capacity = E/(ATR*GHI). The frame index is permuted again — see this file's docstring.")
    print(f"  PASS  closed form reproduces {share:.3f}% of {int(sa_pv.sum()):,} "
          "stand-alone capacities")


def main():
    print("test_index_alignment.py")
    failures = 0
    for fn in (test_pandas_alignment_trap, test_condition_df_resets_index,
               test_stand_alone_capacity_closed_form):
        try:
            fn()
        except AssertionError as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failures += 1
    print("all checks passed" if not failures else f"{failures} check(s) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
