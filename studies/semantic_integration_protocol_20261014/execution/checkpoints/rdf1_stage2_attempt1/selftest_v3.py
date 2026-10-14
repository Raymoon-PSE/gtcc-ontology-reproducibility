"""Released v3 namespace isolation tests, plus v1/v2 regressions."""
import copy
import selftest_v2 as previous
import selftest as t
import adapter as a

providers = [t.load('providers/provider_a_v3.json'), t.load('providers/provider_b_v3.json')]
mapping = t.load('providers/boundary_mapping_v3.json')
versions = {'A': '3.0', 'B': '3.0'}
for ambient in (5, 25):
    payloads = t.load(f'fixtures/payloads_v3_{ambient}C.json')
    args = [providers, mapping, t.classes, payloads, versions]
    before = copy.deepcopy(args)
    result = a.integrate(*args)
    t.check(result['status'] == 'accepted')
    t.check(args == before)
    old = a.integrate(previous.providers, previous.mapping, t.classes, t.load(f'fixtures/payloads_v2_{ambient}C.json'), previous.versions)
    for new, base in zip(a.query_all(result), a.query_all(old)):
        for q in ('T', 'P', 'm_dot', 'w', 'canonical_ancestors'):
            t.check(new[q] == base[q])
        t.check(new['consumer']['local_port_id'] == 'inlet')
        t.check(new['consumer']['namespace'] != base['consumer']['namespace'])
        t.check(new['producer']['schema_version'] == '3.0')
    consumers = [b['consumer'] for b in a.query_all(result)]
    t.check(len({(d['provider_id'], d['namespace'], d['local_port_id']) for d in consumers}) == 7)
    returns = {b['boundary_id']: b for b in a.query_returns(result, versions)}
    t.check(returns['cold_reheat']['consumer']['namespace'] == 'thermal.hrsg.reheat')
    t.check(returns['condensate']['consumer']['namespace'] == 'thermal.hrsg.water')
    reordered = copy.deepcopy(args)
    reordered[0].reverse()
    reordered[1]['boundaries'].reverse()
    reordered[3].reverse()
    t.check(a.integrate(*reordered) == result)
    def mutation(fn, code):
        changed = copy.deepcopy(args)
        fn(changed)
        original = copy.deepcopy(changed)
        rejected = a.integrate(*changed)
        t.check(rejected.get('error', {}).get('code') == code)
        t.check('boundaries' not in rejected and bool(rejected['error']['detail']))
        t.check(original == changed)
    mutation(lambda x: x[1]['boundaries'][0]['consumer'].pop('namespace'), 'AMBIGUOUS_MAPPING')
    mutation(lambda x: x[1]['boundaries'].append(dict(x[1]['boundaries'][0], consumer=x[1]['boundaries'][1]['consumer'])), 'AMBIGUOUS_MAPPING')
    mutation(lambda x: x[0][1]['types'][-1].update(parent_type_id='AbsentParent'), 'UNRESOLVED_CLASS')
    mutation(lambda x: x[1]['field_mappings'].append(dict(x[1]['field_mappings'][0], canonical_quantity='pressure')), 'AMBIGUOUS_MAPPING')
    mutation(lambda x: x[1].update(mapping_version='2.0'), 'VERSION_MISMATCH')
    repeated = copy.deepcopy(args)
    repeated[1]['boundaries'] += copy.deepcopy(repeated[1]['boundaries'])
    t.check(a.integrate(*repeated) == result)
a.export_native(providers, mapping, t.classes, t.HERE / 'native_v3.ttl')
print(f'{t.checks} total independent checks passed; native_v3.ttl exported')
