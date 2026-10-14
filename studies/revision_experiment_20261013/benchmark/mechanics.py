"""Matched mechanics backends. RDF export is preparation, never JSON execution.

JSON uses centralized policy and the same numerical/diagnostic kernels. This
isolates representation; it does not deliberately handicap the conventional arm.
"""
from copy import deepcopy
from dataclasses import asdict
import math


def export_json_config(graph, contract=None):
    """One-time equivalent plain configuration, including resolved class closure."""
    from eklm.kas.legacy_bridge.runtime import packages_from_graph
    from eklm.kas.legacy_bridge.integrity import graph_records, default_contract
    from eklm.vdt.mechanical.reference_db import ReferenceDatabase
    from eklm.kas.legacy_bridge.graph import PM
    import json
    devices = []
    # Package parsing here guarantees equivalent catalog/type defaults; original
    # supplied values/status remain explicit so JSON rechecks them at runtime.
    for package, provenance in packages_from_graph(graph, ReferenceDatabase()):
        subject = PM[package.device_id]
        devices.append(dict(device_id=package.device_id, device_type=package.device_type,
            unit_id=package.unit_id, status=package.status.value,
            supplied=json.loads(str(graph.value(subject, PM.mech_requiredParameters) or '{}')),
            optional=json.loads(str(graph.value(subject, PM.mech_optionalParameters) or '{}'))))
    relations = [[str(s),str(p),str(o)] for s,p,o in graph
                 if str(p) in {str(PM[x]) for x in ('part_of','upstream_of','has_outlet_stream','has_inlet_stream')}]
    return dict(devices=devices, records=graph_records(graph,contract),
                contract=deepcopy(contract or default_contract()), relations=sorted(relations),
                namespace=str(PM))


def _trace(config, start):
    ns=config['namespace']; queue=[ns+start];seen=set();edges=set()
    forward={ns+x for x in ('part_of','upstream_of','has_outlet_stream')}
    adjacency={}
    for s,p,o in config['relations']:
        if p in forward: adjacency.setdefault(s,[]).append((o,(s,p,o)))
        elif p==ns+'has_inlet_stream': adjacency.setdefault(o,[]).append((s,(s,p,o)))
    while queue:
        node=queue.pop()
        if node in seen: continue
        seen.add(node)
        for target,edge in adjacency.get(node,[]):
            edges.add(edge)
            if target not in seen:queue.append(target)
    return [list(x) for x in sorted(edges)]


def _normalize(mechanical, audit, params, model_versions):
    aliases=params.get('output_aliases',{})
    rows=[]
    for item in mechanical:
        row=asdict(item);row['outputs']={aliases.get(k,k):v for k,v in row['outputs'].items()}
        row['uncertain_params']=sorted(row['uncertain_params']);rows.append(row)
    return dict(mechanics=sorted(rows,key=lambda x:x['device_id']),
        observations=audit['observations'], diagnoses=audit['diagnoses'],
        process_only_diagnoses=audit['process_only_diagnoses'],
        rule_findings=audit['rule_findings'], routing=audit['routing'],
        provenance={k:('computed_mechanical_result' if v=='computed_mechanical_result_via_graph' else v)
                    for k,v in audit['observation_provenance'].items()},
        relation_traces=audit['relation_traces'], warnings=audit['warnings'],
        model_versions=dict(model_versions or {}))


