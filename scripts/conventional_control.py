"""Independent conventional contract checks over resolved JSON records.

No RDF or production-validator imports. This implements the same declared
policy independently, not an intentionally weak unvalidated baseline.
Inputs retain multivalued fields and resolved class membership.
"""
PREFIX = 'http://plantmind.io/ontology/gtcc#'


def check_records(records, contract):
    issues = []
    def issue(code, subject, prop):
        issues.append((code, subject, prop))
    for subject, expected in contract['devices'].items():
        data = records.get(subject, {})
        states = data.get('mech_hasDataStatus', [])
        allowed = [[PREFIX+'mech_DataStatus_'+s] for s in ('FULL','PARTIAL','NONE')]
        if states not in allowed:
            issue('data_status', subject, 'mech_hasDataStatus')
    for subject, data in records.items():
        if not data.get('mech_hasDataStatus'):
            continue
        if subject not in contract['devices']:
            issue('unregistered_device', subject, 'mech_hasDataStatus')
            continue
        expected = contract['devices'][subject]
        for prop in ('unit_id', 'part_of'):
            if data.get(prop, []) != [expected[prop]]:
                issue('binding', subject, prop)
        if data.get('module_id') and data['module_id'] != [expected['module_id']]:
            issue('binding', subject, 'module_id')
        for prop, key in (('mech_unitId','unit_id'),('mech_deviceType','model')):
            if data.get(prop) and data[prop] != [expected[key]]:
                issue('routing', subject, prop)
        if expected['class'] not in data.get('types', []):
            issue('equipment_type', subject, 'types')
    for subject, expected in contract['upstream'].items():
        if sorted(records.get(subject, {}).get('upstream_of', [])) != sorted(expected):
            issue('connection', subject, 'upstream_of')
    for subject, ports in contract['ports'].items():
        for prop, expected in ports.items():
            if sorted(records.get(subject, {}).get(prop, [])) != sorted(expected):
                issue('port', subject, prop)
    for subject, cls in contract['stream_classes'].items():
        if cls not in records.get(subject, {}).get('types', []):
            issue('stream_type', subject, 'types')
    return sorted(issues)


def query_records(rows):
    """Conventional joins for the six declared retrieval tasks, without RDF."""
    def values(subject, prop):
        return rows.get(subject, {}).get(PREFIX+prop, [])
    out = {f'Q{i}': [] for i in range(1, 7)}
    for subject, props in rows.items():
        if PREFIX+'mech_Priority_P1' in values(subject, 'mech_hasPriority'):
            for life in values(subject, 'mech_combinedLifeFraction'):
                if float(life) > .5:
                    out['Q1'].append({'device':subject, 'life':life})
        for status in values(subject, 'mech_hasDataStatus'):
            out['Q2'].append({'device':subject, 'status':status})
            for why in values(subject, 'justified_by'):
                out['Q5'].append({'unit':subject, 'rationale':why})
        for value in values(subject, 'runtime_value'):
            out['Q4'].append({'observation':subject, 'value':value})
        for destruction in values(subject, 'runtime_exergyDestructionPct'):
            for device in rows:
                if subject not in values(device, 'part_of'):
                    continue
                for fault in values(device, 'has_fault') or [None]:
                    row = {'module':subject,'destructionPct':destruction,'device':device}
                    if fault is not None:
                        row['fault'] = fault
                    if row not in out['Q6']:
                        out['Q6'].append(row)
    comp, turb = PREFIX+'COMP-001', PREFIX+'EXP-001'
    for module in values(comp, 'part_of'):
        if module in values(turb, 'part_of'):
            for surge in values(comp, 'mech_surgeMarginPct'):
                for creep in values(turb, 'mech_creepLifeFraction'):
                    out['Q3'].append({'compressor':comp,'turbine':turb,'surge':surge,'creep':creep})
    return out
