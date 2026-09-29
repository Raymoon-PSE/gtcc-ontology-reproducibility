"""ABox population — writes simulation results into the RDF graph.

Populates stream state values (T, P, m_dot, h, s), variable values,
and KPI values/status from a converged GTCCResult.
"""

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD

from eklm.kas.legacy_bridge.graph import PM, PM4
from eklm.vdt.analysis.gtcc_loop import GTCCResult
from eklm.vdt.data.streams import Stream


def _set_stream_values(g: Graph, uri: URIRef, s: Stream) -> None:
    """Update stream data properties in the graph."""
    props = {
        PM.stream_T: s.T,
        PM.stream_P: s.P,
        PM.stream_m_dot: s.m_dot,
    }
    if s.h is not None:
        props[PM.stream_h] = s.h / 1000.0  # J/kg -> kJ/kg (ontology convention)
    if s.s is not None:
        props[PM.stream_s] = s.s / 1000.0  # J/kg/K -> kJ/kg/K

    for pred in (PM.stream_T, PM.stream_P, PM.stream_m_dot, PM.stream_h, PM.stream_s):
        g.remove((uri, pred, None))
    g.set((uri, PM.runtime_state_updated, Literal(True)))
    for pred, val in props.items():
        g.add((uri, pred, Literal(round(val, 4), datatype=XSD.decimal)))


def _set_var_value(g: Graph, uri: URIRef, value: float) -> None:
    """Set a variable's computed value."""
    g.remove((uri, PM.var_value, None))
    g.add((uri, PM.var_value, Literal(round(value, 6), datatype=XSD.decimal)))


def _set_kpi(g: Graph, uri: URIRef, value: float,
             target: float | None = None, tol: float | None = None) -> None:
    """Set KPI value and compute status."""
    g.remove((uri, PM.kpi_value, None))
    g.add((uri, PM.kpi_value, Literal(round(value, 4), datatype=XSD.decimal)))

    if target is not None and tol is not None:
        delta = abs(value - target) / abs(target) if target != 0 else 0
        status = "within_target" if delta <= tol else "out_of_target"
    else:
        status = "not_validated"

    g.remove((uri, PM.kpi_status, None))
    g.add((uri, PM.kpi_status, Literal(status)))


def _find_uri(g: Graph, stream_id: str) -> URIRef | None:
    """Find a stream URI by stream_id, searching both namespaces."""
    for ns in [PM, PM4]:
        for s, p, o in g.triples((None, ns["stream_id"], None)):
            if str(o) == stream_id:
                return s
    # Try direct URI construction
    for ns_str, prefix in [("http://plantmind.io/ontology/gtcc#", PM),
                           ("http://www.plantmind.ai/gtcc#", PM4)]:
        candidate = URIRef(ns_str + stream_id.replace("-", "-"))
        if (candidate, None, None) in g:
            return candidate
    return None


def _find_var(g: Graph, symbol: str) -> URIRef | None:
    """Find a variable URI by symbol string."""
    for ns in [PM, PM4]:
        for s, p, o in g.triples((None, ns["symbol"], None)):
            if str(o) == symbol:
                return s
        for s, p, o in g.triples((None, ns["param_symbol"], None)):
            if str(o) == symbol:
                return s
        for s, p, o in g.triples((None, ns["scalar_symbol"], None)):
            if str(o) == symbol:
                return s
    return None


# ── Stream ID to GTCCResult mapping ─────────────────────────────────────

_STREAM_MAP = {
    # GT exhaust is available directly in GTCCResult.
    "7": lambda r: r.s7,
    # M2 HRSG gas path
    "S-008": lambda r: r.m2.unit_21.s8,
    "S-009": lambda r: r.m2.unit_24.s9,
    "S-010": lambda r: r.m2.unit_22.s10,
    "S-011": lambda r: r.m2.unit_25.s11,
    "S-012": lambda r: r.m2.unit_23.s12,
    "S-013": lambda r: r.m2.unit_26.s13,
    "S-014": lambda r: r.m2.unit_27.s14,
    "S-015": lambda r: r.m2.unit_28.s15,
    "S-016": lambda r: r.m2.s16,
    # M2 HRSG steam outputs
    "IS-01": lambda r: r.m2.s_is01,
    "IS-03": lambda r: r.m2.s_is03,
    "IS-05": lambda r: r.m2.s_is05,
    # M3 ST
    "S-025": lambda r: r.m3.unit_31.s25,
    "IS-02": lambda r: r.m3.s_is02,
    "S-026": lambda r: r.m3.unit_33.s26,
    "S-027": lambda r: r.m3.node_3m.s27,
    "S-028": lambda r: r.m3.s28,
    # M4 Condenser
    "IS-06": lambda r: r.m4.s_is06,
}


def populate(g: Graph, result: GTCCResult) -> int:
    """Populate the RDF graph with converged simulation results.

    Args:
        g: The RDF graph (loaded TTL files).
        result: Converged GTCCResult from gtcc_solve().

    Returns:
        Number of triples added/updated.
    """
    count = 0
    # Remove freshness markers before writing the current result snapshot.
    g.remove((None, PM.runtime_state_updated, None))

    # 1. Populate stream values
    for sid, getter in _STREAM_MAP.items():
        uri = _find_uri(g, sid)
        if uri is not None:
            stream = getter(result)
            _set_stream_values(g, uri, stream)
            count += 5

    # 2. Populate key variables
    var_map = {
        "eta^(hpt)": result.m3.eta_hpt,
        "eta^(ipt)": result.m3.eta_ipt,
        "eta^(lpt)": result.m3.eta_lpt,
        "W_dot^(hpt)": result.m3.W_hpt,
        "W_dot^(ipt)": result.m3.W_ipt,
        "W_dot^(lpt)": result.m3.W_lpt,
        "W_dot^(ST,shaft)": result.m3.W_shaft,
        "x^(28)": result.m3.x_28,
    }
    for symbol, value in var_map.items():
        uri = _find_var(g, symbol)
        if uri is not None:
            _set_var_value(g, uri, value)
            count += 1

    # 3. Populate KPIs
    kpi_map = {
        "W_dot^(ST)": (result.m3.W_ST, 202_500, 0.05),
    }
    for symbol, (value, target, tol) in kpi_map.items():
        uri = _find_var(g, symbol)
        if uri is not None:
            _set_kpi(g, uri, value, target, tol)
            count += 2

    return count
