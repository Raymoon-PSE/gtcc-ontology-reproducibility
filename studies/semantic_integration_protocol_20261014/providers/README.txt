Fabricated engineering-provider requirements for a GTCC integration comparison
Authoring date: 2026-10-14

These are independently assigned agent-authored fixtures, not documents from
industrial providers, plant observations or independently validated engineering
datasets. One author agent produced both fictional providers without reading old
experiments or representation implementations. Independence refers to separation
from implementation, not to two independently sampled real-world organizations.
The fixtures define metadata and topology only. No physical operating values are
provided. Conversion constants are unit definitions, not measured data.

Use provider_a_vN.json, provider_b_vN.json and boundary_mapping_vN.json together
for N = 1, 2, 3. Each file is a complete snapshot, not a patch. Apply versions in
order. evolution_requests.json states changes and invalid-case requirements.
The native documents are declarative schemas in JSON, not JSON Schema documents.
They leave API, storage, execution and evaluator implementation to the host.

Provider A uses thermal/control equipment vocabulary for GT and HRSG interfaces.
Provider B uses steam-cycle vocabulary for steam turbine and condenser interfaces.
Equipment and type identifiers are provider-local. Each type has either one local
parent or null (root). Parent identifiers must exist; cycles are invalid. Equipment
types must exist. Transitive ancestry includes every parent up to the root.
Each endpoint is identified by (provider_id, namespace, local_port_id); all three
are required. Port directions are relative to the named equipment. Port field
sets describe required scalar engineering quantities, their local field keys
(aliases for canonical quantities), and declared units. Ports referencing the
same field set use the same declaration, not the same runtime value.

All boundary identities and producer/consumer links live ONLY in mapping files.
The seven boundaries are gt_exhaust, hp_steam, hot_reheat, lp_steam, st_exhaust,
cold_reheat and condensate. GT exhaust connects GT to HRSG within provider A;
ST exhaust connects turbine to condenser within provider B. The other five are
cross-provider links, including cold-reheat and condensate return streams.
Each canonical boundary must occur exactly once and have one out producer and
one in consumer. Every endpoint must resolve uniquely in the named version.
For this fixture each port participates in exactly one boundary. Boundary names
are matching identifiers, not additional thermodynamic assumptions.

Field mappings repeat native engineering dimensions explicitly so that adapters
have equal mapping evidence. Every native local key must have exactly one
mapping, agreeing with native quantity/unit declarations. Canonical quantities
are temperature, pressure and mass_flow; canonical public-output units are degC, MPa and kg/h.
A canonical unit needs identity conversion. Other admitted units use the exact
conversion declarations in the mapping. Conversion is from local to canonical.
Absent or contradictory field mapping evidence is invalid. No value ranges,
phase calculations, conservation tolerances or dynamic behavior are implied.

v2 changes local field aliases and units in both providers, and assigns new
subtypes with transitive ancestry to one item of equipment per provider.
v3 introduces repeated local port label inlet in distinct namespaces. Fully
qualified context is supplied in the valid mapping. Native v3 types and fields
otherwise retain v2 definitions.

Each variant_v3_* file is a full replacement for the one named file, used with
the other two VALID v3 files. Run variants independently, never cumulatively.
The conflicting mapping duplicates hp_steam with a different consumer. The
missing-parent schema gives ControlledHRSG an undefined parent. The unqualified
mapping omits one namespace where several inlet ports exist. Explicit rejection
is required; no particular exception API or message wording is prescribed.

Provide identical source documents, conversions, mapping evidence and changes
to both RDF and JSON conditions. Ancestor traversal and qualified lookup can be
implemented in either representation. Nothing requires an RDF-specific syntax
or an external ontology. These fixtures establish neither industrial generality
nor a representation advantage; claims require separately designed evaluation.
