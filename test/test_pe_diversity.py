"""
Unit tests for pe_diversity.py.

Run with:  python -m pytest test_pe_diversity.py -v
Or standalone:  python test_pe_diversity.py
"""
import math
import sys
import os
import numpy as np

# Allow running from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe_diversity import (
    pe_from_n, compute_beta,
    P_1_DEFAULT, P_INF_DEFAULT, P_STEP_DEFAULT,
    N_MID_SWEEP,
)

P_1    = P_1_DEFAULT
P_INF  = P_INF_DEFAULT
P_STEP = P_STEP_DEFAULT
TOL    = 1e-9   # float tolerance for exact-anchor checks


# ── 1. P/E(1) == P_1 for every swept N_mid ──────────────────────────────────
def test_anchor_n1_all_sweeps():
    for n_mid in N_MID_SWEEP:
        result = pe_from_n(1.0, N_mid=n_mid)
        assert abs(result - P_1) < TOL, (
            f"N=1, N_mid={n_mid}: pe_from_n={result:.10f} != P_1={P_1}"
        )

# ── 2. P/E(N_mid) == P_STEP — the calibration identity ──────────────────────
def test_beta_reproduces_p_step_all_sweeps():
    """The analytic beta must exactly recover P_step at N_mid."""
    for n_mid in N_MID_SWEEP:
        result = pe_from_n(float(n_mid), N_mid=n_mid)
        assert abs(result - P_STEP) < 1e-10, (
            f"N=N_mid={n_mid}: pe_from_n={result:.12f} != P_STEP={P_STEP}"
        )

# ── 3. Monotonically decreasing ──────────────────────────────────────────────
def test_monotone_decreasing():
    N_vals = [1, 2, 5, 10, 20, 50, 100, 500, 1000, 5000]
    pe_vals = [pe_from_n(n) for n in N_vals]
    for i in range(len(pe_vals) - 1):
        assert pe_vals[i] > pe_vals[i + 1], (
            f"Not strictly decreasing: pe({N_vals[i]})={pe_vals[i]:.6f} "
            f">= pe({N_vals[i+1]})={pe_vals[i+1]:.6f}"
        )

# ── 4. Every output in [P_INF, P_1] ─────────────────────────────────────────
def test_output_bounds():
    N_vals = np.array([1, 2, 5, 10, 50, 100, 500, 1000, 5000, 1e5], dtype=float)
    pe_vals = pe_from_n(N_vals)
    EPS = 1e-10  # float arithmetic at N=1 may land epsilon above stored P_1
    assert np.all(pe_vals >= P_INF - EPS), (
        f"Values below P_INF={P_INF}: {pe_vals[pe_vals < P_INF - EPS]}"
    )
    assert np.all(pe_vals <= P_1 + EPS), (
        f"Values above P_1={P_1}: {pe_vals[pe_vals > P_1 + EPS]}"
    )

# ── 5. N < 1 raises ValueError ───────────────────────────────────────────────
def test_n_below_1_raises():
    for bad in [0.0, 0.5, -1.0]:
        try:
            pe_from_n(bad)
            assert False, f"Should have raised ValueError for N={bad}"
        except ValueError:
            pass

# ── 6. N_mid <= 1 raises ValueError ─────────────────────────────────────────
def test_n_mid_le_1_raises():
    for bad in [0.0, 1.0, -5.0]:
        try:
            compute_beta(bad)
            assert False, f"Should have raised ValueError for N_mid={bad}"
        except ValueError:
            pass

# ── 7. Approaches P_INF at large N ──────────────────────────────────────────
def test_approaches_p_inf_large_n():
    # With beta≈0.317, N must be very large to converge; N=1e10 gives pe≈1.452
    v = pe_from_n(1e10)
    assert abs(v - P_INF) < 0.005, (
        f"At N=1e10 expected ~P_INF={P_INF}, got {v:.6f}"
    )

# ── 8. Vectorised call returns correct shape ─────────────────────────────────
def test_vectorised_shape():
    N_arr = np.array([1.0, 10.0, 100.0, 1000.0])
    result = pe_from_n(N_arr)
    assert result.shape == N_arr.shape, f"Shape mismatch: {result.shape}"

# ── Run standalone ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        test_anchor_n1_all_sweeps,
        test_beta_reproduces_p_step_all_sweeps,
        test_monotone_decreasing,
        test_output_bounds,
        test_n_below_1_raises,
        test_n_mid_le_1_raises,
        test_approaches_p_inf_large_n,
        test_vectorised_shape,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} tests passed.")
    if failed:
        sys.exit(1)
