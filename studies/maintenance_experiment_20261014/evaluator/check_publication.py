"""Held-out, requirement-derived CHANGE_2 checks. Do not disclose to implementers."""
from copy import deepcopy
import math

BOUNDARIES = ('gt_exhaust', 'hp_steam', 'hot_reheat', 'lp_steam', 'st_exhaust', 'cold_reheat', 'condensate')
CONSUMERS = ('dashboard', 'report', 'diagnostics')
CANONICAL_UNITS = dict(T='degC', P='MPa', m_dot='kg/hr', h='J/kg')
SI_UNITS = dict(T='K', P='Pa', m_dot='kg/s', h='kJ/kg')
REPORT_UNITS = dict(T='degC', P='kPa', m_dot='kg/s', h='J/kg')
CANONICAL_VALUES = dict(T=0.0, P=1.0, m_dot=3600.0, h=1000.0)
SI_VALUES = dict(T=273.15, P=1000000.0, m_dot=1.0, h=1.0)
REPORT_VALUES = dict(T=0.0, P=1000.0, m_dot=1.0, h=1000.0)


def fixture(store_class, alternate=False, consumer_units=None):
    aliases = {key: ('alternate_' if alternate else 'wire_') + key for key in CANONICAL_UNITS}
    input_units = CANONICAL_UNITS if alternate else SI_UNITS
    input_values = CANONICAL_VALUES if alternate else SI_VALUES
    units = consumer_units or dict(dashboard=CANONICAL_UNITS, report=REPORT_UNITS, diagnostics=SI_UNITS)
    facts = [('stream', 'version', '2')]
    for key in CANONICAL_UNITS:
        facts.extend([('stream', 'field_' + key, aliases[key]), ('stream', 'unit_' + key, input_units[key])])
    for consumer in CONSUMERS:
        for key, value in units[consumer].items():
            facts.append((consumer, 'unit_' + key, value))
    record = {'version': '2', 'values': {aliases[k]: v for k, v in input_values.items()},
              'units': {aliases[k]: v for k, v in input_units.items()}, 'composition': {'N2': 0.75, 'O2': 0.25}}
    return store_class(facts).dumps(), {b: deepcopy(record) for b in BOUNDARIES}, facts, aliases


def expected(revision, all_si=False):
    consumers = {}
    for name, units, values in [('dashboard', CANONICAL_UNITS, CANONICAL_VALUES),
                                ('report', REPORT_UNITS, REPORT_VALUES), ('diagnostics', SI_UNITS, SI_VALUES)]:
        if all_si:
            units, values = SI_UNITS, SI_VALUES
        streams = {b: dict(values, w={'N2': 0.75, 'O2': 0.25}) for b in BOUNDARIES}
        consumers[name] = {'units': dict(units), 'streams': streams}
    return {'revision': revision, 'consumers': consumers}


def same(actual, wanted, path='root'):
    if isinstance(wanted, dict):
        assert isinstance(actual, dict), f'{path}: expected dict, got {type(actual).__name__}'
        assert actual.keys() == wanted.keys(), f'{path}: keys differ: {list(actual)} vs {list(wanted)}'
        for key in wanted:
            same(actual[key], wanted[key], path + '.' + key)
    elif isinstance(wanted, (float, int)):
        assert not isinstance(actual, bool) and isinstance(actual, (float, int)), f'{path}: not a real scalar'
        assert math.isfinite(actual) and math.isclose(actual, wanted, rel_tol=1e-12, abs_tol=1e-10), f'{path}: {actual!r} != {wanted!r}'
    else:
        assert actual == wanted, f'{path}: {actual!r} != {wanted!r}'


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError('Expected ValueError')


