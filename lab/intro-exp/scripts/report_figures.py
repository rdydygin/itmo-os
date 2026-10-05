#!/usr/bin/env python3
"""Compact Russian figures for the Typst report, based on final CSV only."""
import csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parents[1]
summary=json.loads((root/'results/summary.json').read_text())
with (root/'results/measurements.csv').open() as f: rows=list(csv.DictReader(f))
plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False})
colors=['#226a91','#b54f2f']
fig,axes=plt.subplots(1,2,figsize=(6.5,1.85),layout='constrained')
for ax,start,name in zip(axes,[0,2],['read/lseek','mmap']):
    for y,i in enumerate(range(start,start+2)):
        s=summary[i]
        ax.errorbar(s['mean']*1000,y,xerr=s['half']*1000,fmt='o',color=colors[y],capsize=5)
        ax.annotate(f"{s['mean']*1000:.3f}",(s['mean']*1000,y),xytext=(0,10),textcoords='offset points',ha='center',fontsize=9)
    ax.set_yticks([0,1],['Read','Write'])
    ax.set_ylim(1.5,-.6)
    ax.set(title=name,xlabel='Время, мс')
    if start==0: ax.set_xlim(0,1250)
    else: ax.set_xlim(5.05,5.5)
    ax.grid(axis='x',alpha=.2)
fig.savefig(root/'figures/brief-comparison.svg'); plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(6.5,1.8),layout='constrained')
for ax,start,name in zip(axes,[0,2],['read/lseek','mmap']):
    groups=[np.array([float(r['wall_s'])/int(r['iterations'])*1000 for r in rows if r['app']==s['app'] and r['mode']==s['mode']]) for s in summary[start:start+2]]
    bins=np.histogram_bin_edges(np.concatenate(groups),bins='auto')
    for x,label,color in zip(groups,['Read','Write'],colors): ax.hist(x,bins=bins,density=True,alpha=.5,color=color,label=label)
    ax.set(title=name,xlabel='Время, мс',ylabel='Плотность, 1/мс')
    ax.legend(fontsize=8,frameon=False)
fig.savefig(root/'figures/brief-distributions.svg');plt.close(fig)
