"""Self-authored checks against released contract; no acceptance-suite imports."""
import copy
import json
from pathlib import Path
import adapter

ROOT = Path(__file__).resolve().parent
PACKET = ROOT.parents[1] / 'packets' / 'stage0'
def read(path):
    return json.loads((PACKET / path).read_text())
providers = [read('providers/provider_a_v1.json'), read('providers/provider_b_v1.json')]
mapping = read('providers/boundary_mapping_v1.json')
canonical = read('protocol/canonical_classes.json')
versions = {'A': '1.0', 'B': '1.0'}
for ambient in (5, 25):
    payloads = read(f'fixtures/payloads_v1_{ambient}C.json')
    args = [providers, mapping, canonical, payloads, versions]
    saved = copy.deepcopy(args)
    result = adapter.integrate(*args)
    assert result['status'] == 'accepted', result
    assert len(adapter.query_all(result)) == 7
    assert len(adapter.query_by_ancestor(result, 'EngineeringAsset')) == 7
    assert len(adapter.query_by_ancestor(result, 'GasTurbine')) == 1
    assert len(adapter.query_by_ancestor(result, 'HeatRecovery')) == 3
    assert len(adapter.query_returns(result, versions)) == 2
    assert adapter.query_returns(result, {'A': '0.0'})['error']['code'] == 'VERSION_MISMATCH'
    assert args == saved
    reordered = copy.deepcopy(args)
    reordered[0].reverse()
    reordered[1]['boundaries'].reverse()
    reordered[1]['field_mappings'].reverse()
    reordered[3].reverse()
    for p in reordered[0]:
        p['types'].reverse()
        p['ports'].reverse()
    assert adapter.integrate(*reordered) == result
    duplicate = copy.deepcopy(args)
    duplicate[1]['boundaries'].append(copy.deepcopy(duplicate[1]['boundaries'][0]))
    duplicate[0][0]['types'].append(copy.deepcopy(duplicate[0][0]['types'][0]))
    assert adapter.integrate(*duplicate) == result
    def negative(change, code):
        altered = copy.deepcopy(args)
        change(altered)
        before = copy.deepcopy(altered)
        actual = adapter.integrate(*altered)
        assert actual['status'] == 'rejected' and actual['error']['code'] == code, actual
        assert 'boundaries' not in actual and altered == before
    negative(lambda a: a[1]['boundaries'].pop(), 'MISSING_BOUNDARY')
    negative(lambda a: a[1]['boundaries'][1].update(producer=a[1]['boundaries'][0]['producer']), 'DUPLICATE_BOUNDARY')
    negative(lambda a: a[3][0]['fields'].update(temp=True), 'INVALID_VALUE')
    negative(lambda a: a[3][0]['fields'].update(extra=1), 'INVALID_SCHEMA')
    negative(lambda a: a[0][0]['types'][0].update(parent_type_id='GasTurbine'), 'UNRESOLVED_CLASS')
    negative(lambda a: a[1]['field_mappings'][0].update(declared_unit='K'), 'INCOMPATIBLE_UNIT')
    negative(lambda a: a[3].append(copy.deepcopy(a[3][0])), 'INVALID_SCHEMA')
for q, v, u, expected in [('temperature', 300, 'K', 26.85), ('pressure', 200000, 'Pa', .2), ('mass_flow', 2, 'kg/s', 7200)]:
    assert abs(adapter.normalize_quantity(q, v, u) - expected) < 1e-10
for q, v, u in [('temperature', 0, 'K'), ('pressure', 0, 'bar'), ('mass_flow', -1, 'kg/s'), ('pressure', float('nan'), 'MPa')]:
    try:
        adapter.normalize_quantity(q, v, u)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid scalar accepted')
(ROOT / 'export_native').mkdir(exist_ok=True)
adapter.export_native(providers, mapping, canonical, versions, ROOT / 'export_native' / 'native_v1.json')
print('json2 independent selftests passed; native_v1.json regenerated')
