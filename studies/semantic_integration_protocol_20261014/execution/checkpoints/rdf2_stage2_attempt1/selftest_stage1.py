"""Stage 1 checks; reads only released stage1 inputs, leaves stage0 artifacts intact."""
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
import adapter as a

HERE = Path(__file__).resolve().parent
PACKET = HERE.parents[1] / 'packets' / 'stage1'

def load(name):
    return json.loads((PACKET / name).read_text())

def inputs(v, ambient):
    return [[load(f'providers/provider_{p}_v{v}.json') for p in ('a', 'b')],
            load(f'providers/boundary_mapping_v{v}.json'), load('protocol/canonical_classes.json'),
            load(f'fixtures/payloads_v{v}_{ambient}C.json'), {'A': f'{v}.0', 'B': f'{v}.0'}]

checks = []
for v in (1, 2):
    for ambient in (5, 25):
        args = inputs(v, ambient)
        before = deepcopy(args)
        result = a.integrate(*args)
        assert args == before
        assert result['status'] == 'accepted', result
        expected = load('fixtures/whole_cycle.json')[str(ambient)]['streams']
        assert len(a.query_all(result)) == 7
        for row in result['boundaries']:
            for quantity in ('T', 'P', 'm_dot'):
                assert math.isclose(row[quantity], expected[row['boundary_id']][quantity], rel_tol=1e-10, abs_tol=1e-6)
            assert row['w'] == expected[row['boundary_id']]['w']
            for role in ('producer', 'consumer'):
                ep = row[role]
                assert ep['schema_version'] == f'{v}.0'
                provider = next(p for p in args[0] if p['provider_id'] == ep['provider_id'])
                for f in provider['field_sets']['state']:
                    assert ep['provenance'][a.QUANTITIES[f['quantity']]] == {'field': f['local_key'], 'unit': f['unit']}
                if v == 2:
                    for req in load('RELEASED_CHANGES.json')[0]['ancestor_requirements']:
                        if ep['provider_id'] == req['provider_id'] and ep['local_equipment_id'] == req['equipment_id']:
                            assert set(req['required_ancestors']) <= set(ep['local_ancestors'])
        for cls, expected_ids in {'EngineeringAsset': a.BOUNDARIES, 'GasTurbine': {'gt_exhaust'},
                                  'HeatRecovery': {'hp_steam', 'hot_reheat', 'lp_steam'},
                                  'SteamExpansion': {'cold_reheat', 'st_exhaust'}, 'HeatSink': {'condensate'}}.items():
            assert {b['boundary_id'] for b in a.query_by_ancestor(result, cls)} == set(expected_ids)
        assert {b['boundary_id'] for b in a.query_returns(result, args[4])} == {'cold_reheat', 'condensate'}
        args[0].reverse(); args[1]['boundaries'].reverse(); args[3].reverse()
        assert a.integrate(*args) == result
        checks.append(f'v{v} {ambient}C baseline, fixture, queries, provenance, ancestry, order, immutability')

args = inputs(2, 5)
args[3][0]['fields'] = inputs(1, 5)[3][0]['fields']
assert a.integrate(*args)['error']['code'] == 'INVALID_SCHEMA'
checks.append('v2 rejects v1 aliases')
args = inputs(2, 5); args[4]['A'] = '1.0'
assert a.integrate(*args)['error']['code'] == 'VERSION_MISMATCH'
checks.append('v2 rejects v1 requested revision')
args = inputs(2, 5); args[0][0]['types'][-1]['parent_type_id'] = 'Absent'
assert a.integrate(*args)['error']['code'] == 'UNRESOLVED_CLASS'
checks.append('v2 missing intermediate ancestry rejects')
args = inputs(2, 5)
triples = a.export_native(*args[:3], HERE / 'export_native' / 'native_v2.ttl')
report = {'status': 'passed', 'checks': checks, 'native_triples': triples,
          'implementation_edits': 0, 'query_edits': 0,
          'adapter_sha256': hashlib.sha256((HERE / 'adapter.py').read_bytes()).hexdigest()}
(HERE / 'selftest_stage1_results.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
