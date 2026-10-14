"""Released v2 regression checks and reproducible native artifact generation."""
import copy
import json
from pathlib import Path
import unittest
import adapter

PACKET = Path(__file__).resolve().parents[2] / 'packets' / 'stage1'
def inputs(version, ambient):
    def read(relative):
        return json.loads((PACKET / relative).read_text())
    return [read(f'providers/provider_{p}_v{version}.json') for p in ('a', 'b')], read(f'providers/boundary_mapping_v{version}.json'), read('protocol/canonical_classes.json'), read(f'fixtures/payloads_v{version}_{ambient}C.json'), {'A': f'{version}.0', 'B': f'{version}.0'}

class Stage1(unittest.TestCase):
    def test_versions(self):
        for ambient in (5, 25):
            old = adapter.integrate(*inputs(1, ambient))
            args = inputs(2, ambient)
            untouched = copy.deepcopy(args)
            new = adapter.integrate(*args)
            self.assertEqual(new['status'], 'accepted', new)
            self.assertEqual(args, untouched)
            for a, b in zip(adapter.query_all(old), adapter.query_all(new)):
                self.assertEqual(a['boundary_id'], b['boundary_id'])
                for q in ('T', 'P', 'm_dot'):
                    self.assertAlmostEqual(a[q], b[q], delta=1e-6)
                self.assertEqual(a['w'], b['w'])
                self.assertEqual(a['canonical_ancestors'], b['canonical_ancestors'])
                for role in ('producer', 'consumer'):
                    endpoint = b[role]
                    self.assertEqual(endpoint['schema_version'], '2.0')
                    if endpoint['local_equipment_id'] == 'H01':
                        self.assertTrue({'ControlledHRSG', 'HRSG', 'HeatRecoveryUnit', 'ThermalAsset'} <= set(endpoint['local_ancestors']))
                    if endpoint['local_equipment_id'] == 'ST1':
                        self.assertTrue({'ReheatSteamTurbine', 'SteamTurbine', 'ExpansionMachine', 'CycleComponent'} <= set(endpoint['local_ancestors']))
            self.assertEqual(len(adapter.query_returns(new, args[-1])), 2)
            args[3][0]['fields']['temp'] = args[3][0]['fields'].pop('temperature_abs')
            self.assertEqual(adapter.integrate(*args)['error']['code'], 'INVALID_SCHEMA')

if __name__ == '__main__':
    args = inputs(2, 5)
    native = adapter.export_native(args[0], args[1], args[2], args[-1])
    (Path(__file__).parent / 'native_v2.json').write_text(json.dumps(native, indent=2, sort_keys=True) + '\n')
    unittest.main()
