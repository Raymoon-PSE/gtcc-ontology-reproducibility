"""Independent indexed JSON registry and canonical integration. Standard library only."""
import copy
import json
import math

REQUIRED = frozenset(('gt_exhaust', 'hp_steam', 'hot_reheat', 'lp_steam', 'st_exhaust', 'cold_reheat', 'condensate'))
QUANTITIES = {'temperature': 'T', 'pressure': 'P', 'mass_flow': 'm_dot'}
UNITS = {'temperature': {'degC', 'K'}, 'pressure': {'MPa', 'bar', 'Pa'}, 'mass_flow': {'kg/h', 'kg/s'}}

class ContractError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(detail)

def fail(code, detail):
    raise ContractError(code, detail)

def rejection(code, detail):
    return {'status': 'rejected', 'error': {'code': code, 'detail': str(detail)}}

def name(value):
    if not isinstance(value, str) or not value:
        fail('INVALID_SCHEMA', 'Expected a nonempty identifier string')
    return value

def identity(record):
    if 'namespace' not in record:
        fail('AMBIGUOUS_MAPPING', 'Qualified endpoint has no namespace')
    return tuple(name(record[k]) for k in ('provider_id', 'namespace', 'local_port_id'))

def insert(index, key, value, code='AMBIGUOUS_MAPPING'):
    if key in index and index[key] != value:
        fail(code, 'Conflicting assertions for ' + str(key))
    index[key] = copy.deepcopy(value)

def closure(parents, start):
    seen = set()
    current = start
    while current is not None:
        if current in seen or current not in parents:
            fail('UNRESOLVED_CLASS', 'Missing or cyclic class: ' + str(current))
        seen.add(current)
        current = parents[current]
    return sorted(seen)

def unit_check(quantity, unit):
    if not isinstance(quantity, str) or not isinstance(unit, str) or quantity not in UNITS or unit not in UNITS[quantity]:
        fail('INCOMPATIBLE_UNIT', 'Unsupported quantity/unit: ' + str((quantity, unit)))

def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail('INVALID_VALUE', 'Physical values must be JSON numbers')
    try:
        value = float(value)
    except (OverflowError, ValueError):
        fail('INVALID_VALUE', 'Unrepresentable numeric value')
    if not math.isfinite(value):
        fail('INVALID_VALUE', 'Physical value must be finite')
    return value

def normalize_quantity(quantity, value, unit):
    unit_check(quantity, unit)
    value = numeric(value)
    if unit == 'K':
        value -= 273.15
    elif unit == 'bar':
        value *= 0.1
    elif unit == 'Pa':
        value /= 1000000
    elif unit == 'kg/s':
        value *= 3600
    if not math.isfinite(value) or (quantity == 'temperature' and value <= -273.15) or (quantity == 'pressure' and value <= 0) or (quantity == 'mass_flow' and value < 0):
        fail('INVALID_VALUE', 'Physical value outside its domain')
    return value

