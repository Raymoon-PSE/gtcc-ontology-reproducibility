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



from adapter import PublicationSession, BOUNDARIES, CONSUMERS


def publication_config():
    raw = json.loads(config())
    for consumer in CONSUMERS:
        raw[consumer] = {'unit_T': ['K'], 'unit_P': ['Pa'],
                         'unit_m_dot': ['kg/s'], 'unit_h': ['kJ/kg']}
    return json.dumps(raw)


def records():
    result = {boundary: record() for boundary in BOUNDARIES}
    for i, boundary in enumerate(BOUNDARIES):
        result[boundary]['values']['energy'] = i
    return result


class PublicationTests(unittest.TestCase):
    def test_all_consumers_and_isolation(self):
        session = PublicationSession(); source = records(); saved = copy.deepcopy(source)
        session.begin('r1'); session.publish('r1', source, publication_config())
        got = session.snapshot()
        self.assertEqual(set(got), {'revision', 'consumers'})
        self.assertEqual(set(got['consumers']), set(CONSUMERS))
        for consumer in CONSUMERS:
            view = got['consumers'][consumer]
            self.assertEqual(set(view), {'units', 'streams'})
            self.assertEqual(set(view['streams']), set(BOUNDARIES))
            for i, boundary in enumerate(BOUNDARIES):
                stream = view['streams'][boundary]
                self.assertEqual((stream['T'], stream['P'], stream['m_dot'], stream['h']),
                                 (300, 1e6, 2, i))
        self.assertEqual(source, saved)
        got['consumers']['dashboard']['streams']['gt_exhaust']['w']['water'] = 0
        source['gt_exhaust']['composition']['water'] = 0
        hist = session.history(); hist.clear()
        self.assertEqual(session.snapshot()['consumers']['dashboard']['streams']['gt_exhaust']['w']['water'], .75)
        self.assertEqual(set(session.history()), {'r1'})

    def test_lifecycle_failures_and_retry(self):
        session = PublicationSession()
        with self.assertRaises(ValueError): session.snapshot()
        for revision in ['', None, 1, True]:
            with self.assertRaises(ValueError): session.begin(revision)
        session.begin('r1'); session.publish('r1', records(), publication_config())
        accepted = session.snapshot()
        with self.assertRaises(ValueError): session.begin('r1')
        with self.assertRaises(ValueError): session.publish('r1', records(), publication_config())
        self.assertEqual(session.snapshot(), accepted)
        session.begin('r2')
        with self.assertRaises(ValueError): session.snapshot()
        with self.assertRaises(ValueError): session.publish('r1', records(), publication_config())
        bad = records(); bad['condensate']['composition'] = {}
        with self.assertRaises(ValueError): session.publish('r2', bad, publication_config())
        with self.assertRaises(ValueError): session.snapshot()
        self.assertEqual(session.history(), {'r1': accepted})
        session.publish('r2', records(), publication_config())
        self.assertEqual(set(session.history()), {'r1', 'r2'})
        session.begin('r3'); session.begin('r4')
        with self.assertRaises(ValueError): session.publish('r3', records(), publication_config())
        with self.assertRaises(ValueError): session.begin('r3')
        session.publish('r4', records(), publication_config())

    def test_bad_consumers_and_complete_boundaries(self):
        session = PublicationSession(); session.begin('r1')
        bad_configs = [config()]
        for consumer in CONSUMERS:
            raw = json.loads(publication_config()); del raw[consumer]; bad_configs.append(json.dumps(raw))
            for bad in [[], ['Pa', 'Pa'], ['kg/s'], [True]]:
                raw = json.loads(publication_config()); raw[consumer]['unit_P'] = bad; bad_configs.append(json.dumps(raw))
        for cfg in bad_configs:
            with self.subTest(config=cfg), self.assertRaises(ValueError):
                session.publish('r1', records(), cfg)
            with self.assertRaises(ValueError): session.snapshot()
            self.assertEqual(session.history(), {})
        for boundary in BOUNDARIES:
            bad = records(); del bad[boundary]
            with self.assertRaises(ValueError): session.publish('r1', bad, publication_config())
        bad = records(); bad['extra'] = record()
        with self.assertRaises(ValueError): session.publish('r1', bad, publication_config())
        session.publish('r1', records(), publication_config())

    def test_consumer_overflow_and_new_config(self):
        session = PublicationSession(); session.begin('r1')
        bad = records(); bad['condensate']['values']['pressure'] = 1e308
        with self.assertRaises(ValueError): session.publish('r1', bad, publication_config())
        with self.assertRaises(ValueError): session.snapshot()
        cfg = json.loads(publication_config()); cfg['diagnostics']['unit_P'] = ['MPa']
        session.publish('r1', records(), json.dumps(cfg))
        self.assertEqual(session.snapshot()['consumers']['diagnostics']['streams']['condensate']['P'], 1)
        session.begin('r2'); session.publish('r2', records(), publication_config())
        self.assertEqual(session.snapshot()['consumers']['diagnostics']['streams']['condensate']['P'], 1e6)


if __name__ == '__main__': unittest.main()
