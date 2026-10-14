"""Independent scoped v3 checks; never loads supplied invalid variants."""
import copy
import json
from pathlib import Path
import unittest
import adapter

PACKET = Path(__file__).resolve().parents[2] / 'packets' / 'stage2'
def inputs(version=3, ambient=5):
    def read(relative):
        return json.loads((PACKET / relative).read_text())
    return [read(f'providers/provider_{p}_v{version}.json') for p in ('a', 'b')], read(f'providers/boundary_mapping_v{version}.json'), read('protocol/canonical_classes.json'), read(f'fixtures/payloads_v{version}_{ambient}C.json'), {'A': f'{version}.0', 'B': f'{version}.0'}

class Stage2(unittest.TestCase):
    def test_qualified_endpoints(self):
        for ambient in (5, 25):
            args = inputs(3, ambient)
            original = copy.deepcopy(args)
            result = adapter.integrate(*args)
            prior = adapter.integrate(*inputs(2, ambient))
            self.assertEqual(result['status'], 'accepted', result)
            self.assertEqual(args, original)
            for before, after in zip(adapter.query_all(prior), adapter.query_all(result)):
                for quantity in ('T', 'P', 'm_dot', 'w', 'canonical_ancestors'):
                    self.assertEqual(before[quantity], after[quantity])
                self.assertEqual(after['consumer']['local_port_id'], 'inlet')
            consumers = [b['consumer'] for b in result['boundaries']]
            identities = {(e['provider_id'], e['namespace'], e['local_port_id']) for e in consumers}
            self.assertEqual(len(identities), 7)
            returns = {b['boundary_id']: b for b in adapter.query_returns(result, args[-1])}
            self.assertEqual(returns['cold_reheat']['consumer']['namespace'], 'thermal.hrsg.reheat')
            self.assertEqual(returns['condensate']['consumer']['namespace'], 'thermal.hrsg.water')
            for provider in args[0]:
                provider['ports'].reverse()
            args[1]['boundaries'].reverse()
            args[3].reverse()
            self.assertEqual(adapter.integrate(*args), result)
    def test_independent_conflicts(self):
        def contradictory_mapping(a):
            altered = copy.deepcopy(a[1]['boundaries'][0])
            altered['consumer'] = copy.deepcopy(a[1]['boundaries'][1]['consumer'])
            a[1]['boundaries'].append(altered)
        def contradictory_field(a):
            altered = copy.deepcopy(a[1]['field_mappings'][0])
            altered['canonical_quantity'] = 'pressure'
            a[1]['field_mappings'].append(altered)
        changes = [
            ('AMBIGUOUS_MAPPING', lambda a: a[1]['boundaries'][0]['consumer'].pop('namespace')),
            ('UNRESOLVED_CLASS', lambda a: a[0][0]['types'][0].update(parent_type_id='MissingRoot')),
            ('AMBIGUOUS_MAPPING', contradictory_mapping),
            ('AMBIGUOUS_MAPPING', contradictory_field),
        ]
        for expected, change in changes:
            args = inputs()
            change(args)
            original = copy.deepcopy(args)
            result = adapter.integrate(*args)
            self.assertEqual(result['error']['code'], expected, result)
            self.assertTrue(result['error']['detail'])
            self.assertNotIn('boundaries', result)
            self.assertEqual(args, original)

if __name__ == '__main__':
    args = inputs()
    native = adapter.export_native(args[0], args[1], args[2], args[-1])
    (Path(__file__).parent / 'native_v3.json').write_text(json.dumps(native, indent=2, sort_keys=True) + '\n')
    unittest.main()