class Registry:
    """Tuple-keyed indexes preserve qualified identities and drive every join."""
    def __init__(self, providers, mapping, classes, requested):
        self.versions = {}
        self.types = {}
        self.equipment = {}
        self.ports = {}
        self.fields = {}
        self.boundaries = {}
        self.type_maps = {}
        self.canonical_parents = copy.deepcopy(classes['canonical_parent'])
        self.mapping_version = name(mapping['mapping_version'])
        for provider in providers:
            pid = name(provider['provider_id'])
            insert(self.versions, pid, name(provider['version']), 'VERSION_MISMATCH')
            for t in provider['types']:
                parent = t['parent_type_id']
                insert(self.types, (pid, name(t['local_type_id'])), None if parent is None else (pid, name(parent)), 'UNRESOLVED_CLASS')
            for e in provider['equipment']:
                insert(self.equipment, (pid, name(e['local_equipment_id'])), name(e['local_type_id']))
            for fs, fields in provider['field_sets'].items():
                fs = name(fs)
                for f in fields:
                    insert(self.fields, (pid, fs, name(f['local_key'])), (name(f['quantity']), name(f['unit'])))
            for p in provider['ports']:
                p = dict(p, provider_id=pid)
                insert(self.ports, identity(p), {k: name(p[k]) for k in ('local_equipment_id', 'direction', 'field_set_id')})
        if len(self.versions) != 2:
            fail('INVALID_SCHEMA', 'Exactly two providers required')
        if self.versions != requested or self.versions != mapping['provider_versions']:
            fail('VERSION_MISMATCH', 'Requested, mapping and provider versions must agree')
        # Snapshot mapping version follows the greatest released provider revision.
        if self.mapping_version != max(self.versions.values(), key=lambda x: tuple(int(n) for n in x.split('.'))):
            fail('VERSION_MISMATCH', 'Mapping revision does not match provider snapshot')
        for b in mapping['boundaries']:
            insert(self.boundaries, name(b['canonical_boundary_id']), (identity(b['producer']), identity(b['consumer'])))
        if REQUIRED - self.boundaries.keys():
            fail('MISSING_BOUNDARY', 'Required boundary absent')
        if self.boundaries.keys() != REQUIRED:
            fail('INVALID_SCHEMA', 'Unexpected canonical boundary')
        used = set()
        for bid, endpoints in self.boundaries.items():
            for endpoint, direction in zip(endpoints, ('out', 'in')):
                if endpoint in used:
                    fail('DUPLICATE_BOUNDARY', 'Endpoint reused across canonical boundaries')
                used.add(endpoint)
                if endpoint not in self.ports or self.ports[endpoint]['direction'] != direction:
                    fail('INVALID_SCHEMA', 'Unresolved endpoint or incorrect direction: ' + str(endpoint))
        for cls, parent in self.canonical_parents.items():
            name(cls)
            if parent is not None:
                name(parent)
            closure(self.canonical_parents, cls)
        self.local_closures = {key: closure(self.types, key) for key in self.types}
        for entry in classes['provider_type_mappings']:
            key = (name(entry['provider']), name(entry['local_type']))
            target = name(entry['canonical_type'])
            if key not in self.types or target not in self.canonical_parents:
                fail('UNRESOLVED_CLASS', 'Type mapping refers to an absent class')
            insert(self.type_maps, key, target)
        self.equipment_closures = {}
        for key, local in self.equipment.items():
            local_key = (key[0], local)
            if local_key not in self.local_closures:
                fail('UNRESOLVED_CLASS', 'Equipment class missing')
            canonical = set()
            for ancestor in self.local_closures[local_key]:
                if ancestor in self.type_maps:
                    canonical.update(closure(self.canonical_parents, self.type_maps[ancestor]))
            if 'EngineeringAsset' not in canonical:
                fail('UNRESOLVED_CLASS', 'Equipment has no explicit EngineeringAsset ancestry')
            self.equipment_closures[key] = sorted(canonical)
        mapped_fields = {}
        for f in mapping['field_mappings']:
            key = tuple(name(f[k]) for k in ('provider_id', 'field_set_id', 'local_key'))
            insert(mapped_fields, key, (name(f['canonical_quantity']), name(f['declared_unit'])))
        if mapped_fields.keys() != self.fields.keys():
            fail('INVALID_SCHEMA', 'Field mappings must cover exactly native declared fields')
        self.field_sets = {}
        for key, spec in self.fields.items():
            quantity, unit = spec
            mq, mu = mapped_fields[key]
            unit_check(quantity, unit)
            unit_check(mq, mu)
            if mq != quantity:
                fail('AMBIGUOUS_MAPPING', 'Field quantity contradicts native declaration')
            if mu != unit:
                fail('INCOMPATIBLE_UNIT', 'Mapped unit contradicts native declaration')
            field_set = self.field_sets.setdefault(key[:2], {})
            if quantity in field_set:
                fail('AMBIGUOUS_MAPPING', 'More than one field for quantity')
            field_set[quantity] = (key[2], unit)
        for key, fields in self.field_sets.items():
            if fields.keys() != QUANTITIES.keys():
                fail('INVALID_SCHEMA', 'Incomplete scalar field set')
        for endpoint, port in self.ports.items():
            if (endpoint[0], port['local_equipment_id']) not in self.equipment or (endpoint[0], port['field_set_id']) not in self.field_sets or port['direction'] not in ('in', 'out'):
                fail('INVALID_SCHEMA', 'Invalid equipment, field set or direction')

    def descriptor(self, endpoint):
        pid, namespace, local_port = endpoint
        port = self.ports[endpoint]
        equipment_key = (pid, port['local_equipment_id'])
        local_type = self.equipment[equipment_key]
        provenance = {QUANTITIES[q]: {'field': f, 'unit': u} for q, (f, u) in self.field_sets[(pid, port['field_set_id'])].items()}
        provenance['w'] = {'field': 'composition', 'unit': 'mass_fraction'}
        return {'provider_id': pid, 'namespace': namespace, 'local_port_id': local_port, 'schema_version': self.versions[pid], 'local_equipment_id': equipment_key[1], 'local_type_id': local_type, 'local_ancestors': sorted(t[1] for t in self.local_closures[(pid, local_type)]), 'canonical_ancestors': list(self.equipment_closures[equipment_key]), 'provenance': provenance}

    def observe(self, endpoint, payload):
        port = self.ports[endpoint]
        fields = self.field_sets[(endpoint[0], port['field_set_id'])]
        values = payload['fields']
        if not isinstance(values, dict) or values.keys() != {f for f, u in fields.values()}:
            fail('INVALID_SCHEMA', 'Payload aliases must equal native field aliases')
        output = {QUANTITIES[q]: normalize_quantity(q, values[f], u) for q, (f, u) in fields.items()}
        composition = payload['composition']
        if not isinstance(composition, dict):
            fail('INVALID_SCHEMA', 'Missing/non-object composition')
        if not composition:
            fail('INVALID_VALUE', 'Composition must be nonempty')
        for species, fraction in composition.items():
            name(species)
            if numeric(fraction) < 0:
                fail('INVALID_VALUE', 'Negative mass fraction')
        if not math.isclose(sum(composition.values()), 1, rel_tol=0, abs_tol=1e-8):
            fail('INVALID_VALUE', 'Composition does not sum to one')
        output['w'] = copy.deepcopy(composition)
        return output

