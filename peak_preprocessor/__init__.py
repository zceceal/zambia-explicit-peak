"""
peak_preprocessor — R1 demand pre-processor for the Zambia OnSSET peak-vs-energy study.

Public API:
    pe_from_n(N, N_mid=20, P_1=3.98, P_inf=1.45, P_step=2.43)
    compute_beta(N_mid, P_1=3.98, P_inf=1.45, P_step=2.43)
"""
from .pe_diversity import pe_from_n, compute_beta  # noqa: F401 — re-exported as the package API
