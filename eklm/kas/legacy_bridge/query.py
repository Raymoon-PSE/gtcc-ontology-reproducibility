"""SPARQL query interface for the PlantMind ontology.

Provides pre-built queries for common diagnostic and analysis tasks.
"""

from rdflib import Graph
from rdflib.namespace import RDFS

from eklm.kas.legacy_bridge.graph import PM

_NS = {"pm": PM, "rdfs": RDFS}


def query_off_design_kpis(g: Graph) -> list[dict]:
    """Find all KPIs that are out of target."""
    q = """
    SELECT ?kpi ?label ?value ?status
    WHERE {
        ?kpi a/rdfs:subClassOf* pm:KPI .
        ?kpi pm:kpi_status ?status .
        OPTIONAL { ?kpi rdfs:label ?label }
        OPTIONAL { ?kpi pm:kpi_value ?value }
        FILTER(?status = "out_of_target")
    }
    """
    results = []
    for row in g.query(q, initNs=_NS):
        results.append({
            "uri": str(row.kpi),
            "label": str(row.label) if row.label is not None else "",
            "value": float(row.value) if row.value is not None else None,
            "status": str(row.status),
        })
    return results


def query_upstream_units(g: Graph, unit_uri: str) -> list[dict]:
    """Find all units upstream of a given unit (uses transitivity).

    Args:
        unit_uri: Full URI of the target unit.

    Returns:
        List of upstream units (labels and URIs).
    """
    q = """
    SELECT DISTINCT ?upstream ?label
    WHERE {
        ?upstream pm:upstream_of+ <%s> .
        OPTIONAL { ?upstream rdfs:label ?label }
    }
    """ % unit_uri
    results = []
    for row in g.query(q, initNs=_NS):
        results.append({
            "uri": str(row.upstream),
            "label": str(row.label) if row.label is not None else "",
        })
    return results


def query_downstream_impact(g: Graph, unit_uri: str) -> list[dict]:
    """Find all units/streams affected by changes in a given unit.

    Traverses asserted upstream_of paths. This is connectivity, not causal proof.
    """
    q = """
    SELECT DISTINCT ?downstream ?label
    WHERE {
        <%s> pm:upstream_of+ ?downstream .
        OPTIONAL { ?downstream rdfs:label ?label }
    }
    """ % unit_uri
    results = []
    for row in g.query(q, initNs=_NS):
        results.append({
            "uri": str(row.downstream),
            "label": str(row.label) if row.label is not None else "",
        })
    return results


def query_unit_streams(g: Graph, unit_uri: str) -> dict:
    """Get inlet and outlet streams for a unit."""
    inlets = []
    outlets = []

    q_in = """
    SELECT ?stream ?label ?sid
    WHERE {
        <%s> pm:has_inlet_stream ?stream .
        OPTIONAL { ?stream rdfs:label ?label }
        OPTIONAL { ?stream pm:stream_id ?sid }
    }
    """ % unit_uri
    for row in g.query(q_in, initNs=_NS):
        inlets.append({
            "uri": str(row.stream),
            "label": str(row.label) if row.label is not None else "",
            "stream_id": str(row.sid) if row.sid is not None else "",
        })

    q_out = """
    SELECT ?stream ?label ?sid
    WHERE {
        <%s> pm:has_outlet_stream ?stream .
        OPTIONAL { ?stream rdfs:label ?label }
        OPTIONAL { ?stream pm:stream_id ?sid }
    }
    """ % unit_uri
    for row in g.query(q_out, initNs=_NS):
        outlets.append({
            "uri": str(row.stream),
            "label": str(row.label) if row.label is not None else "",
            "stream_id": str(row.sid) if row.sid is not None else "",
        })

    return {"inlets": inlets, "outlets": outlets}


def query_stream_state(g: Graph, stream_id: str) -> dict | None:
    """Get the current state of a stream by ID."""
    q = """
    SELECT ?stream ?T ?P ?m_dot ?h ?s ?runtime_current
    WHERE {
        ?stream pm:stream_id "%s" .
        OPTIONAL { ?stream pm:stream_T ?T }
        OPTIONAL { ?stream pm:stream_P ?P }
        OPTIONAL { ?stream pm:stream_m_dot ?m_dot }
        OPTIONAL { ?stream pm:stream_h ?h }
        OPTIONAL { ?stream pm:stream_s ?s }
        OPTIONAL { ?stream pm:runtime_state_updated ?runtime_current }
    }
    """ % stream_id
    for row in g.query(q, initNs=_NS):
        return {
            "stream_id": stream_id,
            "runtime_updated": bool(row.runtime_current.toPython()) if row.runtime_current is not None else False,
            "T": float(row.T) if row.T is not None else None,
            "P": float(row.P) if row.P is not None else None,
            "m_dot": float(row.m_dot) if row.m_dot is not None else None,
            "h": float(row.h) if row.h is not None else None,
            "s": float(row.s) if row.s is not None else None,
        }
    return None


def query_design_rationales(g: Graph, unit_uri: str | None = None) -> list[dict]:
    """Get design rationales, optionally filtered by unit."""
    if unit_uri:
        q = """
        SELECT ?dr ?label ?rationale
        WHERE {
            <%s> pm:justified_by ?dr .
            OPTIONAL { ?dr rdfs:label ?label }
            OPTIONAL { ?dr pm:rationale ?rationale }
            OPTIONAL { ?dr pm:dr_rationale ?rationale }
        }
        """ % unit_uri
    else:
        q = """
        SELECT ?dr ?label ?rationale
        WHERE {
            ?dr a pm:DesignRationale .
            OPTIONAL { ?dr rdfs:label ?label }
            OPTIONAL { ?dr pm:rationale ?rationale }
            OPTIONAL { ?dr pm:dr_rationale ?rationale }
        }
        """
    results = []
    for row in g.query(q, initNs=_NS):
        results.append({
            "uri": str(row.dr),
            "label": str(row.label) if row.label is not None else "",
            "rationale": str(row.rationale) if row.rationale is not None else "",
        })
    return results


def query_module_summary(g: Graph) -> list[dict]:
    """Get all ProcessModules with their unit counts."""
    q = """
    SELECT ?mod ?label ?mid (COUNT(?unit) AS ?n_units)
    WHERE {
        ?mod a/rdfs:subClassOf* pm:ProcessModule .
        OPTIONAL { ?mod rdfs:label ?label }
        OPTIONAL { ?mod pm:module_id ?mid }
        OPTIONAL { ?unit pm:part_of ?mod }
    }
    GROUP BY ?mod ?label ?mid
    """
    results = []
    for row in g.query(q, initNs=_NS):
        results.append({
            "uri": str(row.mod),
            "label": str(row.label) if row.label is not None else "",
            "module_id": str(row.mid) if row.mid is not None else "",
            "n_units": int(row.n_units) if row.n_units is not None else 0,
        })
    return results
