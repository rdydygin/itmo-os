#!/usr/bin/env python3
"""Process saved measurements, write statistical summaries and draw charts."""
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import t

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
CONFIGS = [(app, mode) for app in ('graph_traverse', 'graph_traverse_mmap') for mode in ('read', 'write')]
LABELS = ['read/lseek: Read', 'read/lseek: Write', 'mmap: Read', 'mmap: Write']
COLORS = ['#2379a5', '#d36231', '#2379a5', '#d36231']

def load(name):
    with (RESULTS / name).open() as f:
        return list(csv.DictReader(f))

def stats(x):
    x = np.array(x, dtype=float)
    n = len(x)
    mean = float(x.mean())
    std = float(x.std(ddof=1))
    half = float(t.ppf(.975, n - 1) * std / math.sqrt(n))
    return dict(n=n, mean=mean, std=std, ci_low=mean-half, ci_high=mean+half, half=half, relative_half=half/mean, median=float(np.median(x)), iqr=float(np.percentile(x, 75)-np.percentile(x, 25)), target_n=max(2, math.ceil((1.96*std/(.05*mean))**2)))

def main():
    rows = load('measurements.csv')
    plan = json.loads((RESULTS / 'plan.json').read_text())
    groups, summaries = [], []
    for app, mode in CONFIGS:
        group = [r for r in rows if r['app'] == app and r['mode'] == mode]
        assert len(group) == plan['final_n']
        assert all(r['cache'] == 'warm' and r['graph'] == 'graph-rand.bin' for r in group)
        x = [float(r['wall_s']) / int(r['iterations']) for r in group]
        groups.append(x)
        s = stats(x)
        s.update(app=app, mode=mode)
        for field in ['user_s', 'sys_s', 'vol_ctx', 'invol_ctx', 'minflt', 'majflt', 'inblock', 'oublock']:
            s[field] = float(np.mean([float(r[field]) for r in group]))
        summaries.append(s)
        with (RESULTS / f'{app}-{mode}.csv').open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(group)
    (RESULTS / 'summary.json').write_text(json.dumps(summaries, indent=2))
    with (RESULTS / 'summary.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=summaries[0].keys())
        w.writeheader()
        w.writerows(summaries)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), layout='constrained')
    for ax, start, name in zip(axes, [0, 2], ['read/lseek', 'mmap (zoom)']):
        for local, i in enumerate(range(start, start+2)):
            s = summaries[i]
            ax.errorbar(s['mean']*1000, local, xerr=s['half']*1000, fmt='o', capsize=7, color=COLORS[i], markersize=7)
            ax.annotate(f"{s['mean']*1000:.3f} ± {s['half']*1000:.3f} ms", (s['mean']*1000, local), xytext=(0, 18), textcoords='offset points', ha='center', fontsize=8)
        ax.set_yticks([0, 1], ['Read', 'Write'])
        ax.set_ylim(1.5, -.6)
        ax.set_xlabel('Wall time per traversal (ms)')
        if start == 0:
            ax.set_xlim(0, summaries[1]['ci_high']*1150)
        else:
            low = min(s['ci_low'] for s in summaries[2:])*1000
            high = max(s['ci_high'] for s in summaries[2:])*1000
            ax.set_xlim(low-.1, high+.1)
        ax.grid(axis='x', alpha=.2)
        ax.set_title(name)
    fig.suptitle(f'Read vs Write / Cache / 10 MiB / Random; N={plan["final_n"]}; 95% CI')
    fig.savefig(ROOT / 'figures/comparison.png', dpi=180)
    fig.savefig(ROOT / 'figures/comparison.svg')
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.7), layout='constrained')
    for ax, start, label in zip(axes, [0, 2], ['read/lseek', 'mmap']):
        bins = np.histogram_bin_edges(np.concatenate(groups[start:start+2])*1000, bins='auto')
        for index in range(start, start+2):
            ax.hist(np.array(groups[index])*1000, bins=bins, density=True, alpha=.5, label=CONFIGS[index][1], color=COLORS[index])
        ax.set(title=label, xlabel='Wall time per traversal (ms)', ylabel='Probability density (1/ms)')
        ax.legend()
    fig.savefig(ROOT / 'figures/distributions.png', dpi=180)
    fig.savefig(ROOT / 'figures/distributions.svg')
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(9, 4.8), layout='constrained')
    for ax, x, label, color in zip(axes.flat, groups, LABELS, COLORS):
        ax.plot(range(1, len(x)+1), np.array(x)*1000, '.-', color=color, linewidth=.7)
        ax.set(title=label, xlabel='Round', ylabel='ms per traversal')
    fig.savefig(ROOT / 'figures/run-order.png', dpi=180)
    plt.close(fig)
    # Diagnostic estimates belong to analysis, not report rendering.
    diagnostic_rows = load('diagnostics.csv')
    monitoring = {}
    for app in ('graph_traverse', 'graph_traverse_mmap'):
        monitoring[app] = {}
        for name, phase in [('bare', 'monitor-bare'), ('time', 'monitor-time')]:
            x = [float(row['wall_s']) / int(row['iterations'])
                 for row in diagnostic_rows if row['app'] == app and row['phase'] == phase]
            monitoring[app][name] = stats(x)
    noise = next(row.copy() for row in diagnostic_rows if row['phase'] == 'cpu-noise')
    noise['wall_per_traversal_s'] = float(noise['wall_s']) / int(noise['iterations'])
    (RESULTS / 'diagnostics-summary.json').write_text(json.dumps(
        {'monitoring': monitoring, 'cpu_noise': noise}, indent=2))
    print(f'Processed {len(rows)} final observations: summaries in results/, charts in figures/.')


if __name__ == '__main__':
    main()