def checks(module, store_class):
    results = []

    def run(case_id, case):
        try:
            case()
            results.append(dict(id=case_id, passed=True, error=''))
        except Exception as exc:
            results.append(dict(id=case_id, passed=False, error=f'{type(exc).__name__}: {exc}'))

    def setup():
        config, records, facts, aliases = fixture(store_class)
        return module.PublicationSession(), config, records, facts, aliases

    def accepted():
        session, config, records, facts, aliases = setup()
        session.begin('old')
        session.publish('old', records, config)
        return session, config, records, facts, aliases

    def good():
        session, config, records, _, _ = setup()
        same(module.adapt(records[BOUNDARIES[0]], config), dict(CANONICAL_VALUES, w={'N2': .75, 'O2': .25}))
        session.begin('r1')
        session.publish('r1', records, config)
        same(session.snapshot(), expected('r1'))
        same(session.history(), {'r1': expected('r1')})

    def pending_history():
        session, config, records, _, _ = setup()
        rejects(session.snapshot)
        same(session.history(), {})
        session.begin('first')
        rejects(session.snapshot)
        session.publish('first', records, config)
        session.begin('second')
        rejects(session.snapshot)
        same(session.history(), {'first': expected('first')})
        session.publish('second', records, config)
        same(session.snapshot(), expected('second'))
        same(session.history(), {r: expected(r) for r in ('first', 'second')})

    def delayed_old():
        session, config, records, _, _ = setup()
        session.begin('abandoned')
        session.begin('new')
        rejects(lambda: session.publish('abandoned', records, config))
        rejects(session.snapshot)
        same(session.history(), {})
        session.publish('new', records, config)
        rejects(lambda: session.publish('abandoned', records, config))
        same(session.snapshot(), expected('new'))

    def late_record_atomic():
        session, config, records, _, aliases = accepted()
        session.begin('bad')
        records[BOUNDARIES[-1]]['values'][aliases['P']] = -1
        rejects(lambda: session.publish('bad', records, config))
        rejects(session.snapshot)
        same(session.history(), {'old': expected('old')})

    def late_consumer_atomic():
        session, config, records, facts, _ = accepted()
        session.begin('bad')
        bad = [(s, p, 'kg' if (s, p) == ('diagnostics', 'unit_h') else o) for s, p, o in facts]
        rejects(lambda: session.publish('bad', records, store_class(bad).dumps()))
        rejects(session.snapshot)
        same(session.history(), {'old': expected('old')})

    def input_isolation():
        session, config, records, _, aliases = setup()
        saved = deepcopy(records)
        session.begin('r')
        session.publish('r', records, config)
        same(records, saved)
        records[BOUNDARIES[0]]['composition']['N2'] = .1
        records[BOUNDARIES[0]]['values'][aliases['T']] = 800
        records.clear()
        same(session.snapshot(), expected('r'))
        same(session.history(), {'r': expected('r')})

    def output_isolation():
        session, _, _, _, _ = accepted()
        snapshot = session.snapshot()
        snapshot['consumers']['dashboard']['streams'][BOUNDARIES[0]]['w']['N2'] = 99
        snapshot['consumers']['report']['units']['P'] = 'broken'
        snapshot['consumers']['diagnostics']['streams'].clear()
        history = session.history()
        history['old']['consumers']['report']['streams'][BOUNDARIES[-1]]['w'].clear()
        history.clear()
        same(session.snapshot(), expected('old'))
        same(session.history(), {'old': expected('old')})

    def revision_reuse():
        session, config, records, _, _ = accepted()
        for invalid in ('old', '', None, 3, True):
            rejects(lambda invalid=invalid: session.begin(invalid))
            same(session.snapshot(), expected('old'))
        session.begin('pending')
        rejects(lambda: session.begin('pending'))
        session.begin('new')
        rejects(lambda: session.begin('pending'))
        session.publish('new', records, config)
        same(session.snapshot(), expected('new'))

    def retry_failure():
        session, config, records, _, aliases = accepted()
        session.begin('retry')
        bad = deepcopy(records)
        bad[BOUNDARIES[-1]]['values'][aliases['h']] = float('nan')
        rejects(lambda: session.publish('retry', bad, config))
        session.publish('retry', records, config)
        same(session.snapshot(), expected('retry'))
        same(session.history(), {r: expected(r) for r in ('old', 'retry')})

    def missing_boundary():
        for missing in BOUNDARIES:
            session, config, records, _, _ = setup()
            session.begin('r')
            del records[missing]
            rejects(lambda: session.publish('r', records, config))
            rejects(session.snapshot)
            same(session.history(), {})

    def configuration_changes():
        session, config, records, _, _ = accepted()
        config2, records2, _, _ = fixture(store_class, alternate=True, consumer_units={c: SI_UNITS for c in CONSUMERS})
        session.begin('new')
        session.publish('new', records2, config2)
        same(session.snapshot(), expected('new', all_si=True))
        same(session.history()['old'], expected('old'))
        session.begin('back')
        session.publish('back', records, config)
        same(session.snapshot(), expected('back'))

    def completed_revision():
        session, config, records, _, _ = accepted()
        rejects(lambda: session.publish('old', records, config))
        rejects(lambda: session.publish('unknown', records, config))
        same(session.snapshot(), expected('old'))
        same(session.history(), {'old': expected('old')})

    def extra_boundary():
        session, config, records, _, _ = setup()
        session.begin('r')
        records['extra'] = deepcopy(records[BOUNDARIES[0]])
        rejects(lambda: session.publish('r', records, config))
        rejects(session.snapshot)
        same(session.history(), {})

    def consumer_overflow():
        session, _, _, _, _ = accepted()
        config, records, _, aliases = fixture(store_class, alternate=True)
        records[BOUNDARIES[-1]]['values'][aliases['P']] = 1e303
        session.begin('overflow')
        rejects(lambda: session.publish('overflow', records, config))
        rejects(session.snapshot)
        same(session.history(), {'old': expected('old')})

    cases = [('C2_01_three_consumers_seven_boundaries', good), ('C2_02_pending_and_history', pending_history),
             ('C2_03_delayed_old_completion', delayed_old), ('C2_04_late_record_atomic', late_record_atomic),
             ('C2_05_late_consumer_atomic', late_consumer_atomic), ('C2_06_input_copy_isolation', input_isolation),
             ('C2_07_snapshot_history_copy_isolation', output_isolation), ('C2_08_revision_reuse', revision_reuse),
             ('C2_09_retry_failed_revision', retry_failure), ('C2_10_missing_boundary', missing_boundary),
             ('C2_11_configuration_not_cached', configuration_changes), ('C2_12_completed_revision_rejected', completed_revision),
             ('C2_13_extra_boundary', extra_boundary), ('C2_14_nonfinite_consumer_atomic', consumer_overflow)]
    for case_id, case in cases:
        run(case_id, case)
    return results
