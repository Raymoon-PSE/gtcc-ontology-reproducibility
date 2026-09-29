"""Ontology graph loader — merges 4 TTL files into a single RDF graph.

Handles namespace unification: M4 uses a different base URI than M1-M3.
"""

from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD

# Canonical namespace (M1-M3 use this)
PM = Namespace("http://plantmind.io/ontology/gtcc#")

# M4 namespace (different base URI — will be aliased)
PM4 = Namespace("http://www.plantmind.ai/gtcc#")

# Default TTL file locations
DEFAULT_TTL_DIR = Path(__file__).resolve().parents[2] / "kdl" / "schema" / "catalog"
DEFAULT_TTL_FILES = [
    "PlantMind_GTCC_GT_Module_v1_2.ttl",
    "PlantMind_GTCC_HRSG_Module_v1_1.ttl",
    "PlantMind_GTCC_ST_Module_v1_0.ttl",
    "PlantMind_GTCC_M4_Condenser_v1_0.ttl",
    "PlantMind_GTCC_Mechanical_v1_0.ttl",
]


def load_graph(ttl_dir: Path | str | None = None) -> Graph:
    """Load and merge all 4 TTL files into a single RDF graph.

    Args:
        ttl_dir: Directory containing TTL files. None -> default Protege dir.

    Returns:
        Merged rdflib.Graph with pm: namespace bound.
    """
    if ttl_dir is None:
        ttl_dir = DEFAULT_TTL_DIR
    ttl_dir = Path(ttl_dir)

    g = Graph()
    g.bind("pm", PM)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("owl", OWL)
    g.bind("xsd", XSD)

    for fname in DEFAULT_TTL_FILES:
        fpath = ttl_dir / fname
        if fpath.exists():
            g.parse(str(fpath), format="turtle")

    return g


def get_units(g: Graph) -> list[dict]:
    """Get all ProcessUnit individuals with their properties."""
    query = """
    SELECT ?unit ?label ?unit_id ?module_id
    WHERE {
        ?unit a/rdfs:subClassOf* ?cls .
        FILTER(?cls IN (pm:ProcessUnit, <http://www.plantmind.ai/gtcc#ProcessUnit>))
        OPTIONAL { ?unit rdfs:label ?label }
        OPTIONAL { ?unit pm:unit_id ?unit_id }
        OPTIONAL { ?unit pm:module_id ?module_id }
    }
    """
    results = []
    for row in g.query(query, initNs={"pm": PM, "rdfs": RDFS}):
        results.append({
            "uri": str(row.unit),
            "label": str(row.label) if row.label else "",
            "unit_id": str(row.unit_id) if row.unit_id else "",
            "module_id": str(row.module_id) if row.module_id else "",
        })
    return results


def get_streams(g: Graph) -> list[dict]:
    """Get all MaterialStream individuals."""
    query = """
    SELECT ?stream ?label ?stream_id
    WHERE {
        ?stream a/rdfs:subClassOf* pm:MaterialStream .
        OPTIONAL { ?stream rdfs:label ?label }
        OPTIONAL { ?stream pm:stream_id ?stream_id }
    }
    """
    results = []
    for row in g.query(query, initNs={"pm": PM, "rdfs": RDFS}):
        results.append({
            "uri": str(row.stream),
            "label": str(row.label) if row.label else "",
            "stream_id": str(row.stream_id) if row.stream_id else "",
        })
    return results
