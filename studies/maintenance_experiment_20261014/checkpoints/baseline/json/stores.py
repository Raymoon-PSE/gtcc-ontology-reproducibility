"""Equivalent indexed JSON and RDF/RDFS stores for explicit engineering facts.

No OWL reasoner is implied. Both receive identical authored facts, share contract
rules, and support transitive subclass traversal. Representation is the variable.
"""
from __future__ import annotations
import json
from collections import defaultdict
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS

NS = Namespace('urn:eklm:revision:')
RELATIONS = {'type', 'subclass', 'source', 'target', 'binding', 'depends_on'}
PREDICATES = {'type': RDF.type, 'subclass': RDFS.subClassOf}

class ContractError(ValueError):
    pass

class Store:
    def one(self, subject, predicate):
        values = self.values(subject, predicate)
        if len(values) != 1:
            raise ContractError(f'{subject}.{predicate}: expected one value, got {len(values)}')
        return values[0]

    def ancestors(self, cls):
        seen, queue = set(), [cls]
        while queue:
            value = queue.pop()
            if value in seen:
                continue
            seen.add(value)
            queue.extend(self.values(value, 'subclass'))
        return seen

    def instance_of(self, subject, cls):
        return any(cls in self.ancestors(t) for t in self.values(subject, 'type'))

class JSONStore(Store):
    name = 'json'
    def __init__(self, facts):
        index = defaultdict(lambda: defaultdict(set))
        for s, p, o in facts:
            index[s][p].add(o)
        self.index = {s:{p:sorted(v) for p,v in preds.items()} for s,preds in index.items()}
    def values(self, subject, predicate):
        return list(self.index.get(subject, {}).get(predicate, []))
    def dumps(self):
        return json.dumps(self.index, sort_keys=True, separators=(',', ':'))
    @classmethod
    def loads(cls, payload):
        index = json.loads(payload)
        return cls((s,p,o) for s,ps in index.items() for p,os in ps.items() for o in os)

class RDFStore(Store):
    name = 'rdf'
    def __init__(self, facts):
        self.graph = Graph()
        self.graph.bind('rev', NS)
        for s,p,o in facts:
            self.graph.add((NS[s], PREDICATES.get(p, NS[p]), NS[o] if p in RELATIONS else Literal(o)))
    def values(self, subject, predicate):
        values = self.graph.objects(NS[subject], PREDICATES.get(predicate, NS[predicate]))
        return sorted(str(o)[len(str(NS)):] if isinstance(o,URIRef) and str(o).startswith(str(NS)) else str(o) for o in values)
    def dumps(self):
        return self.graph.serialize(format='turtle')
    @classmethod
    def loads(cls, payload):
        obj=cls([]); obj.graph.parse(data=payload,format='turtle');return obj

STORES = {'rdf': RDFStore, 'json': JSONStore}

def fact_delta(before, after):
    before,after=set(map(tuple,before)),set(map(tuple,after))
    removed,added=before-after,after-before
    return {'removed':sorted(removed),'added':sorted(added),
            'logical_fact_operations':len(removed)+len(added),
            'changed_slots':len({(s,p) for s,p,o in removed|added}),
            'affected_subjects':len({s for s,p,o in removed|added}),
            'interpretation':'representation-independent authored configuration changes; not measured developer effort'}
