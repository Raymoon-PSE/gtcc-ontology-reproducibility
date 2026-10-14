"""Validate external streams against a freshly queried JSONStore schema."""
import json
import math
from collections.abc import Mapping
from numbers import Real

from stores import JSONStore

FIELDS = ('T', 'P', 'm_dot', 'h')
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


def _schema(text):
    # Validate serialization before the native store can collapse duplicates.
    raw = json.loads(text, object_pairs_hook=_object)
    expected = {'version'} | {'field_' + f for f in FIELDS} | {'unit_' + f for f in FIELDS}
    if not isinstance(raw, dict) or set(raw) != {'stream'}:
        raise ValueError('Expected a stream schema')
    declarations = raw['stream']
    if not isinstance(declarations, dict) or set(declarations) != expected:
        raise ValueError('Invalid schema declarations')
    for objects in declarations.values():
        if not isinstance(objects, list) or len(objects) != 1:
            raise ValueError('Expected exactly one declaration per slot')
    store = JSONStore.loads(text)
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
