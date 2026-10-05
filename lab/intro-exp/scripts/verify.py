#!/usr/bin/env python3
"""Validate saved experiment artifacts and render PDF pages for visual review."""
import csv
import json
from pathlib import Path
import numpy as np
from scipy.stats import t
from pypdf import PdfReader
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
plan = json.loads((ROOT / 'results/plan.json').read_text())
with (ROOT / 'results/measurements.csv').open() as f:
    rows = list(csv.DictReader(f))
summary = json.loads((ROOT / 'results/summary.json').read_text())
assert len(rows) == 4 * plan['final_n']
for s in summary:
    group = [r for r in rows if r['app'] == s['app'] and r['mode'] == s['mode']]
    assert len(group) == plan['final_n']
    assert sorted(int(r['run_id']) for r in group) == list(range(1, plan['final_n']+1))
    assert all(r['returncode'] == '0' and r['cache'] == 'warm' and r['graph'] == 'graph-rand.bin' for r in group)
    x = np.array([float(r['wall_s']) / int(r['iterations']) for r in group])
    half = t.ppf(.975, len(x)-1) * x.std(ddof=1) / np.sqrt(len(x))
    assert np.isclose(x.mean(), s['mean'])
    assert np.isclose(x.mean()-half, s['ci_low'])
    assert np.isclose(x.mean()+half, s['ci_high'])
    with (ROOT / f'results/{s["app"]}-{s["mode"]}.csv').open() as f:
        assert list(csv.DictReader(f)) == group
assert json.loads((ROOT / 'results/verification.json').read_text())['all_nodes_verified']
path = ROOT / 'output/pdf/report.pdf'
reader = PdfReader(path)
assert all(len(page.extract_text()) > 100 for page in reader.pages)
assert 'Read vs Write' in reader.pages[0].extract_text()
folder = ROOT / 'out/pdf-preview'
folder.mkdir(parents=True, exist_ok=True)
for i, page in enumerate(pdfium.PdfDocument(str(path))):
    page.render(scale=1.3).to_pil().save(folder / f'page-{i+1}.png')
print(f'OK: {len(rows)} final observations; four matching CSV; Student t intervals; {len(reader.pages)} PDF pages rendered.')
