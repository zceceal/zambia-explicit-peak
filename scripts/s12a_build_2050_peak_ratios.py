"""
s12a_build_2050_peak_ratios.py — how much does population growth to 2050 erode the peak-to-energy
signal, and what does the central (uniform-growth) 2050 peak ratio look like per settlement?

Reads:  data/processed/zambia_grid3_spine_pe_n20.csv (central N_mid=20 spine, PE_ratio at 2030)
        data/processed/zambia_grid3_calib_distgate.csv (for IsUrban, to split urban/rural growth)
Writes (to the current working directory, not data/processed/):
  zambia_settlements_PE_2050_uniform.csv — the central-case (uniform growth) 2050 PE_ratio/N_hh,
    consumed by s12b to build the 2050 spine
  pe_2050_erosion_summary.csv — median/rural-median/pop-weighted PE_ratio and the "signal excess"
    (population-weighted mean of max(PE_ratio-2, 0)) under four growth scenarios: the 2035-static
    baseline, uniform 2050 growth, and two urban-share sensitivities (60%/63% of 2050 growth urban)

Usage:  python scripts/s12a_build_2050_peak_ratios.py [POP2050_total]   # default 34.5e6
"""
import pandas as pd, numpy as np, sys
from pathlib import Path
BASE = str(Path(__file__).resolve().parent.parent / "data" / "processed") + "/"
pe_df=pd.read_csv(BASE+"zambia_grid3_spine_pe_n20.csv")
cal=pd.read_csv(BASE+"zambia_grid3_calib_distgate.csv")[['id','IsUrban']].rename(columns={'IsUrban':'IsUrbanCal'})
df=pe_df.merge(cal,on='id',how='left')
urb=(df['IsUrbanCal']==2).values
Nhh=df['N_hh'].values; pop=df['Pop'].values; pe35=df['PE_ratio'].values
P1,PINF,PSTEP,NMID=3.98,1.45,2.43,20
beta=-np.log((PSTEP-PINF)/(P1-PINF))/np.log(NMID)
pe=lambda N: PINF+(P1-PINF)*np.power(np.maximum(N,1.0),-beta)
pop2020=pop.sum(); up=pop[urb].sum(); rp=pop[~urb].sum()

POP2050=float(sys.argv[1]) if len(sys.argv)>1 else 34.5e6
def proj(us=None):
    if us is None: r=np.full(len(df),POP2050/pop2020)
    else: r=np.where(urb,(us*POP2050)/up,((1-us)*POP2050)/rp)
    return Nhh*r, pop*r
rows=[]
for name,us in [("2035_static",None),("2050_uniform",-1),("2050_urban60",0.60),("2050_urban63",0.63)]:
    if name=="2035_static":
        pe_v, w = pe35, pop
    else:
        N50,w = proj(None if us==-1 else us); pe_v=pe(N50)
    e=np.average(np.maximum(pe_v-2,0),weights=w)
    rows.append(dict(scenario=name, median=np.median(pe_v), rural_median=np.median(pe_v[~urb]),
                     popwtd=np.average(pe_v,weights=w), signal_excess=e))
    # save the R1_2050 spine for the central (uniform) case, ready for OnSSET
    if name=="2050_uniform":
        out=pe_df.copy(); out['PE_ratio']=pe_v; out['N_hh']=proj(None)[0]
        out.to_csv("zambia_settlements_PE_2050_uniform.csv",index=False)
res=pd.DataFrame(rows)
base=res.loc[0,'signal_excess']
res['erosion_%']=(1-res['signal_excess']/base)*100
res.to_csv("pe_2050_erosion_summary.csv",index=False)
print(f"beta={beta:.4f}  POP2050={POP2050/1e6:.1f}M  ratio={POP2050/pop2020:.3f}")
print(res.round(3).to_string(index=False))
print("\nsaved: zambia_settlements_PE_2050_uniform.csv  +  pe_2050_erosion_summary.csv")
