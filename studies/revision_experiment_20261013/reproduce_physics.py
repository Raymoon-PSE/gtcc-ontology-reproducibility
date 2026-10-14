"""Rerun three linked-cycle physical baselines against frozen numerical records.

This does not execute mechanical diagnostics or the ontology runtime. Run from
any directory. A JSON result is printed; optional --output saves that result.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import math
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'source_snapshot'))
sys.path.insert(0, str(ROOT))
from benchmark.physics import run_physics, summarize


def compare(actual, expected, path='physical'):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys(), path
        return sum(compare(actual[k], v, f'{path}.{k}') for k, v in expected.items())
    if isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        return sum(compare(a, e, f'{path}[{i}]') for i, (a, e) in enumerate(zip(actual, expected)))
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        assert type(actual) is type(expected) and actual == expected, (path, actual, expected)
    elif isinstance(expected, (int, float)):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool), path
        assert math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-6), (path, actual, expected)
    else:
        raise TypeError((path, type(expected)))
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'PHYSICS_SOURCE_MANIFEST.json').read_text())
    for entry in manifest['files']:
        p = ROOT / 'source_snapshot' / entry['path']
        assert hashlib.sha256(p.read_bytes()).hexdigest() == entry['public_sha256'], entry['path']
    oracle = json.loads((ROOT / 'results/main/oracles.json').read_text())
    runs = []
    for ambient in (5, 15, 25):
        output, result = run_physics(ambient)
        actual = summarize(output, result)
        leaves = compare(actual, oracle[str(ambient)]['physical'])
        assert actual['converged']
        assert abs(actual['cycle_water_audit']['external_mass_residual_kg_hr']) < 1e-6
        assert abs(actual['cycle_water_audit']['external_energy_residual_kW']) < 0.01
        assert actual['hrsg_local_balances_passed']
        assert actual['hrsg_endpoint_screen_passed']
        assert len(actual['streams']) == 7 and all(v > 0 for v in actual['boundary_calls'].values())
        runs.append({'ambient_C': ambient, 'matched_scalar_leaves': leaves,
                     'W_net_kW': actual['W_net_kW'], 'converged': True,
                     'physical': actual, 'status': 'passed'})
    report = {'scope': 'Fresh linked-cycle physics only; no mechanical or ontology-runtime execution.',
              'relative_tolerance': 1e-10, 'absolute_tolerance': 1e-6,
              'verified_source_files': len(manifest['files']),
              'packages': {p: importlib.metadata.version(p) for p in ('numpy','scipy','CoolProp')},
              'runs': runs}
    text = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text)

if __name__ == '__main__':
    main()
