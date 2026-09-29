"""Closed-world engineering contracts for the configured GTCC runtime.

Checks declared bindings before numerical execution. This validates consistency
with an independently maintained contract, not physical correctness of the
contract, measured plant performance, or arbitrary GTCC topologies. A plain-data
adapter is supplied to avoid attributing validation policy to RDF alone.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from rdflib import Graph
from rdflib.namespace import RDF, RDFS
from eklm.kas.legacy_bridge.graph import PM

@dataclass(frozen=True, order=True)
class Finding:
    code: str
    subject: str
    predicate: str
    expected: str
    actual: str

class IntegrityError(ValueError):
    def __init__(self, findings):
        self.findings = tuple(findings)
        super().__init__('Engineering integrity rejected: ' + '; '.join(
            f'{f.code} {f.subject} {f.predicate}: expected {f.expected}, got {f.actual}'
            for f in findings))

def default_contract():
    return json.loads(Path(__file__).with_name('integrity_contract.json').read_text())

def graph_records(g, contract=None):
    """Lossless multi-valued projection of the checked vocabulary.

    No selecting a convenient first value: contradictory declarations must fail.
    Class closure is schema traversal, not a complete OWL reasoner.
    """
    props = ('unit_id','module_id','part_of','mech_deviceType','mech_unitId',
             'mech_hasDataStatus','upstream_of','has_inlet_stream','has_outlet_stream')
    c = default_contract() if contract is None else contract
    # Restrict projection to the contract scope plus ALL declared mechanical
    # devices, so unknown devices cannot disappear through scope filtering.
    from rdflib import URIRef
    subjects = set(g.subjects(PM.mech_hasDataStatus, None))
    subjects.update(URIRef(s) for section in ('ports','upstream','stream_classes') for s in c[section])
    rows = {}
    for s in subjects:
        rec = {p: sorted(str(o) for o in g.objects(s, PM[p])) for p in props}
        types = set(g.objects(s, RDF.type)); closure = set(types); queue = list(types)
        while queue:
            c = queue.pop()
            for parent in g.objects(c, RDFS.subClassOf):
                if parent not in closure: closure.add(parent); queue.append(parent)
        rec['types'] = sorted(map(str, closure))
        if any(rec.values()): rows[str(s)] = rec
    return rows

def validate_records(rows, contract=None):
    """Centralized non-RDF control. Same policy, no RDF calls or graph loader."""
    c = default_contract() if contract is None else contract
    findings = []
    def emit(code,s,p,expected,actual):
        findings.append(Finding(code,s,p,json.dumps(expected,sort_keys=True),json.dumps(actual,sort_keys=True)))
    # A contract record anchors BOTH descriptive identifiers and runtime routing.
    for s, rec in sorted(rows.items()):
        if not rec.get('mech_hasDataStatus'): continue
        expected = c['devices'].get(s)
        if expected is None:
            emit('unregistered_device',s,'mech_hasDataStatus','registered device',rec['mech_hasDataStatus']); continue
        for p in ('unit_id','part_of'):
            if rec.get(p,[]) != [expected[p]]:emit('binding',s,p,[expected[p]],rec.get(p,[]))
        # module_id is optional in the existing ST catalog, but conflicts fail.
        if rec.get('module_id') and rec['module_id'] != [expected['module_id']]:
            emit('binding',s,'module_id',[expected['module_id']],rec['module_id'])
        for p,key in [('mech_unitId','unit_id'),('mech_deviceType','model')]:
            if rec.get(p) and rec[p] != [expected[key]]:emit('routing',s,p,[expected[key]],rec[p])
        if expected['class'] not in rec.get('types',[]):
            emit('equipment_type',s,'types',expected['class'],rec.get('types',[]))
    # Required arcs are for the declared public GT configuration only. Optional
    # bypasses/new layouts require an explicit revised engineering contract.
    for s, targets in c['upstream'].items():
        actual = sorted(rows.get(s,{}).get('upstream_of',[]))
        if actual != sorted(targets):emit('connection',s,'upstream_of',sorted(targets),actual)
    for s, ports in c['ports'].items():
        for p, targets in ports.items():
            actual = sorted(rows.get(s,{}).get(p,[]))
            if actual != sorted(targets):emit('port',s,p,sorted(targets),actual)
    for s, cls in c['stream_classes'].items():
        actual = rows.get(s,{}).get('types',[])
        if cls not in actual:emit('stream_type',s,'types',cls,actual)
    return sorted(findings)

def validate_graph(g, contract=None):
    """RDF arm: ontology class closure plus the same engineering constraints."""
    if not isinstance(g, Graph): raise TypeError('Expected rdflib.Graph')
    return validate_records(graph_records(g, contract), contract)

def require_valid_graph(g, contract=None):
    findings = validate_graph(g, contract)
    if findings: raise IntegrityError(findings)
    return {'passed':True,'contract':(contract or default_contract())['version'],
            'scope':'six registered mechanical bindings and specified GT arcs/ports',
            'physical_validation':False}


def clear_runtime_evidence(g, output=None):
    """Invalidate previous evidence even when preflight fails before a solve."""
    from eklm.kas.legacy_bridge.mech_bridge import _PROP_MAP
    for prop in set(_PROP_MAP.values()):
        g.remove((None, prop, None))
    for subject in list(set(g.subjects())):
        if str(subject).startswith((str(PM.RuntimeFinding_), str(PM.RuntimeDiagnosis_), str(PM.RuntimeObservation_))):
            g.remove((subject, None, None))
    if output is not None:
        output.pop('ontology_runtime', None)
        output.pop('mech_results', None)
        for key in _PROP_MAP:
            output.pop(key, None)