def _run_mechanics(result, params, backend='rdf', model_versions=None):
    """Return representation-neutral evidence. Caller owns fresh config/snapshot.

    model_versions selects common same-kernel adapters; output_aliases is an
    export-schema hook. Neither is ontology inference or new numerical physics.
    Advanced residual/temporal monitors are outside this matched benchmark.
    """
    if any(params.get(k) is not None for k in ('residual_monitor_model','temporal_monitor_model')):
        raise ValueError('Residual/temporal monitors outside matched mechanics scope')
    if backend=='rdf':
        from eklm.kas.legacy_bridge.runtime import execute_runtime
        out={};execute_runtime(out,result,params)
        return _normalize(out['mech_results'],out['ontology_runtime'],params,model_versions)
    if backend!='json':raise ValueError('backend must be rdf or json')
    from eklm.kas.legacy_bridge.integrity import validate_records, IntegrityError
    from eklm.vdt.mechanical.reference_db import ReferenceDatabase
    from eklm.vdt.mechanical.model_router import ModelRouter
    from eklm.vdt.mechanical.data_package import DeviceDataPackage, DataStatus
    from eklm.kas.legacy_bridge.bayesian import DESIGN_REF, _extract_observations, diagnose_bayesian
    from eklm.kas.legacy_bridge.diagnostics import diagnose
    config=params['json_config']; contract=params.get('engineering_contract',config['contract'])
    findings=validate_records(config['records'],contract)
    if findings:raise IntegrityError(findings)
    db=ReferenceDatabase(params.get('mechanical_reference_dir')); router=ModelRouter(db)
    mechanical=[];trace=[]
    for record in sorted(config['devices'],key=lambda x:x['device_id']):
        declared=DataStatus(record['status']);supplied=record['supplied'];defaults=db.get_defaults(record['device_type'])
        if declared is DataStatus.NONE:required={}
        elif not defaults:raise ValueError('No reference parameter schema')
        elif declared is DataStatus.FULL:
            if any(supplied.get(k) is None for k in defaults):raise ValueError('FULL lacks explicit data')
            required=dict(supplied)
        else:
            required={**defaults,**supplied}
            if any(v is None for v in required.values()):raise ValueError('null required data')
        package=DeviceDataPackage(record['device_id'],record['device_type'],record['unit_id'],required,dict(record['optional']))
        package.status=declared;model=router.route(package);item=model.run(result.operating_point)
        refs=sorted(k for k in defaults if k not in supplied) if declared is DataStatus.PARTIAL else []
        item.uncertain_params=sorted(set(item.uncertain_params)|set(refs));mechanical.append(item)
        trace.append(dict(device_id=record['device_id'],declared_status=declared.value,
            reference_parameters=refs,explicit_parameters=sorted(supplied),model=type(model).__name__,result_status=item.status))
    reference={**DESIGN_REF,**params.get('diagnostic_reference',{})}
    obs=_extract_observations(result,reference)
    obs.update(eta_comp=float(params.get('eta_comp',.845)),eta_turb=float(params.get('eta_turb',.876)))
    provenance={k:'process_result' for k in obs};provenance.update(eta_comp='model_parameter_not_sensor',eta_turb='model_parameter_not_sensor')
    overrides=params.get('runtime_observation_overrides',{})
    if set(overrides)-{'W_GT','W_ST','W_net','T_stack','PTD_HP','P_cond','x_28'}:raise ValueError('Only explicit process measurement channels')
    for k,v in overrides.items():
        if not math.isfinite(v):raise ValueError('Non-finite synthetic measurement')
        obs[k]=float(v);provenance[k]='synthetic_measurement_override'
    for k in ('W_GT','W_ST','W_net'):
        if reference[k]<=0:raise ValueError('Reference powers must be positive')
        obs[k+'_pct']=100*(obs[k]/reference[k]-1);provenance[k+'_pct']='derived_from_'+provenance[k]
    if not params.get('diagnostic_include_model_parameters',True):
        for k in ('eta_comp','eta_turb'):obs.pop(k,None);provenance.pop(k,None)
    # Equivalent publication precision: RDF populate_mech rounds to six decimals.
    surge=[round(m.outputs['mech_comp_surge_margin_pct'],6) for m in mechanical
           if m.status!='INACTIVE' and 'mech_comp_surge_margin_pct' in m.outputs and m.outputs['mech_comp_surge_margin_pct']!=-1]
    if len(surge)>1:raise ValueError('Fault library needs explicit compressor scope')
    if surge:obs['mech_comp_surge_margin_pct']=surge[0];provenance['mech_comp_surge_margin_pct']='computed_mechanical_result'
    if not all(math.isfinite(v) for v in obs.values()):raise ValueError('Non-finite runtime observation')
    findings=[{**asdict(f),'severity':f.severity.value} for f in diagnose(result,mechanical)]
    audit=dict(observations=obs,observation_provenance=provenance,
        diagnoses=[asdict(x) for x in diagnose_bayesian(result,observations=obs,reference=reference)],
        process_only_diagnoses=[asdict(x) for x in diagnose_bayesian(result,observations={k:v for k,v in obs.items() if not k.startswith('mech_')},reference=reference)],
        routing=trace,rule_findings=findings,
        relation_traces={m.device_id:_trace(config,m.device_id) for m in mechanical},
        warnings=[w for m in mechanical for w in m.warnings])
    return _normalize(mechanical,audit,params,model_versions)


def run_mechanics(result, params, backend='rdf', model_versions=None):
    """Apply actual common versioned execution adapters, restored after each run.

    Version adapters delegate unchanged kernels. They exercise replacement wiring,
    not a claim of a newer or more accurate physical model. Serial benchmark only.
    """
    from eklm.vdt.mechanical.model_router import ModelRouter
    versions=dict(model_versions or {})
    original=ModelRouter.route
    class VersionedModelAdapter:
        def __init__(self, inner, version):self.inner=inner;self.version=version
        def run(self, operating_point):return self.inner.run(operating_point)
    def route(router, package):
        model=original(router,package)
        return VersionedModelAdapter(model,versions[package.device_id]) if package.device_id in versions else model
    if versions:ModelRouter.route=route
    try:return _run_mechanics(result,params,backend,versions)
    finally:ModelRouter.route=original


def make_default_params():
    """Prepare independent RDF/JSON configurations before benchmark timing."""
    from eklm.kas.legacy_bridge.graph import load_graph
    graph=load_graph()
    return {'ontology_graph':graph,'json_config':export_json_config(graph)}
