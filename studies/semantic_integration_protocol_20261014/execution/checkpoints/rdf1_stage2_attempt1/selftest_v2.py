"""Released-v2 tests and original independent v1 regressions."""
import copy
import math
import selftest as t
import adapter as a

providers = [t.load('providers/provider_a_v2.json'), t.load('providers/provider_b_v2.json')]
mapping = t.load('providers/boundary_mapping_v2.json')
versions = {'A': '2.0', 'B': '2.0'}
for ambient in (5, 25):
    payloads = t.load(f'fixtures/payloads_v2_{ambient}C.json')
    args = [providers, mapping, t.classes, payloads, versions]
    before = copy.deepcopy(args)
    result = a.integrate(*args)
    t.check(result['status'] == 'accepted')
    t.check(before == args)
    base = a.integrate(t.providers, t.mapping, t.classes, t.load(f'fixtures/payloads_v1_{ambient}C.json'), t.versions)
    for new, old in zip(a.query_all(result), a.query_all(base)):
        t.check(new['boundary_id'] == old['boundary_id'])
        for q in ('T', 'P', 'm_dot'):
            t.check(math.isclose(new[q], old[q], rel_tol=1e-10, abs_tol=1e-6))
        t.check(new['w'] == old['w'])
        for role in ('producer', 'consumer'):
            desc = new[role]
            t.check(desc['schema_version'] == '2.0')
            if desc['local_equipment_id'] == 'H01':
                t.check({'ControlledHRSG', 'HRSG', 'HeatRecoveryUnit', 'ThermalAsset'} <= set(desc['local_ancestors']))
            if desc['local_equipment_id'] == 'ST1':
                t.check({'ReheatSteamTurbine', 'SteamTurbine', 'ExpansionMachine', 'CycleComponent'} <= set(desc['local_ancestors']))
    t.check(len(a.query_by_ancestor(result, 'HeatRecovery')) == 3)
    t.check(len(a.query_by_ancestor(result, 'SteamExpansion')) == 2)
    t.check(len(a.query_returns(result, versions)) == 2)
    changed = copy.deepcopy(args)
    changed[3][0]['fields']['temp'] = changed[3][0]['fields'].pop('temperature_abs')
    t.check(a.integrate(*changed)['error']['code'] == 'INVALID_SCHEMA')
    changed = copy.deepcopy(args)
    changed[1]['mapping_version'] = '1.0'
    t.check(a.integrate(*changed)['error']['code'] == 'VERSION_MISMATCH')
if not (t.HERE / 'native_v2.ttl').exists():
    a.export_native(providers, mapping, t.classes, t.HERE / 'native_v2.ttl')
print(f'{t.checks} total independent checks passed; native_v2.ttl available')