def integrate(providers, boundary_mapping, canonical_classes, payloads, requested_versions):
    try:
        registry = Registry(providers, boundary_mapping, canonical_classes, requested_versions)
        observations = {}
        for payload in payloads:
            endpoint = identity(payload['endpoint'])
            if endpoint[0] not in registry.versions or payload['schema_version'] != registry.versions[endpoint[0]]:
                fail('VERSION_MISMATCH', 'Payload version does not match provider')
            if endpoint in observations:
                fail('INVALID_SCHEMA', 'Repeated endpoint observation')
            observations[endpoint] = payload
        required_endpoints = {e for pair in registry.boundaries.values() for e in pair}
        if observations.keys() != required_endpoints:
            fail('INVALID_SCHEMA', 'Payload endpoint coverage differs from mapping')
        boundaries = []
        for bid, (producer, consumer) in sorted(registry.boundaries.items()):
            left = registry.observe(producer, observations[producer])
            right = registry.observe(consumer, observations[consumer])
            for key in ('T', 'P', 'm_dot'):
                if abs(left[key] - right[key]) > 1e-6 + 1e-10 * abs(left[key]):
                    fail('INVALID_VALUE', 'Endpoint scalar disagreement for ' + bid)
            if left['w'].keys() != right['w'].keys() or any(abs(left['w'][s] - right['w'][s]) > 1e-8 for s in left['w']):
                fail('INVALID_VALUE', 'Endpoint composition disagreement for ' + bid)
            prod = registry.descriptor(producer)
            boundaries.append(dict(boundary_id=bid, **left, producer=prod, consumer=registry.descriptor(consumer), canonical_ancestors=list(prod['canonical_ancestors'])))
        return {'status': 'accepted', 'boundaries': boundaries}
    except ContractError as error:
        return rejection(error.code, str(error))
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError) as error:
        return rejection('INVALID_SCHEMA', 'Malformed input: ' + str(error))

def query_all(result):
    return copy.deepcopy(sorted(result['boundaries'], key=lambda b: b['boundary_id']))

def query_by_ancestor(result, canonical_class):
    return copy.deepcopy([b for b in result['boundaries'] if canonical_class in b['producer']['canonical_ancestors']])

def query_returns(result, requested_versions):
    versions = {}
    for b in result['boundaries']:
        for role in ('producer', 'consumer'):
            endpoint = b[role]
            if endpoint['provider_id'] in versions and versions[endpoint['provider_id']] != endpoint['schema_version']:
                return rejection('VERSION_MISMATCH', 'Mixed versions in result')
            versions[endpoint['provider_id']] = endpoint['schema_version']
    if versions != requested_versions:
        return rejection('VERSION_MISMATCH', 'Requested versions differ from canonical records')
    return copy.deepcopy([b for b in result['boundaries'] if b['boundary_id'] in ('cold_reheat', 'condensate')])

def export_native(providers, boundary_mapping, canonical_classes, requested_versions):
    """Deterministic serialization of the actual indexes used for integration."""
    registry = Registry(providers, boundary_mapping, canonical_classes, requested_versions)
    return {label: [{'key': key, 'value': value} for key, value in sorted(index.items(), key=lambda item: str(item[0]))] if isinstance(index, dict) else index for label, index in vars(registry).items()}
