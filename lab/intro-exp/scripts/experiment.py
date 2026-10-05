#!/usr/bin/env python3
"""Reproducible Read vs Write / Cache / 10M / Rand experiment (POSIX)."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
CONFIGS = [(app, mode) for app in ('graph_traverse', 'graph_traverse_mmap') for mode in ('read', 'write')]
FIELDS = ['timestamp', 'phase', 'app', 'mode', 'run_id', 'order', 'graph', 'cache', 'iterations', 'cpu_affinity', 'wall_s', 'user_s', 'sys_s', 'vol_ctx', 'invol_ctx', 'minflt', 'majflt', 'inblock', 'oublock', 'returncode', 'command']

def command(args):
    p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    return {'command': args, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}

def snapshot(name):
    commands = [['uname', '-a'], ['uptime'], ['df', '-h', str(ROOT)], ['clang', '--version']]
    if sys.platform == 'darwin':
        commands += [['sw_vers'], ['sysctl', 'hw.model', 'hw.memsize', 'hw.pagesize', 'hw.ncpu', 'hw.physicalcpu', 'hw.logicalcpu', 'machdep.cpu.brand_string', 'hw.perflevel0.physicalcpu', 'hw.perflevel1.physicalcpu'], ['vm_stat'], ['top', '-l', '1', '-n', '12', '-o', 'cpu'], ['diskutil', 'info', '/'], ['system_profiler', 'SPNVMeDataType'], ['pmset', '-g', 'batt']]
    else:
        commands += [['lscpu'], ['free', '-h'], ['lsblk', '-o', 'NAME,MODEL,SIZE,ROTA,TYPE,MOUNTPOINTS'], ['ps', '-eo', 'pid,comm,pcpu', '--sort=-pcpu']]
    entries = []
    for args in commands:
        try:
            entries.append(command(args))
        except OSError as exc:
            entries.append({'command': args, 'error': str(exc)})
    (RESULTS / f'environment-{name}.json').write_text(json.dumps({'timestamp': dt.datetime.now().astimezone().isoformat(), 'platform': sys.platform, 'commands': entries}, ensure_ascii=False, indent=2))

def verify_graph(path):
    data = path.read_bytes()
    magic, version, count, size, fanout, root, flags = struct.unpack_from('<8sIQIIQI', data)
    assert magic == b'GCACHEG1' and version == 1 and size == 24 and fanout == 1
    assert len(data) == 40 + count * size
    visited = bytearray(count)
    current = root
    same_page = 0
    page_size = os.sysconf('SC_PAGE_SIZE')
    for step in range(count):
        assert current < count and not visited[current]
        visited[current] = 1
        value, degree, reserved, child = struct.unpack_from('<qIIQ', data, 40 + current * size)
        assert degree == (0 if step == count - 1 else 1)
        if degree:
            same_page += (40 + current * size) // page_size == (40 + child * size) // page_size
            current = child
    return {'bytes': len(data), 'nodes': count, 'record_size': size, 'root': root, 'verified_nodes': sum(visited), 'same_page_edges': same_page, 'page_size': page_size, 'sha256': hashlib.sha256(data).hexdigest()}

def prepare():
    for directory in ('out', 'results', 'figures'):
        (ROOT / directory).mkdir(exist_ok=True)
    for app, _ in CONFIGS[::2]:
        args = ['clang', '-O2', '-Wall', '-Wextra', '-o', f'out/{app}', f'src/{app}.c']
        result = command(args)
        (RESULTS / f'build-{app}.json').write_text(json.dumps(result, indent=2))
        if result['returncode']:
            raise RuntimeError(result['stderr'])
    page_size = os.sysconf('SC_PAGE_SIZE')
    for topology, name in [('chain', 'rand'), ('sequential', 'seq')]:
        args = [sys.executable, '../util/graphgen.py', '-s', '10M', '--seed', '427', '--topology', topology, '-b', '0.5', '--min-step-pages', '2', '--page-size', str(page_size), '--verify', '-o', f'out/graph-{name}.bin']
        result = command(args)
        (RESULTS / f'generation-{name}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        if result['returncode']:
            raise RuntimeError(result['stderr'])
    info = {name: verify_graph(ROOT / f'out/graph-{name}.bin') for name in ('rand', 'seq')}
    (RESULTS / 'graphs.json').write_text(json.dumps(info, indent=2))
    print('Prepared and verified:', info, flush=True)

def measure(app, mode, iterations, phase, run_id, order, graph='rand', no_cache=False, core=None, prefix=None):
    args = [str(ROOT / 'out' / app)] + (['--write'] if mode == 'write' else []) + (['--no-cache'] if no_cache else []) + [str(iterations), str(ROOT / f'out/graph-{graph}.bin')]
    if core is not None:
        args = ['taskset', '-c', str(core)] + args
    if prefix:
        args = prefix + args
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter_ns()
    p = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    _, stderr = p.communicate()
    elapsed = (time.perf_counter_ns() - start) / 1e9
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    with (RESULTS / 'runs.log').open('a') as log:
        log.write(f'{phase}/{run_id}/{order}: {args!r}\n{stderr}\n')
    if p.returncode:
        raise RuntimeError(f'Failed {args}: {stderr}')
    expected = json.loads((RESULTS / 'graphs.json').read_text())[graph]['nodes']
    if stderr.count(f'OK ({expected} nodes processed)') != iterations:
        raise RuntimeError('Unexpected traversal coverage')
    row = dict(timestamp=dt.datetime.now().astimezone().isoformat(), phase=phase, app=app, mode=mode, run_id=run_id, order=order, graph=f'graph-{graph}.bin', cache='no-cache' if no_cache else 'warm', iterations=iterations, cpu_affinity=core if core is not None else 'uncontrolled', wall_s=elapsed, returncode=p.returncode, command=json.dumps(args))
    for field, attr in [('user_s', 'ru_utime'), ('sys_s', 'ru_stime'), ('vol_ctx', 'ru_nvcsw'), ('invol_ctx', 'ru_nivcsw'), ('minflt', 'ru_minflt'), ('majflt', 'ru_majflt'), ('inblock', 'ru_inblock'), ('oublock', 'ru_oublock')]:
        row[field] = getattr(after, attr) - getattr(before, attr)
    return row

def series(path, phase, n, iterations, rng, core):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for run in range(1, n + 1):
            configs = CONFIGS.copy()
            rng.shuffle(configs)
            for order, (app, mode) in enumerate(configs, 1):
                writer.writerow(measure(app, mode, iterations, phase, run, order, core=core))
                f.flush()
            print(f'{phase}: {run}/{n}', flush=True)

def collect(core):
    import numpy as np
    from scipy.stats import t
    rng = random.Random(427)
    snapshot('before')
    # Fixed protocol BEFORE observing measurements. No post hoc trimming.
    plan = {'variant': 'Read vs Write,Cache,10M,Rand', 'seed': 427, 'warmups_per_config': 2, 'pilot_n': 10, 'target_relative_halfwidth': 0.05, 'minimum_n': 30, 'maximum_n': 100, 'iterations': 5, 'cache': 'two complete warmup traversals per config; no eviction', 'metric': 'whole child process wall time / iterations', 'outliers': 'keep all successful runs', 'core': core, 'build': 'clang -O2 -Wall -Wextra', 'write_semantics': 'buffered updates; no fsync or msync in Cache mode', 'order': 'shuffle four configurations each round; seed 427'}
    (RESULTS / 'plan.json').write_text(json.dumps(plan, indent=2))
    series(RESULTS / 'warmup.csv', 'warmup', 2, 5, rng, core)
    series(RESULTS / 'pilot.csv', 'pilot', 10, 5, rng, core)
    rows = list(csv.DictReader((RESULTS / 'pilot.csv').open()))
    required = {}
    for app, mode in CONFIGS:
        x = np.array([float(r['wall_s']) / 5 for r in rows if r['app'] == app and r['mode'] == mode])
        n = 30
        for _ in range(100):
            next_n = max(30, int(np.ceil((t.ppf(.975, n - 1) * x.std(ddof=1) / (.05 * x.mean())) ** 2)))
            if next_n == n:
                break
            n = next_n
        required[f'{app}/{mode}'] = n
    n = min(100, max(required.values()))
    plan.update(pilot_required_n=required, final_n=n)
    (RESULTS / 'plan.json').write_text(json.dumps(plan, indent=2))
    snapshot('final-before')
    series(RESULTS / 'measurements.csv', 'final', n, 5, rng, core)
    snapshot('after')
    # Monitoring is separate from the statistical series.
    with (RESULTS / 'diagnostics.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for app, mode in CONFIGS:
            for graph in ('rand', 'seq'):
                writer.writerow(measure(app, mode, 1, 'baseline', 1, 1, graph=graph, core=core))
        prefix = ['/usr/bin/time', '-l'] if sys.platform == 'darwin' else ['/usr/bin/time', '-v']
        for run in range(1, 6):
            for app in ('graph_traverse', 'graph_traverse_mmap'):
                writer.writerow(measure(app, 'read', 5, 'monitor-bare', run, 1, core=core))
                writer.writerow(measure(app, 'read', 5, 'monitor-time', run, 2, core=core, prefix=prefix))
        # Own finite CPU worker only; always stopped in finally. rusage below
        # excludes it because the worker is reaped AFTER the measured child.
        worker = subprocess.Popen([sys.executable, '-c', 'import time\nend=time.monotonic()+30\nx=1\nwhile time.monotonic()<end: x=(x*1664525+1013904223)&0xffffffff'])
        try:
            time.sleep(.1)
            writer.writerow(measure('graph_traverse', 'read', 5, 'cpu-noise', 1, 1, core=core))
        finally:
            worker.terminate()
            worker.wait()
    # Verify writes changed ONLY values, with exactly the expected increment.
    final_rows = list(csv.DictReader((RESULTS / 'measurements.csv').open()))
    assert len(final_rows) == 4 * n
    assert all(int(r['returncode']) == 0 for r in final_rows)
    original = ROOT / 'out/verification-original.bin'
    p = command([sys.executable, '../util/graphgen.py', '-s', '10M', '--seed', '427', '--topology', 'chain', '-b', '0.5', '--min-step-pages', '2', '--page-size', str(os.sysconf('SC_PAGE_SIZE')), '-o', str(original)])
    if p['returncode']:
        raise RuntimeError(p['stderr'])
    old, new = original.read_bytes(), (ROOT / 'out/graph-rand.bin').read_bytes()
    increments = 2 * (2 + 10 + n) * 5 + 2  # both write apps plus baseline
    assert old[:40] == new[:40]
    for offset in range(40, len(old), 24):
        assert old[offset + 8:offset + 24] == new[offset + 8:offset + 24]
        assert struct.unpack_from('<q', new, offset)[0] == struct.unpack_from('<q', old, offset)[0] + increments
    (RESULTS / 'verification.json').write_text(json.dumps({'final_rows': len(final_rows), 'write_increment_each_node': increments, 'graph_structure_unchanged': True, 'all_nodes_verified': True}, indent=2))
    original.unlink()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'collect', 'all'])
    parser.add_argument('--core', type=int, help='Linux taskset core; default: scheduler controlled')
    args = parser.parse_args()
    if args.core is not None and not shutil.which('taskset'):
        parser.error('--core requires taskset')
    if args.action in ('prepare', 'all'):
        prepare()
    if args.action in ('collect', 'all'):
        collect(args.core)
