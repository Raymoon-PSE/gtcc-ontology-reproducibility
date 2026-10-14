"""Validate a versioned stream using its runtime RDF schema."""
import math
from copy import deepcopy
from collections.abc import Mapping
from numbers import Real

from rdflib import Literal
from stores import NS, RDFStore

FIELDS = ('T', 'P', 'm_dot', 'h')
CONSUMERS = ('dashboard', 'report', 'diagnostics')
BOUNDARIES = ('gt_exhaust', 'hp_steam', 'hot_reheat', 'lp_steam', 'st_exhaust', 'cold_reheat', 'condensate')
CONVERSIONS = {
    'T': {'degC': (1.0, 0.0), 'K': (1.0, -273.15)},
    'P': {'MPa': (1.0, 0.0), 'kPa': (0.001, 0.0), 'Pa': (0.000001, 0.0)},
    'm_dot': {'kg/hr': (1.0, 0.0), 'kg/s': (3600.0, 0.0)},
    'h': {'J/kg': (1.0, 0.0), 'kJ/kg': (1000.0, 0.0)},
}


def _schema(text):
    if not isinstance(text, str):
        raise ValueError('configuration must be serialized text')
    try:
        store = RDFStore.loads(text)
        expected = {'version'} | {'%s_%s' % (kind, f) for kind in ('field', 'unit') for f in FIELDS}
        for subject, predicate, value in store.graph:
            allowed = ({NS[p] for p in expected} if subject == NS.stream else
                       {NS['unit_' + f] for f in FIELDS} if subject in {NS[c] for c in CONSUMERS} else set())
            if predicate not in allowed or not isinstance(value, Literal):
                raise ValueError('invalid schema declaration')
        for consumer in CONSUMERS:
            if any(store.graph.triples((NS[consumer], None, None))):
                _consumer_units(store, consumer)
        if store.one('stream', 'version') != '2':
            raise ValueError('unsupported schema version')
        schema = {}
        for field in FIELDS:
            wire = store.one('stream', 'field_' + field)
            unit = store.one('stream', 'unit_' + field)
            if not wire or unit not in CONVERSIONS[field]:
                raise ValueError('invalid wire name or unsupported unit')
            schema[field] = (wire, unit)
        if len({wire for wire, _ in schema.values()}) != len(FIELDS):
            raise ValueError('duplicate wire alias')
        return schema
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('invalid RDF configuration') from exc


def _number(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError('expected finite real number')
    try:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('expected finite real number')
        return result
    except (OverflowError, TypeError) as exc:
        raise ValueError('expected finite real number') from exc


def adapt(record, configuration_text):
    schema = _schema(configuration_text)
    if not isinstance(record, Mapping) or set(record) != {'version', 'values', 'units', 'composition'}:
        raise ValueError('invalid record fields')
    if not isinstance(record['version'], str) or record['version'] != '2':
        raise ValueError('wrong record version')
    aliases = {wire for wire, _ in schema.values()}
    for key in ('values', 'units'):
        if not isinstance(record[key], Mapping) or set(record[key]) != aliases:
            raise ValueError('invalid ' + key + ' fields')
    result = {}
    for field, (wire, unit) in schema.items():
        if record['units'][wire] != unit:
            raise ValueError('mismatched unit')
        scale, offset = CONVERSIONS[field][unit]
        result[field] = _number(record['values'][wire]) * scale + offset
        if not math.isfinite(result[field]):
            raise ValueError('nonfinite converted value')
    if result['T'] <= -273.15 or result['P'] <= 0 or result['m_dot'] < 0:
        raise ValueError('invalid physical stream value')
    composition = record['composition']
    if not isinstance(composition, Mapping) or not composition:
        raise ValueError('composition must be a nonempty mapping')
    fractions = []
    for species, fraction in composition.items():
        if not isinstance(species, str) or not species:
            raise ValueError('invalid species name')
        fraction = _number(fraction)
        if fraction < 0 or fraction > 1 + 1e-9:
            raise ValueError('invalid mass fraction')
        fractions.append(fraction)
    if abs(math.fsum(fractions) - 1) > 1e-9:
        raise ValueError('mass fractions must sum to one')
    result['w'] = dict(composition)
    return result


def _consumer_units(store, consumer):
    units = {}
    for field in FIELDS:
        unit = store.one(consumer, 'unit_' + field)
        if unit not in CONVERSIONS[field]:
            raise ValueError('unsupported consumer unit')
        units[field] = unit
    return units


class PublicationSession:
    """Publish complete multi-consumer snapshots with revision isolation."""

    def __init__(self):
        self._begun = set()
        self._pending = None
        self._current = None
        self._history = {}

    def begin(self, revision):
        if not isinstance(revision, str) or not revision or revision in self._begun:
            raise ValueError('revision must be a new nonempty string')
        self._begun.add(revision)
        self._pending = revision
        self._current = None

    def publish(self, revision, records, configuration_text):
        if not isinstance(revision, str) or self._pending is None or revision != self._pending:
            raise ValueError('revision is not pending')
        if not isinstance(records, Mapping) or set(records) != set(BOUNDARIES):
            raise ValueError('exactly seven boundary records are required')
        # Validate and parse this call's configuration before preparing outputs.
        _schema(configuration_text)
        try:
            store = RDFStore.loads(configuration_text)
        except Exception as exc:
            raise ValueError('invalid RDF configuration') from exc
        consumer_units = {c: _consumer_units(store, c) for c in CONSUMERS}
        canonical = {b: adapt(records[b], configuration_text) for b in BOUNDARIES}
        consumers = {}
        for consumer in CONSUMERS:
            units = consumer_units[consumer]
            streams = {}
            for boundary in BOUNDARIES:
                source = canonical[boundary]
                converted = {}
                for field in FIELDS:
                    scale, offset = CONVERSIONS[field][units[field]]
                    value = (source[field] - offset) / scale
                    if not math.isfinite(value):
                        raise ValueError('nonfinite consumer output')
                    converted[field] = value
                converted['w'] = deepcopy(source['w'])
                streams[boundary] = converted
            consumers[consumer] = {'units': dict(units), 'streams': streams}
        prepared = {'revision': revision, 'consumers': consumers}
        # No session state changes until all boundaries and consumers succeed.
        self._history[revision] = deepcopy(prepared)
        self._current = prepared
        self._pending = None

    def snapshot(self):
        if self._current is None:
            raise ValueError('no current accepted snapshot')
        return deepcopy(self._current)

    def history(self):
        return deepcopy(self._history)
