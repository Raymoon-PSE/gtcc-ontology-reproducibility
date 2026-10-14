"""Validate external streams against a freshly queried JSONStore schema."""
import copy
import json
import math
from collections.abc import Mapping
from numbers import Real

from stores import JSONStore

FIELDS = ('T', 'P', 'm_dot', 'h')
CONSUMERS = ('dashboard', 'report', 'diagnostics')
BOUNDARIES = ('gt_exhaust', 'hp_steam', 'hot_reheat', 'lp_steam',
              'st_exhaust', 'cold_reheat', 'condensate')
UNITS = {
    'T': {'degC': (1.0, 0.0), 'K': (1.0, -273.15)},
    'P': {'MPa': (1.0, 0.0), 'kPa': (0.001, 0.0), 'Pa': (0.000001, 0.0)},
    'm_dot': {'kg/hr': (1.0, 0.0), 'kg/s': (3600.0, 0.0)},
    'h': {'J/kg': (1.0, 0.0), 'kJ/kg': (1000.0, 0.0)},
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON declaration')
        result[key] = value
    return result


def _load_store(text):
    # Validate serialization before the native store can collapse duplicates.
    raw = json.loads(text, object_pairs_hook=_object)
    expected = {'version'} | {'field_' + f for f in FIELDS} | {'unit_' + f for f in FIELDS}
    if not isinstance(raw, dict) or 'stream' not in raw or set(raw) - {'stream', *CONSUMERS}:
        raise ValueError('Expected a stream schema')
    for subject, declarations in raw.items():
        required = expected if subject == 'stream' else {'unit_' + f for f in FIELDS}
        if not isinstance(declarations, dict) or set(declarations) != required:
            raise ValueError('Invalid schema declarations')
        for objects in declarations.values():
            if not isinstance(objects, list) or len(objects) != 1:
                raise ValueError('Expected exactly one declaration per slot')
    store = JSONStore.loads(text)
    for consumer in set(raw) & set(CONSUMERS):
        _consumer_units(store, consumer)
    return store


def _consumer_units(store, consumer):
    units = {}
    for field in FIELDS:
        unit = store.one(consumer, 'unit_' + field)
        if not isinstance(unit, str) or unit not in UNITS[field]:
            raise ValueError('Unsupported consumer unit')
        units[field] = unit
    return units


def _schema(text):
    store = _load_store(text)
    version = store.one('stream', 'version')
    if isinstance(version, bool) or version not in (2, '2'):
        raise ValueError('Unsupported schema version')
    wires, units = {}, {}
    for field in FIELDS:
        wire = store.one('stream', 'field_' + field)
        unit = store.one('stream', 'unit_' + field)
        if not isinstance(wire, str) or not isinstance(unit, str) or unit not in UNITS[field]:
            raise ValueError('Invalid wire name or unsupported unit')
        wires[field], units[field] = wire, unit
    if len(set(wires.values())) != len(FIELDS):
        raise ValueError('Duplicate wire alias')
    return wires, units


def _number(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError('Expected a finite real number')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Expected a finite real number')
    return value


def adapt(record, configuration_text):
    """Return canonical Celsius, MPa, kg/hr and J/kg; never mutate inputs."""
    try:
        wires, units = _schema(configuration_text)
        if not isinstance(record, Mapping) or set(record) != {'version', 'values', 'units', 'composition'}:
            raise ValueError('Invalid record fields')
        if not isinstance(record['version'], str) or record['version'] != '2':
            raise ValueError('Wrong record version')
        names = set(wires.values())
        for key in ('values', 'units'):
            if not isinstance(record[key], Mapping) or set(record[key]) != names:
                raise ValueError('Missing or extra wire fields')
        result = {}
        for field in FIELDS:
            wire = wires[field]
            if record['units'][wire] != units[field]:
                raise ValueError('Wire unit mismatch')
            scale, offset = UNITS[field][units[field]]
            value = _number(record['values'][wire]) * scale + offset
            if not math.isfinite(value):
                raise ValueError('Nonfinite converted value')
            result[field] = value
        if result['T'] <= -273.15 or result['P'] <= 0 or result['m_dot'] < 0:
            raise ValueError('Invalid physical stream value')
        composition = record['composition']
        if not isinstance(composition, Mapping) or not composition:
            raise ValueError('Missing composition')
        fractions = []
        for species, fraction in composition.items():
            if not isinstance(species, str) or not species:
                raise ValueError('Invalid species name')
            value = _number(fraction)
            if value < 0:
                raise ValueError('Negative mass fraction')
            fractions.append(value)
        if abs(math.fsum(fractions) - 1.0) > 1e-9:
            raise ValueError('Composition must sum to one')
        result['w'] = dict(composition)
        return result
    except (TypeError, KeyError, OverflowError, AttributeError, RecursionError) as exc:
        raise ValueError('Invalid stream or configuration') from exc


class PublicationSession:
    """Atomically publish complete revisions and preserve isolated history."""

    def __init__(self):
        self._begun = set()
        self._pending = None
        self._current = None
        self._history = {}

    def begin(self, revision):
        if not isinstance(revision, str) or not revision or revision in self._begun:
            raise ValueError('Revision must be a new nonempty string')
        self._begun.add(revision)
        self._pending = revision
        self._current = None

    def publish(self, revision, records, configuration_text):
        if not isinstance(revision, str) or revision != self._pending:
            raise ValueError('Revision is not pending')
        try:
            if not isinstance(records, Mapping) or set(records) != set(BOUNDARIES):
                raise ValueError('Expected exactly seven stream boundaries')
            store = _load_store(configuration_text)
            canonical = {boundary: adapt(records[boundary], configuration_text)
                         for boundary in BOUNDARIES}
            consumers = {}
            for consumer in CONSUMERS:
                units = _consumer_units(store, consumer)
                streams = {}
                for boundary, source in canonical.items():
                    output = {}
                    for field in FIELDS:
                        scale, offset = UNITS[field][units[field]]
                        value = (source[field] - offset) / scale
                        if not math.isfinite(value):
                            raise ValueError('Nonfinite consumer result')
                        output[field] = value
                    output['w'] = copy.deepcopy(source['w'])
                    streams[boundary] = output
                consumers[consumer] = {'units': dict(units), 'streams': streams}
            prepared = {'revision': revision, 'consumers': consumers}
            # Build every stored copy before the state transition.
            new_history = dict(self._history)
            new_history[revision] = copy.deepcopy(prepared)
            new_current = copy.deepcopy(prepared)
        except (TypeError, KeyError, OverflowError, AttributeError, RecursionError) as exc:
            raise ValueError('Invalid publication') from exc
        self._history = new_history
        self._current = new_current
        self._pending = None

    def snapshot(self):
        if self._current is None:
            raise ValueError('No accepted current revision')
        return copy.deepcopy(self._current)

    def history(self):
        return copy.deepcopy(self._history)
