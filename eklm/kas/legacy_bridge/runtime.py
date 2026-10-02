"""Opt-in ontology-governed execution, added for the CACE reproduction audit.

This module connects existing models; it does not fit a surge-margin law or
create validation measurements. Graph configuration and computed evidence are
kept separate. FULL is rejected unless explicit device data are complete.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict

from rdflib import Graph, Literal
from rdflib.namespace import XSD

from eklm.kas.legacy_bridge.graph import PM, load_graph
from eklm.kas.legacy_bridge.populate import populate
from eklm.kas.legacy_bridge.mech_bridge import _PROP_MAP, populate_mech
from eklm.kas.legacy_bridge.bayesian import _extract_observations, diagnose_bayesian, DESIGN_REF
from eklm.kas.legacy_bridge.diagnostics import diagnose
from eklm.vdt.mechanical.data_package import DataStatus, DeviceDataPackage
from eklm.vdt.mechanical.model_router import ModelRouter
from eklm.vdt.mechanical.reference_db import ReferenceDatabase

# Existing catalog identifiers. New devices can declare their type/unit in RDF.
_CATALOG = {
    'COMP-001': ('Compressor', '1-2'), 'EXP-001': ('GT_Turbine', '1-5'),
    'COMB-001': ('Combustor', '1-4'), 'HPSH-001': ('HRSG_Superheater', '2-1'),
    'RH-001': ('Reheater', '2-4'), 'HPTURB': ('HP_ST', '3-1'),
}


def _one(g, subject, predicate):
    values = list(g.objects(subject, predicate))
    if len(values) > 1:
        raise ValueError(f'Multiple values for {subject} {predicate}')
    return values[0] if values else None


def _parameters(g, device, predicate):
    raw = _one(g, device, predicate)
    if raw is None:
        return {}
    def reject_constant(value):
        raise ValueError('Non-standard JSON numeric constant: '+value)
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate JSON parameter: '+key)
            result[key]=value
        return result
    value = json.loads(str(raw), parse_constant=reject_constant, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError(f'{predicate} must encode a JSON object')
    return value


def packages_from_graph(g: Graph, ref_db: ReferenceDatabase):
    """Read DataStatus anew on every run, retaining the source of each parameter.

    PARTIAL uses archived reference parameters plus explicit RDF overrides.
    FULL requires explicit values for every parameter in that device's reference
    schema. Merely relabelling a PARTIAL device FULL cannot remove uncertainty.
    NONE disables the device even if historical measurements remain in the graph.
    """
    devices = sorted(set(g.subjects(PM.mech_hasDataStatus, None)), key=str)
    if not devices:
        raise ValueError('Ontology contains no mechanical DataStatus declarations')
    for device in devices:
        name = str(device).rsplit('#', 1)[-1]
        value = _one(g, device, PM.mech_hasDataStatus)
        prefix = str(PM.mech_DataStatus_)
        if not str(value).startswith(prefix):
            raise ValueError(f'Invalid DataStatus for {name}: {value}')
        try:
            declared = DataStatus(str(value)[len(prefix):])
        except ValueError as exc:
            raise ValueError(f'Unknown DataStatus for {name}: {value}') from exc
        known_type, known_unit = _CATALOG.get(name, (None, None))
        dtype = _one(g, device, PM.mech_deviceType) or known_type
        unit = _one(g, device, PM.mech_unitId) or known_unit
        if not dtype or not unit:
            raise ValueError(f'{name} needs mech_deviceType and mech_unitId')
        dtype, unit = str(dtype), str(unit)
        defaults = ref_db.get_defaults(dtype)
        supplied = _parameters(g, device, PM.mech_requiredParameters)
        optional = _parameters(g, device, PM.mech_optionalParameters)
        from eklm.kas.legacy_bridge.input_policy import resolve_parameters
        required, supplied_all = resolve_parameters(defaults, supplied, optional, declared.value)
        package = DeviceDataPackage(name, dtype, unit, required, optional)
        # Declared policy is accepted only after the data checks above.
        package.status = declared
        provenance = {
            'device_id': name, 'declared_status': declared.value,
            'reference_parameters': sorted(k for k in defaults if k not in supplied_all)
                if declared is DataStatus.PARTIAL else [],
            'explicit_parameters': sorted(supplied_all),
        }
        yield package, provenance


def run_graph_mechanical(g, operating_point, ref_db):
    router = ModelRouter(ref_db)
    results, trace = [], []
    # A rejected configuration must not leave previous mechanical evidence live.
    for prop in set(_PROP_MAP.values()):
        g.remove((None, prop, None))
    for package, provenance in packages_from_graph(g, ref_db):
        model = router.route(package)
        result = model.run(operating_point)
        from eklm.kas.legacy_bridge.input_policy import validate_outputs
        validate_outputs(result, package)
        result.uncertain_params = sorted(set(result.uncertain_params)
                                        | set(provenance['reference_parameters']))
        provenance.update(model=type(model).__name__, result_status=result.status)
        results.append(result)
        trace.append(provenance)
    # Publish only after every configured device has completed successfully.
    populate_mech(g, results)
    return results, trace


def observations_from_graph(g, process_keys):
    """Consume the current graph snapshot, not caller-supplied diagnostic values."""
    obs = {}
    for key in process_keys:
        value = _one(g, PM['RuntimeObservation_' + key], PM.runtime_value)
        if value is None:
            raise ValueError(f'Missing process observation: {key}')
        obs[key] = float(value)
    # The current fault library has one compressor evidence term. Reject ambiguity.
    prop = _PROP_MAP['mech_comp_surge_margin_pct']
    values = list(g.subject_objects(prop))
    if len(values) > 1:
        raise ValueError('Fault library needs an explicit compressor scope for multiple devices')
    if values:
        obs['mech_comp_surge_margin_pct'] = float(values[0][1])
    if not all(math.isfinite(value) for value in obs.values()):
        raise ValueError('Non-finite runtime observation')
    return obs



def trace_declared_relations(g, start):
    """Follow asserted graph connections. This is not a causal/physics solver."""
    queue, seen, edges = [start], set(), set()
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        for prop in (PM.part_of, PM.upstream_of, PM.has_outlet_stream):
            for target in g.objects(node, prop):
                edges.add((str(node), str(prop), str(target)))
                if target not in seen:
                    queue.append(target)
        for target in g.subjects(PM.has_inlet_stream, node):
            edges.add((str(target), str(PM.has_inlet_stream), str(node)))
            if target not in seen:
                queue.append(target)
    return [list(edge) for edge in sorted(edges)]

def execute_runtime(output, result, params):
    """Run graph-configured mechanics, ABox write, graph read, diagnosis and rules.

    Called by run_gtcc(..., ontology_runtime=True). Optional ontology_graph or
    ontology_dir selects configuration; mechanical_reference_dir selects sources.
    No numerical degradation coefficients are introduced by this orchestration.
    """
    g = params.get('ontology_graph')
    if g is None:
        g = load_graph(params.get('ontology_dir'))
    if not isinstance(g, Graph):
        raise TypeError('ontology_graph must be an rdflib.Graph')
    from eklm.kas.legacy_bridge.integrity import require_valid_graph, clear_runtime_evidence
    clear_runtime_evidence(g, output)
    integrity = require_valid_graph(g, params.get('engineering_contract'))
    ref_db = ReferenceDatabase(params.get('mechanical_reference_dir'))
    populate(g, result)
    mechanical, trace = run_graph_mechanical(g, result.operating_point, ref_db)
    reference = {**DESIGN_REF, **params.get("diagnostic_reference", {})}
    process = _extract_observations(result, reference)
    process['eta_comp'] = float(params.get('eta_comp', 0.845))
    process['eta_turb'] = float(params.get('eta_turb', 0.876))
    provenance = {key: 'process_result' for key in process}
    provenance.update(eta_comp='model_parameter_not_sensor', eta_turb='model_parameter_not_sensor')
    overrides = params.get('runtime_observation_overrides', {})
    allowed = {'W_GT', 'W_ST', 'W_net', 'T_stack', 'PTD_HP', 'P_cond', 'x_28'}
    if set(overrides) - allowed:
        raise ValueError('Only explicit process measurement channels may be overridden')
    for key, value in overrides.items():
        if not math.isfinite(value):
            raise ValueError('Non-finite synthetic measurement')
        process[key] = float(value)
        provenance[key] = 'synthetic_measurement_override'
    for key in ('W_GT', 'W_ST', 'W_net'):
        if reference[key] <= 0:
            raise ValueError('Reference powers must be positive')
        process[key + '_pct'] = 100 * (process[key] / reference[key] - 1)
        provenance[key + '_pct'] = 'derived_from_' + provenance[key]
    if not params.get('diagnostic_include_model_parameters', True):
        for key in ('eta_comp', 'eta_turb'):
            process.pop(key, None)
            provenance.pop(key, None)
    # Remove observations omitted in this run from a reused graph.
    for subject in list(g.subjects(PM.runtime_value, None)):
        if str(subject).startswith(str(PM.RuntimeObservation_)):
            g.remove((subject, PM.runtime_value, None))
    for key, value in process.items():
        g.set((PM['RuntimeObservation_' + key], PM.runtime_value,
               Literal(value, datatype=XSD.double)))
    obs = observations_from_graph(g, process)
    diagnoses = diagnose_bayesian(result, observations=obs, reference=reference)
    process_only = {k:v for k,v in obs.items() if not k.startswith('mech_')}
    process_diagnoses = diagnose_bayesian(result, observations=process_only, reference=reference)
    provenance.update({k:'computed_mechanical_result_via_graph' for k in obs if k.startswith('mech_')})
    findings = [{**asdict(f), 'severity':f.severity.value} for f in diagnose(result, mechanical)]
    # Rules operate on computed physical state, not synthetic sensor perturbations.
    for subject in list(set(g.subjects())):
        if str(subject).startswith(str(PM.RuntimeFinding_)):
            g.remove((subject, None, None))
    for index, finding in enumerate(findings):
        subject = PM['RuntimeFinding_' + str(index)]
        g.set((subject, PM.runtime_rule, Literal(finding['rule_id'])))
        g.set((subject, PM.runtime_severity, Literal(finding['severity'])))
        g.set((subject, PM.runtime_message, Literal(finding['message'])))
    for diagnosis in diagnoses:
        subject = PM['RuntimeDiagnosis_' + diagnosis.fault_id]
        g.set((subject, PM.runtime_posterior, Literal(diagnosis.posterior, datatype=XSD.double)))
        g.set((subject, PM.runtime_recommendation, Literal(diagnosis.recommendation)))
    residual_assessment = None  # Optional post-paper monitoring excluded from this release.
    output['mech_results'] = mechanical
    for item in mechanical:
        output.update(item.outputs)
    output['ontology_runtime'] = {
        'integrity': integrity,
        'routing': trace, 'observations': obs,
        'observation_provenance': provenance,
        'reference': reference,
        'residual_assessment': residual_assessment,
        'mechanical_evidence_independence': 'model-derived; not independent measured evidence',
        'process_only_diagnoses': [asdict(item) for item in process_diagnoses],
        'rule_findings': findings,
        'rule_scope': 'computed physical/mechanical state; synthetic observation overrides affect Bayesian arms only',
        'relation_traces': {item.device_id:trace_declared_relations(g, PM[item.device_id]) for item in mechanical},
        'execution_steps': ['process_to_graph','graph_configured_mechanics','mechanics_to_graph','observations_from_graph','paired_bayesian','physical_state_rules','declared_relation_tracing'],
        'limitations': ['Physics topology remains Python-configured', 'R-01 is an existing no-op', 'Declared relations are not proof of causality'],
        'diagnoses': [asdict(item) for item in diagnoses],
        'warnings': [warning for item in mechanical for warning in item.warnings],
        'graph_triples': len(g),
        'evidence_origin': 'current process results and graph-published mechanical outputs',
    }
    return g
