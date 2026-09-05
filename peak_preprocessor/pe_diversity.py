"""
Diversity / coincidence peak-to-energy (P/E) sub-model for the R1 pre-processor.

Model form
----------
After-diversity P/E as a function of the number of household connections N:

    P/E(N) = P_inf + (P_1 - P_inf) * N ** (-beta)

P/E is the peak-to-mean-power ratio (inverse load factor).  As N grows from 1
toward infinity, P/E falls monotonically from P_1 toward P_inf because
individual household peaks do not coincide.

Anchor values — Lorenzoni et al. 2020, Table 2
-----------------------------------------------
Measured on 61 isolated mini-grids across developing countries worldwide
(NOT sub-Saharan-Africa-specific; the dataset is global).  Values are by load
archetype, NOT by connection count — see the N_mid note below.  Table 2 gives
the per-cluster normalised peak (mean ± SD): Flat 1.45±0.26, Step 2.03±0.29,
Step-peak 2.43±0.23, Peak 3.98±0.46, Outliers 2.58±0.62.

    P_1    = 3.98  (±0.46)  "Peak" archetype      — satisfied at N = 1
    P_inf  = 1.45  (±0.26)  "Flat" archetype       — approached as N → ∞
    P_step = 2.43  (±0.23)  "Step-peak" archetype  — used to calibrate beta

Beta calibration
----------------
beta is derived analytically by requiring P/E(N_mid) == P_step:

    beta = -ln((P_step - P_inf) / (P_1 - P_inf)) / ln(N_mid)
         = 0.9484 / ln(N_mid)        (for the default anchor values)

N_mid is a *stated assumption*, not a measured quantity.  Lorenzoni reports
archetypes, not connection counts, so N_mid cannot be read from the data.
Central case: N_mid = 20 (beta ≈ 0.317).  Sensitivity sweep: {10, 20, 50}.

References
----------
Lorenzoni, L., Cherubini, P., Fioriti, D., Poli, D., Micangeli, A. &
Giglioli, R. (2020). "Classification and modeling of load profiles of isolated
mini-grids in developing countries: a data-driven approach."  Energy for
Sustainable Development, 59, 208-225.  doi:10.1016/j.esd.2020.10.001.  Table 2.
"""

import math
import numpy as np

# ── Lorenzoni 2020 Table 2 anchors (do not change without updating citation) ─
P_1_DEFAULT    = 3.98   # "Peak" archetype;      SD ±0.46
P_INF_DEFAULT  = 1.45   # "Flat" archetype;      SD ±0.26
P_STEP_DEFAULT = 2.43   # "Step-peak" archetype; SD ±0.23

# SDs — stored here for the calibration figure; not used in pe_from_n itself
SD_P_1    = 0.46
SD_P_INF  = 0.26
SD_P_STEP = 0.23

# Swept N_mid values (central case first)
N_MID_SWEEP   = [20, 10, 50]
N_MID_CENTRAL = 20


def compute_beta(
    N_mid: float,
    P_1: float = P_1_DEFAULT,
    P_inf: float = P_INF_DEFAULT,
    P_step: float = P_STEP_DEFAULT,
) -> float:
    """
    Derive beta analytically so that pe_from_n(N_mid) == P_step.

    beta = -ln((P_step - P_inf) / (P_1 - P_inf)) / ln(N_mid)

    Parameters
    ----------
    N_mid : float
        Assumed connection count at which P/E equals the Step-peak archetype.
        Must be > 1.  Stated assumption, not a measured value.

    Returns
    -------
    float
        Shape exponent beta > 0.
    """
    if N_mid <= 1.0:
        raise ValueError(f"N_mid must be > 1; got {N_mid!r}")
    if not (P_inf < P_step < P_1):
        raise ValueError(
            f"Anchors must satisfy P_inf < P_step < P_1; "
            f"got P_inf={P_inf}, P_step={P_step}, P_1={P_1}"
        )
    log_ratio = math.log((P_step - P_inf) / (P_1 - P_inf))
    return -log_ratio / math.log(N_mid)


def pe_from_n(
    N,
    N_mid: float = N_MID_CENTRAL,
    P_1: float = P_1_DEFAULT,
    P_inf: float = P_INF_DEFAULT,
    P_step: float = P_STEP_DEFAULT,
):
    """
    After-diversity P/E ratio for N household connections.

    Implements: P/E(N) = P_inf + (P_1 - P_inf) * N ** (-beta)
    where beta is derived analytically from the Step-peak anchor and N_mid.

    Parameters
    ----------
    N : float or array-like
        Number of household connections (>= 1).  Accepts scalars or NumPy arrays.
    N_mid : float
        Assumed N at which P/E == P_step (Step-peak archetype).
        Central case 20; sensitivity sweep {10, 20, 50}.
        This is a stated assumption, not a measured value.
    P_1, P_inf, P_step : float
        Lorenzoni 2020 Table 2 anchors.  Override only in tests or sensitivity
        analysis; use defaults for the main analysis.

    Returns
    -------
    float or ndarray
        P/E ratio in [P_inf, P_1], same shape as N.

    Raises
    ------
    ValueError
        If any element of N < 1, or if N_mid <= 1, or if anchors are inconsistent.

    Notes
    -----
    Anchors, their source and the beta identity: see the module docstring above.
    """
    N_arr = np.asarray(N, dtype=float)
    scalar = N_arr.ndim == 0
    N_arr = np.atleast_1d(N_arr)

    if np.any(N_arr < 1.0):
        raise ValueError(f"All N must be >= 1; min supplied = {N_arr.min()}")

    beta = compute_beta(N_mid, P_1=P_1, P_inf=P_inf, P_step=P_step)
    result = P_inf + (P_1 - P_inf) * N_arr ** (-beta)

    return float(result[0]) if scalar else result
