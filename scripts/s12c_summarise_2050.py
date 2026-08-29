"""
s12c_summarise_2050.py — energy-weighted DeltaLCOE% and technology split for one R0/R1 arm pair at
a given analysis year. No re-solve: reads the two per-settlement CSVs s12_run_2050_horizon.py wrote
and prints the same headline summary s14_paper_numbers.py prints for the 2030 arms, at whichever
year column is given (used for the 2050 horizon; also works on any other single-year arm pair).

Reads:  <R0.csv>, <R1.csv> — two per-settlement OnSSET output CSVs with matching settlement rows
Writes: nothing; prints to stdout only

Usage:  python scripts/s12c_summarise_2050.py <R0.csv> <R1.csv> [YEAR]   # default YEAR=2030
"""
import pandas as pd, numpy as np, sys
r0=pd.read_csv(sys.argv[1]); r1=pd.read_csv(sys.argv[2]); yr=sys.argv[3] if len(sys.argv)>3 else '2030'
def ew(d):
    lc=d[f'MinimumOverallLCOE{yr}'].values; e=d[f'EnergyPerSettlement{yr}'].values
    m=np.isfinite(lc)&np.isfinite(e)&(e>0); return np.average(lc[m],weights=e[m])
a,b=ew(r0),ew(r1)
sw=int((r0[f'Technology{yr}'].values!=r1[f'Technology{yr}'].values).sum())
print(f"{yr}: R0 EW-LCOE={a:.4f}  R1={b:.4f}  dLCOE={100*(b-a)/a:+.1f}%  switches={sw}")
for d,n in [(r0,'R0'),(r1,'R1')]:
    g=d[f'Pop{yr}'].groupby(d[f'Technology{yr}']).sum(); print(f"  {n} split%:",(g/g.sum()*100).round(1).to_dict())
