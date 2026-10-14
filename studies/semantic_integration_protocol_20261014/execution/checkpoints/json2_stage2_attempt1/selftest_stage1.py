"""Released v1/v2 snapshot checks; imports only own adapter."""
import copy
import json
import math
from pathlib import Path
import adapter
ROOT = Path(__file__).resolve().parent
PACKET = ROOT.parents[1] / 'packets' / 'stage1'
def read(path):
    return json.loads((PACKET / path).read_text())
canonical = read('protocol/canonical_classes.json')
physical = read('fixtures/whole_cycle.json')
for version in (1, 2):
    providers = [read(f'providers/provider_{p}_v{version}.json') for p in ('a', 'b')]
    mapping = read(f'providers/boundary_mapping_v{version}.json')
    revisions = {'A': f'{version}.0', 'B': f'{version}.0'}
    for ambient in (5, 25):
        payloads = read(f'fixtures/payloads_v{version}_{ambient}C.json')
        args = [providers, mapping, canonical, payloads, revisions]
        saved = copy.deepcopy(args)
        result = adapter.integrate(*args)
        assert result['status'] == 'accepted', result
        assert args == saved
        for b in result['boundaries']:
            truth = physical[str(ambient)]['streams'][b['boundary_id']]
            for field in ('T', 'P', 'm_dot'):
                assert math.isclose(b[field], truth[field], rel_tol=1e-10, abs_tol=1e-6)
            assert b['w'] == truth['w']
            for role in ('producer', 'consumer'):
                d = b[role]
                assert d['schema_version'] == revisions[d['provider_id']]
                if version == 2 and d['local_equipment_id'] == 'H01':
                    assert {'ControlledHRSG', 'HRSG', 'HeatRecoveryUnit', 'ThermalAsset'} == set(d['local_ancestors'])
                if version == 2 and d['local_equipment_id'] == 'ST1':
                    assert {'ReheatSteamTurbine', 'SteamTurbine', 'ExpansionMachine', 'CycleComponent'} == set(d['local_ancestors'])
        assert len(adapter.query_returns(result, revisions)) == 2
        assert len(adapter.query_by_ancestor(result, 'HeatRecovery')) == 3
        reordered = copy.deepcopy(args)
        reordered[0].reverse()
        reordered[1]['field_mappings'].reverse()
        reordered[3].reverse()
        assert adapter.integrate(*reordered) == result
        if version == 2:
            old_alias = copy.deepcopy(args)
            old_alias[3][0]['fields']['temp'] = old_alias[3][0]['fields'].pop('temperature_abs')
            assert adapter.integrate(*old_alias)['error']['code'] == 'INVALID_SCHEMA'
            mixed = copy.deepcopy(args)
            mixed[3][0]['schema_version'] = '1.0'
            assert adapter.integrate(*mixed)['error']['code'] == 'VERSION_MISMATCH'
    if version == 2:
        adapter.export_native(providers, mapping, canonical, revisions, ROOT / 'export_native' / 'native_v2.json')
print('json2 stage1 selftests passed; v1/v2 physical and semantic checks; native_v2.json regenerated')
