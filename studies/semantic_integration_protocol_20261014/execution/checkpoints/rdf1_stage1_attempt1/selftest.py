"""Independent tests using exclusively the released packet."""
import copy
import json
from pathlib import Path
import adapter as a

HERE = Path(__file__).resolve().parent
PACKET = HERE.parent.parent / 'packets' / 'stage1'
def load(name): return json.loads((PACKET / name).read_text())
providers = [load('providers/provider_a_v1.json'), load('providers/provider_b_v1.json')]
mapping = load('providers/boundary_mapping_v1.json')
classes = load('protocol/canonical_classes.json')
versions = {'A': '1.0', 'B': '1.0'}
checks = 0

def check(condition):
    global checks
    assert condition
    checks += 1

for ambient in (5, 25):
    payloads = load(f'fixtures/payloads_v1_{ambient}C.json')
    original = copy.deepcopy((providers, mapping, classes, payloads, versions))
    result = a.integrate(providers, mapping, classes, payloads, versions)
    check(result['status'] == 'accepted')
    check(len(a.query_all(result)) == 7)
    check(len(a.query_by_ancestor(result, 'EngineeringAsset')) == 7)
    check(len(a.query_by_ancestor(result, 'HeatRecovery')) == 3)
    check(a.query_by_ancestor(result, 'unknown') == [])
    check({b['boundary_id'] for b in a.query_returns(result, versions)} == {'cold_reheat', 'condensate'})
    check(a.query_returns(result, {'A': '9'})['error']['code'] == 'VERSION_MISMATCH')
    shuffled = a.integrate(list(reversed(providers)), dict(mapping, boundaries=list(reversed(mapping['boundaries']))), classes, list(reversed(payloads)), versions)
    check(shuffled == result)
    check(original == (providers, mapping, classes, payloads, versions))
    returned = a.query_all(result)
    returned[0]['producer']['namespace'] = 'changed'
    check(returned != a.query_all(result))

for q, value, unit, expected in [('temperature', 302.15, 'K', 29), ('pressure', 7, 'bar', .7), ('mass_flow', 1.25, 'kg/s', 4500)]:
    check(abs(a.normalize_quantity(q, value, unit) - expected) < 1e-9)
for q, value, unit in [('pressure', True, 'MPa'), ('temperature', 0, 'K'), ('pressure', 0, 'Pa'), ('mass_flow', float('inf'), 'kg/h'), ('mass_flow', -1, 'kg/s')]:
    try: a.normalize_quantity(q, value, unit)
    except ValueError: check(True)
    else: check(False)

def mutation(fn, code):
    args = copy.deepcopy([providers, mapping, classes, payloads, versions])
    fn(args)
    before = copy.deepcopy(args)
    result = a.integrate(*args)
    check(result.get('error', {}).get('code') == code)
    check('boundaries' not in result and bool(result['error']['detail']))
    check(args == before)

mutation(lambda x: x[1]['boundaries'].pop(), 'MISSING_BOUNDARY')
mutation(lambda x: x[1]['boundaries'][0]['producer'].pop('namespace'), 'AMBIGUOUS_MAPPING')
mutation(lambda x: x[1]['boundaries'].append(dict(x[1]['boundaries'][0], producer=x[1]['boundaries'][1]['producer'])), 'AMBIGUOUS_MAPPING')
mutation(lambda x: x[1]['boundaries'][1].update(producer=x[1]['boundaries'][0]['producer']), 'DUPLICATE_BOUNDARY')
mutation(lambda x: x[0][0]['types'][0].update(parent_type_id='GasTurbine'), 'UNRESOLVED_CLASS')
mutation(lambda x: x[0][0]['types'][0].update(parent_type_id='absent'), 'UNRESOLVED_CLASS')
mutation(lambda x: x[0][0]['field_sets']['state'][0].update(unit='MPa'), 'INCOMPATIBLE_UNIT')
mutation(lambda x: x[1]['field_mappings'].append(dict(x[1]['field_mappings'][0], canonical_quantity='pressure')), 'AMBIGUOUS_MAPPING')
mutation(lambda x: x[3][0]['fields'].update(temp=True), 'INVALID_VALUE')
mutation(lambda x: x[3][0]['fields'].update(extra=1), 'INVALID_SCHEMA')
mutation(lambda x: x[3].append(copy.deepcopy(x[3][0])), 'INVALID_SCHEMA')
mutation(lambda x: x[3][0].update(schema_version='2.0'), 'VERSION_MISMATCH')
mutation(lambda x: x[3][0].pop('composition'), 'INVALID_SCHEMA')
mutation(lambda x: x[3][0]['composition'].update(N2=.1), 'INVALID_VALUE')
mutation(lambda x: x[3][0]['fields'].update(temp=400), 'INVALID_VALUE')
repeat = copy.deepcopy(mapping)
repeat['boundaries'] += copy.deepcopy(repeat['boundaries'])
repeat['field_mappings'] += copy.deepcopy(repeat['field_mappings'])
check(a.integrate(providers, repeat, classes, payloads, versions)['status'] == 'accepted')
if not (HERE / 'native_v1.ttl').exists():
    a.export_native(providers, mapping, classes, HERE / 'native_v1.ttl')
print(f'{checks} independent checks passed; native_v1.ttl available')
