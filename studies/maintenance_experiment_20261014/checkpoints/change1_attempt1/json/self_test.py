import copy
import json
import unittest
from adapter import adapt
from stores import JSONStore


def config(wires=None, units=None):
    wires = wires or {'T': 'temp', 'P': 'pressure', 'm_dot': 'flow', 'h': 'energy'}
    units = units or {'T': 'K', 'P': 'kPa', 'm_dot': 'kg/s', 'h': 'kJ/kg'}
    facts = [('stream', 'version', '2')]
    for field in wires:
        facts.extend([('stream', 'field_' + field, wires[field]), ('stream', 'unit_' + field, units[field])])
    return JSONStore(facts).dumps()


def record():
    return {'version': '2', 'values': {'temp': 300, 'pressure': 1000, 'flow': 2, 'energy': -5},
            'units': {'temp': 'K', 'pressure': 'kPa', 'flow': 'kg/s', 'energy': 'kJ/kg'},
            'composition': {'water': 0.75, 'gas': 0.25}}


class AdapterTests(unittest.TestCase):
    def test_conversion_and_copy(self):
        r = record(); original = copy.deepcopy(r)
        got = adapt(r, config())
        self.assertEqual(set(got), {'T', 'P', 'm_dot', 'h', 'w'})
        self.assertAlmostEqual(got['T'], 26.85)
        self.assertEqual((got['P'], got['m_dot'], got['h']), (1, 7200, -5000))
        self.assertEqual(r, original)
        self.assertIsNot(got['w'], r['composition'])

    def test_units_and_fresh_config(self):
        for unit, value in [('MPa', 1), ('kPa', 1000), ('Pa', 1000000)]:
            r = record(); r['units']['pressure'] = unit; r['values']['pressure'] = value
            c = config(units={'T': 'K', 'P': unit, 'm_dot': 'kg/s', 'h': 'kJ/kg'})
            self.assertEqual(adapt(r, c)['P'], 1)
        r = record(); r['values'] = {'a': 30, 'b': 2, 'c': 0, 'd': 10}
        r['units'] = {'a': 'degC', 'b': 'MPa', 'c': 'kg/hr', 'd': 'J/kg'}
        c = config(dict(zip(('T', 'P', 'm_dot', 'h'), 'abcd')), {'T':'degC','P':'MPa','m_dot':'kg/hr','h':'J/kg'})
        self.assertEqual(adapt(r, c)['T'], 30)
        self.assertAlmostEqual(adapt(record(), config())['T'], 26.85)

    def test_bad_values(self):
        for key, bad in [('temp', 0), ('temp', -1), ('pressure', 0), ('flow', -1), ('flow', 1e308)]:
            r = record(); r['values'][key] = bad
            with self.subTest(key=key,bad=bad), self.assertRaises(ValueError): adapt(r, config())
        for key in record()['values']:
            for bad in [True, None, '1', float('nan'), float('inf'), {}, 10**1000]:
                r = record(); r['values'][key] = bad
                with self.subTest(key=key,bad=repr(bad)[:30]), self.assertRaises(ValueError): adapt(r, config())

    def test_bad_record(self):
        variants = []
        for key in record():
            r = record(); del r[key]; variants.append(r)
        r = record(); r['extra'] = 1; variants.append(r)
        for key in ['values', 'units']:
            for mutation in ['extra', 'missing']:
                r = record()
                if mutation == 'extra': r[key]['extra'] = 1
                else: del r[key]['temp']
                variants.append(r)
        for bad in [2, '3', True]:
            r = record(); r['version'] = bad; variants.append(r)
        for bad in [{}, {'x': 0.5}, {'x': -1, 'y': 2}, {'x': float('nan')}, {'x': True}, {1: 1}, {'x': float('inf')}]:
            r = record(); r['composition'] = bad; variants.append(r)
        r = record(); r['units']['temp'] = 'degC'; variants.append(r)
        for r in variants:
            with self.subTest(record=r), self.assertRaises(ValueError): adapt(r, config())

    def test_bad_schema(self):
        variants = ['bad json', '[]', '{}']
        base = json.loads(config())
        for key in base['stream']:
            c = copy.deepcopy(base); del c['stream'][key]; variants.append(json.dumps(c))
            c = copy.deepcopy(base); c['stream'][key] *= 2; variants.append(json.dumps(c))
        for key, value in [('field_T', ['flow']), ('unit_T', ['MPa']), ('version', ['3']), ('version', [True]), ('field_T', [2]), ('unit_T', [{}])]:
            c = copy.deepcopy(base); c['stream'][key] = value; variants.append(json.dumps(c))
        c = copy.deepcopy(base); c['stream']['field_extra'] = ['x']; variants.append(json.dumps(c))
        variants.append(config().replace('"version":["2"]', '"version":["2"],"version":["2"]'))
        for c in variants:
            with self.subTest(config=c), self.assertRaises(ValueError): adapt(record(), c)


if __name__ == '__main__': unittest.main()
