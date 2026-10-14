"""Independent released-packet checks; no acceptance/evaluator imports."""
import copy
import json
from pathlib import Path
import unittest
import adapter

PACKET = Path(__file__).resolve().parents[2] / 'packets' / 'stage0'
def read(relative):
    return json.loads((PACKET / relative).read_text())
def inputs(ambient=5):
    return [read('providers/provider_a_v1.json'), read('providers/provider_b_v1.json')], read('providers/boundary_mapping_v1.json'), read('protocol/canonical_classes.json'), read(f'fixtures/payloads_v1_{ambient}C.json'), {'A': '1.0', 'B': '1.0'}

class Checks(unittest.TestCase):
    def test_baselines_and_queries(self):
        for ambient in (5, 25):
            args = inputs(ambient)
            original = copy.deepcopy(args)
            result = adapter.integrate(*args)
            self.assertEqual(result['status'], 'accepted', result)
            self.assertEqual(args, original)
            self.assertEqual(len(adapter.query_all(result)), 7)
            expected = {'EngineeringAsset': 7, 'GasTurbine': 1, 'HeatRecovery': 3, 'SteamExpansion': 2, 'HeatSink': 1, 'Absent': 0}
            for ancestor, count in expected.items():
                self.assertEqual(len(adapter.query_by_ancestor(result, ancestor)), count)
            self.assertEqual(len(adapter.query_returns(result, args[-1])), 2)
            self.assertEqual(adapter.query_returns(result, {})['error']['code'], 'VERSION_MISMATCH')
            args[0].reverse()
            args[1]['boundaries'].reverse()
            args[3].reverse()
            self.assertEqual(adapter.integrate(*args), result)
    def test_conversions(self):
        for q, value, unit, expected in [('temperature', 300, 'K', 26.85), ('pressure', 7, 'bar', .7), ('mass_flow', 3, 'kg/s', 10800)]:
            self.assertAlmostEqual(adapter.normalize_quantity(q, value, unit), expected)
        for q, value, unit in [('temperature', 0, 'K'), ('pressure', 0, 'MPa'), ('mass_flow', -1, 'kg/h'), ('pressure', True, 'MPa'), ('temperature', float('nan'), 'K')]:
            with self.assertRaises(ValueError):
                adapter.normalize_quantity(q, value, unit)
    def test_rejections(self):
        changes = [
            ('MISSING_BOUNDARY', lambda a: a[1]['boundaries'].pop()),
            ('INVALID_SCHEMA', lambda a: a[3].pop()),
            ('INVALID_VALUE', lambda a: a[3][0]['fields'].update(temp=True)),
            ('VERSION_MISMATCH', lambda a: a[4].update(A='8.0')),
            ('UNRESOLVED_CLASS', lambda a: a[0][0]['types'][0].update(parent_type_id='GasTurbine')),
            ('INCOMPATIBLE_UNIT', lambda a: a[1]['field_mappings'][0].update(declared_unit='K')),
            ('AMBIGUOUS_MAPPING', lambda a: a[1]['boundaries'][0]['producer'].pop('namespace')),
            ('DUPLICATE_BOUNDARY', lambda a: a[1]['boundaries'][1].update(producer=copy.deepcopy(a[1]['boundaries'][0]['producer'])))
        ]
        for code, change in changes:
            args = inputs()
            change(args)
            original = copy.deepcopy(args)
            result = adapter.integrate(*args)
            self.assertEqual(result['error']['code'], code, result)
            self.assertNotIn('boundaries', result)
            self.assertEqual(args, original)
    def test_idempotence_and_transitivity(self):
        args = inputs()
        baseline = adapter.integrate(*args)
        args[1]['boundaries'].append(copy.deepcopy(args[1]['boundaries'][0]))
        args[1]['field_mappings'].append(copy.deepcopy(args[1]['field_mappings'][0]))
        args[0][0]['types'].append({'local_type_id': 'CustomLeaf', 'parent_type_id': 'GasTurbine'})
        args[0][0]['equipment'][0]['local_type_id'] = 'CustomLeaf'
        result = adapter.integrate(*args)
        self.assertEqual(result['status'], 'accepted', result)
        self.assertEqual([b['boundary_id'] for b in adapter.query_by_ancestor(result, 'GasTurbine')], ['gt_exhaust'])
        self.assertIn('CustomLeaf', adapter.query_by_ancestor(result, 'GasTurbine')[0]['producer']['local_ancestors'])

if __name__ == '__main__':
    args = inputs()
    artifact = adapter.export_native(args[0], args[1], args[2], args[4])
    (Path(__file__).parent / 'native_v1.json').write_text(json.dumps(artifact, indent=2, sort_keys=True) + '\n')
    unittest.main()
