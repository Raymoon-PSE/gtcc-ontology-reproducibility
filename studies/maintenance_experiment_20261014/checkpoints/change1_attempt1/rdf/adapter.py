"""Validate a versioned stream using its runtime RDF schema."""
import math
from collections.abc import Mapping
from numbers import Real

from rdflib import Literal
from stores import NS, RDFStore

FIELDS = ('T', 'P', 'm_dot', 'h')
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
            if subject != NS.stream or predicate not in {NS[p] for p in expected} or not isinstance(value, Literal):
                raise ValueError('invalid schema declaration')
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
