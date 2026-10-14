"""Arm-local tests using released material and independently written mutations only."""
import json
import math
from copy import deepcopy
from pathlib import Path
import adapter as a

PACKET = Path(__file__).resolve().parents[2] / 'packets' / 'stage0'
HERE = Path(__file__).resolve().parent

def load(name):
    return json.loads((PACKET / name).read_text())

def inputs(temp='5'):
    return [[load('providers/provider_a_v1.json'), load('providers/provider_b_v1.json')],
            load('providers/boundary_mapping_v1.json'), load('protocol/canonical_classes.json'),
            load('fixtures/payloads_v1_' + temp + 'C.json'), {'A': '1.0', 'B': '1.0'}]

checks = []
def check(label, args, code=None):
    before = deepcopy(args)
    result = a.integrate(*args)
    assert args == before, label + ': mutated input'
    if code:
        assert result['status'] == 'rejected', (label, result)
        assert result['error']['code'] == code, (label, result)
        assert result['error']['detail'] and 'boundaries' not in result
    else:
        assert result['status'] == 'accepted', (label, result)
    checks.append(label)
    return result

for ambient in ('5', '25'):
    args = inputs(ambient)
    r = check('released baseline ' + ambient, args)
    fixture = load('fixtures/whole_cycle.json')[ambient]['streams']
    for b in r['boundaries']:
        for q in ('T', 'P', 'm_dot'):
            assert math.isclose(b[q], fixture[b['boundary_id']][q], abs_tol=1e-6, rel_tol=1e-10)
        assert b['w'] == fixture[b['boundary_id']]['w']
    for cls, expected in {'EngineeringAsset': a.BOUNDARIES, 'GasTurbine': {'gt_exhaust'},
                          'HeatRecovery': {'hp_steam', 'hot_reheat', 'lp_steam'},
                          'SteamExpansion': {'cold_reheat', 'st_exhaust'}, 'HeatSink': {'condensate'},
                          'unknown': set()}.items():
        assert {b['boundary_id'] for b in a.query_by_ancestor(r, cls)} == set(expected)
    assert {b['boundary_id'] for b in a.query_returns(r, args[4])} == {'cold_reheat', 'condensate'}
    assert a.query_returns(r, {'A': '3.0', 'B': '1.0'})['error']['code'] == 'VERSION_MISMATCH'
    baseline = deepcopy(r)
    a.query_all(r)[0]['w'].clear()
    assert baseline == r
    shuffled = deepcopy(args)
    shuffled[0].reverse()
    shuffled[1]['boundaries'].reverse()
    shuffled[1]['field_mappings'].reverse()
    shuffled[2]['provider_type_mappings'].reverse()
    shuffled[3].reverse()
    for p in shuffled[0]:
        for key in ('types', 'ports', 'equipment'):
            p[key].reverse()
    assert check('order independence ' + ambient, shuffled) == baseline

for q, v, u, expected in [('temperature', 300, 'K', 26.85), ('pressure', 200000, 'Pa', .2),
                            ('pressure', 1, 'bar', .1), ('mass_flow', 2, 'kg/s', 7200)]:
    assert math.isclose(a.normalize_quantity(q, v, u), expected, abs_tol=1e-10)
for q, v, u in [('temperature', -273.15, 'degC'), ('pressure', 0, 'Pa'), ('mass_flow', -1, 'kg/h'),
                 ('temperature', True, 'K'), ('pressure', float('inf'), 'bar'), ('mass_flow', 2, 'bar')]:
    try:
        a.normalize_quantity(q, v, u)
    except ValueError:
        pass
    else:
        raise AssertionError((q, v, u))

x = inputs(); x[1]['boundaries'].pop(); check('missing boundary', x, 'MISSING_BOUNDARY')
x = inputs(); x[1]['boundaries'][1]['producer'] = deepcopy(x[1]['boundaries'][0]['producer']); check('endpoint reuse', x, 'DUPLICATE_BOUNDARY')
x = inputs(); m = deepcopy(x[1]['boundaries'][0]); m['producer'] = deepcopy(x[1]['boundaries'][1]['producer']); x[1]['boundaries'].append(m); check('mapping conflict', x, 'AMBIGUOUS_MAPPING')
x = inputs(); x[1]['boundaries'] += deepcopy(x[1]['boundaries']); x[1]['field_mappings'] += deepcopy(x[1]['field_mappings']); check('idempotent mapping assertions', x)
x = inputs(); x[0][0]['types'] += deepcopy(x[0][0]['types']); x[0][0]['ports'] += deepcopy(x[0][0]['ports']); check('idempotent native assertions', x)
x = inputs(); x[0][0]['types'][0]['parent_type_id'] = 'GasTurbine'; check('cycle', x, 'UNRESOLVED_CLASS')
x = inputs(); x[0][0]['types'][0]['parent_type_id'] = 'not_declared'; check('missing parent', x, 'UNRESOLVED_CLASS')
x = inputs(); x[1]['field_mappings'][0]['declared_unit'] = 'K'; check('unit metadata conflict', x, 'INCOMPATIBLE_UNIT')
x = inputs(); f = deepcopy(x[1]['field_mappings'][0]); f['canonical_quantity'] = 'pressure'; x[1]['field_mappings'].append(f); check('quantity mapping conflict', x, 'AMBIGUOUS_MAPPING')
x = inputs(); del x[1]['boundaries'][0]['producer']['namespace']; check('missing namespace', x, 'AMBIGUOUS_MAPPING')
x = inputs(); x[3][0]['fields']['temp'] += 1; check('endpoint scalar disagreement', x, 'INVALID_VALUE')
x = inputs(); x[3][0]['fields']['temp'] = True; check('boolean value', x, 'INVALID_VALUE')
x = inputs(); x[3][0]['fields']['extra'] = 1; check('undeclared payload alias', x, 'INVALID_SCHEMA')
x = inputs(); x[3].append(deepcopy(x[3][0])); check('duplicate observation', x, 'INVALID_SCHEMA')
x = inputs(); x[3][0]['schema_version'] = '2.0'; check('payload revision', x, 'VERSION_MISMATCH')
x = inputs(); x[4]['A'] = '2.0'; check('requested revision', x, 'VERSION_MISMATCH')
x = inputs(); x[0][0]['types'].append({'local_type_id': 'SpecialGT', 'parent_type_id': 'GasTurbine'}); x[0][0]['equipment'][0]['local_type_id'] = 'SpecialGT'; check('new transitive leaf', x)

# Verify the representation is operational: graph mutation affects resolution.
x = inputs(); g = a.import_graph(*x[:3]); ep = a.node('equipment', 'A', 'GT01')
assert 'GasTurbine' in a.classes(g, ep)[1]
g.remove((a.node('type', 'A', 'GasTurbine'), a.N.canonicalClass, None))
assert 'GasTurbine' not in a.classes(g, ep)[1]
triples = a.export_native(*inputs()[:3], HERE / 'export_native' / 'native_v1.ttl')
report = {'status': 'passed', 'independent_checks': checks, 'check_count': len(checks),
          'additional_checks': 'physical fixture quantities, all query sets, numeric domains, graph causality',
          'native_triples': triples}
(HERE / 'selftest_results.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
