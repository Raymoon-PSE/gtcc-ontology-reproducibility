"""Own stage2 checks using released valid snapshots only."""
import copy
import json
import math
from pathlib import Path
import adapter
ROOT = Path(__file__).resolve().parent
PACKET = ROOT.parents[1] / 'packets' / 'stage2'
def read(path):
    return json.loads((PACKET / path).read_text())
canonical = read('protocol/canonical_classes.json')
physical = read('fixtures/whole_cycle.json')
for version in (1, 2, 3):
    providers = [read(f'providers/provider_{p}_v{version}.json') for p in ('a', 'b')]
    mapping = read(f'providers/boundary_mapping_v{version}.json')
    revisions = dict.fromkeys(('A', 'B'), f'{version}.0')
    for ambient in (5, 25):
        args = [providers, mapping, canonical, read(f'fixtures/payloads_v{version}_{ambient}C.json'), revisions]
        saved = copy.deepcopy(args)
        result = adapter.integrate(*args)
        assert result['status'] == 'accepted', result
        assert args == saved
        by_id = {b['boundary_id']: b for b in result['boundaries']}
        for b in by_id.values():
            truth = physical[str(ambient)]['streams'][b['boundary_id']]
            for field in ('T', 'P', 'm_dot'):
                assert math.isclose(b[field], truth[field], rel_tol=1e-10, abs_tol=1e-6)
            assert b['w'] == truth['w']
        for declared in mapping['boundaries']:
            b = by_id[declared['canonical_boundary_id']]
            for role in ('producer', 'consumer'):
                assert all(b[role][key] == value for key, value in declared[role].items())
        assert len(adapter.query_returns(result, revisions)) == 2
        assert len(adapter.query_by_ancestor(result, 'EngineeringAsset')) == 7
        assert len(adapter.query_by_ancestor(result, 'SteamExpansion')) == 2
        reversed_args = copy.deepcopy(args)
        reversed_args[0].reverse()
        reversed_args[1]['boundaries'].reverse()
        reversed_args[1]['field_mappings'].reverse()
        reversed_args[3].reverse()
        assert adapter.integrate(*reversed_args) == result
        if version == 3:
            def negative(mutate, code):
                altered = copy.deepcopy(args)
                mutate(altered)
                saved_altered = copy.deepcopy(altered)
                observed = adapter.integrate(*altered)
                assert observed['status'] == 'rejected' and observed['error']['code'] == code, observed
                assert 'boundaries' not in observed and observed['error']['detail']
                assert altered == saved_altered
            negative(lambda a: a[1]['boundaries'][0]['consumer'].pop('namespace'), 'AMBIGUOUS_MAPPING')
            negative(lambda a: a[0][0]['types'][-1].update(parent_type_id='absent_parent'), 'UNRESOLVED_CLASS')
            def contradictory(a):
                alternative = copy.deepcopy(a[1]['field_mappings'][0])
                alternative['canonical_quantity'] = 'pressure'
                a[1]['field_mappings'].append(alternative)
            negative(contradictory, 'AMBIGUOUS_MAPPING')
            idempotent = copy.deepcopy(args)
            idempotent[1]['field_mappings'].append(copy.deepcopy(idempotent[1]['field_mappings'][0]))
            assert adapter.integrate(*idempotent) == result
    if version == 3:
        adapter.export_native(providers, mapping, canonical, revisions, ROOT / 'export_native' / 'native_v3.json')
print('json2 stage2 selftests passed: v1/v2/v3 and own scoped mutations; native_v3.json generated')
