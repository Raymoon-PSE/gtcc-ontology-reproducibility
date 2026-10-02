"""New EKLM simulation evaluation, distinct from the unrecovered historical 55 cases.

Run from any directory. Inputs, reference, both arms, queries and failures are saved.
Physical kernels are unchanged; diagnostic threshold equality is explicit.
"""
from pathlib import Path
import sys, json, warnings, math, hashlib
from copy import deepcopy
from dataclasses import asdict
from collections import Counter
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rdflib import Literal
from eklm.vdt.gui_adapter import run_gtcc
from eklm.kas.legacy_bridge.graph import load_graph, PM
from eklm.kas.legacy_bridge.bayesian import diagnose_bayesian, _extract_observations, LEGACY_DESIGN_REF
from eklm.kas.legacy_bridge.runtime import _CATALOG
from eklm.kas.legacy_bridge.mech_bridge import _PROP_MAP
from eklm.vdt.mechanical.reference_db import ReferenceDatabase
from eklm.vdt.mechanical.data_package import DataStatus, DeviceDataPackage
from eklm.vdt.mechanical.model_router import ModelRouter
warnings.filterwarnings('ignore')
OUT = ROOT/'outputs/revision'; OUT.mkdir(parents=True, exist_ok=True)
def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, allow_nan=False))
base_params = dict(eta_comp=.845, eta_turb=.876, cumulative_hours=10000, start_stop_count=200)
d0, r0 = run_gtcc(base_params)
reference = {k:v for k,v in _extract_observations(r0).items() if not k.endswith('_pct')}
reference['mech_comp_surge_margin_pct'] = 15.0
save('diagnostic_reference.json', reference)
protocol = {
 'identity':'CII revision evaluation 2026-10-02; newly constructed, not the historical 55-case experiment',
 'reference':'One fixed nominal EKLM run; no re-baselining of perturbed cases; NETL comparison remains separate',
 'scope':'Simulation implementation consistency and configuration governance, not independent physical validation',
 'operating_points':[.845,.815],
 'devices':list(_CATALOG),
 'modes':['PARTIAL','FULL','NONE','PARTIAL_explicit','FULL_missing','PARTIAL_null'],
 'expected':'48 valid and 24 invalid combinations; paired arms share kernels and routing classes, but decode RDF and JSON separately',
 'control':'Plain JSON uses explicit resolved device types and unit IDs, no graph reads during evaluation',
 'tolerance':{'rel':1e-9,'abs':1e-6},
 'limitations':['Development evaluation, not blinded holdout','No human editing-time or field-accuracy claims']}
save('protocol.json',protocol)
def scores(r, eta, sm=None, ref=reference):
    p={'eta_comp':eta,'eta_turb':.876}
    if sm is not None:p['mech_comp_surge_margin_pct']=sm
    return {x.fault_id:x.posterior for x in diagnose_bayesian(r,params=p,reference=ref)}
scenarios=[]
for eta in [.845,.835,.825,.815,.805,.795]:
    d,r=run_gtcc({**base_params,'eta_comp':eta})
    sm=max(15-130*(.845-eta),5)
    scenarios.append({'eta':eta,'assumed_margin':sm,'W_net':d['W_net'],
      'process_only':scores(r,eta),'design_margin':scores(r,eta,15),
      'assumed_margin_scores':scores(r,eta,sm),'margin_10':scores(r,eta,10),
      'legacy_process_only':scores(r,eta,ref=LEGACY_DESIGN_REF)})
dh,rh=run_gtcc({**base_params,'PTD_HP':5.0})
save('diagnostics.json',{'reference':reference,'legacy_reference':LEGACY_DESIGN_REF,
 'scenarios':scenarios,'hrsg':{'PTD_observed':rh.m2.unit_22.PTD,'scores':scores(rh,.845)},
 'interpretation':'Bayesian-style normalized hypothesis scores; geometric-mean symptom weights are not calibrated joint likelihoods'})
refdb=ReferenceDatabase()
def plain_records():
    return {n:{'type':t,'unit':u,'status':'PARTIAL','required':{},'optional':{}}
            for n,(t,u) in _CATALOG.items()}
def plain_run(records, op):
    result=[];trace=[];router=ModelRouter(refdb)
    for name,x in sorted(records.items()):
        status=DataStatus(x['status']); defaults=refdb.get_defaults(x['type']); supplied=x['required']
        if status is DataStatus.NONE: required={}
        elif status is DataStatus.FULL:
            if any(supplied.get(k) is None for k in defaults):raise ValueError('Incomplete FULL input')
            required=supplied
        else:
            required={**defaults,**supplied}
            if any(v is None for v in required.values()):raise ValueError('Null PARTIAL input')
        package=DeviceDataPackage(name,x['type'],x['unit'],required,x['optional'])
        package.status=status
        model=router.route(package); rr=model.run(op)
        fallback=sorted(k for k in defaults if k not in supplied) if status is DataStatus.PARTIAL else []
        rr.uncertain_params=sorted(set(rr.uncertain_params)|set(fallback))
        result.append(rr)
        trace.append({'device_id':name,'declared_status':status.value,'reference_parameters':fallback,
          'explicit_parameters':sorted(supplied),'model':type(model).__name__,'result_status':rr.status})
    obs=_extract_observations(op_result,reference)
    obs['eta_comp']=eta
    for rr in result:
        if 'mech_comp_surge_margin_pct' in rr.outputs:
            obs['mech_comp_surge_margin_pct']=rr.outputs['mech_comp_surge_margin_pct']
    sc={x.fault_id:x.posterior for x in diagnose_bayesian(op_result,observations=obs,reference=reference)}
    return [asdict(x) for x in result],trace,sc
cases=[]
for eta in protocol['operating_points']:
    _,op_result=run_gtcc({**base_params,'eta_comp':eta})
    for device in protocol['devices']:
        for mode in protocol['modes']:
            name=f'{eta}_{device}_{mode}';g=load_graph();plain=plain_records()
            status=mode.split('_')[0]; supplied={};defaults=refdb.get_defaults(plain[device]['type'])
            if mode=='FULL':supplied=defaults.copy()
            if mode=='PARTIAL_explicit':
                key=sorted(defaults)[0];supplied={key:defaults[key]}
            if mode=='PARTIAL_null':supplied={sorted(defaults)[0]:None}
            plain[device].update(status=status,required=supplied)
            g.set((PM[device],PM.mech_hasDataStatus,PM['mech_DataStatus_'+status]))
            if supplied:g.set((PM[device],PM.mech_requiredParameters,Literal(json.dumps(supplied))))
            folder=OUT/'cases'/name;folder.mkdir(parents=True,exist_ok=True)
            g.serialize(folder/'input.ttl',format='turtle')
            (folder/'input.json').write_text(json.dumps(plain,indent=2))
            record={'name':name,'device':device,'mode':mode,'eta':eta,'expected_valid':mode not in ['FULL_missing','PARTIAL_null']}
            try:
                out,rr=run_gtcc({**base_params,'eta_comp':eta,'ontology_runtime':True,'ontology_graph':g,'diagnostic_reference':reference})
                record['rdf']={'valid':True,'mechanical':[asdict(x) for x in out['mech_results']],
                  'trace':out['ontology_runtime']['routing'],
                  'scores':{x['fault_id']:x['posterior'] for x in out['ontology_runtime']['diagnoses']},'W_net':out['W_net']}
            except ValueError as e:record['rdf']={'valid':False,'error':str(e)}
            try:
                mech,trace,sc=plain_run(plain,op_result.operating_point)
                record['json']={'valid':True,'mechanical':mech,'trace':trace,'scores':sc,'W_net':op_result.W_net}
            except ValueError as e:record['json']={'valid':False,'error':str(e)}
            assert record['rdf']['valid']==record['json']['valid']==record['expected_valid'],name
            if record['expected_valid']:
                assert record['rdf']['mechanical']==record['json']['mechanical'],name
                assert record['rdf']['trace']==record['json']['trace'],name
                for k,v in record['rdf']['scores'].items():assert math.isclose(v,record['json']['scores'][k],rel_tol=1e-9,abs_tol=1e-6),name
                assert math.isclose(record['rdf']['W_net'],record['json']['W_net'],rel_tol=1e-9),name
            cases.append(record)
            (folder/'result.json').write_text(json.dumps(record,indent=2))
    print('Paired cases complete:',eta,flush=True)
save('paired_cases.json',cases)
# Reuse the same populated graph, not a fresh graph, for every lifecycle test.
lifecycle=[]
for device in _CATALOG:
    g=load_graph()
    for state in ['PARTIAL','NONE','PARTIAL','INVALID']:
        if state=='INVALID':g.set((PM[device],PM.mech_unitId,Literal('WRONG')))
        else:g.set((PM[device],PM.mech_hasDataStatus,PM['mech_DataStatus_'+state]))
        try:
            d,r=run_gtcc({**base_params,'ontology_runtime':True,'ontology_graph':g,'diagnostic_reference':reference})
            assert state!='INVALID'
            rr=next(x for x in d['mech_results'] if x.device_id==device)
            vals=[(str(p),str(o)) for p in set(_PROP_MAP.values()) for o in g.objects(PM[device],p)]
            assert bool(vals)==(state!='NONE')
            if device=='COMP-001':assert ('mech_comp_surge_margin_pct' in d['ontology_runtime']['observations'])==(state!='NONE')
            lifecycle.append({'device':device,'state':state,'status':rr.status,'stored_mechanical_values':len(vals),'passed':True})
        except ValueError:
            assert state=='INVALID'
            assert not any(list(g.triples((None,p,None))) for p in set(_PROP_MAP.values()))
            assert not list(g.triples((None,PM.runtime_posterior,None)))
            assert not list(g.triples((None,PM.runtime_value,None)))
            lifecycle.append({'device':device,'state':state,'passed':True,'evidence_cleared':True})
save('lifecycle.json',lifecycle)
g=load_graph();db,rb=run_gtcc({**base_params,'ontology_runtime':True,'ontology_graph':g,'diagnostic_reference':reference})
# Module exergy is a computed result annotation, not a fault-causation inference.
for entry in db['exergy_destruction']:
    module_id=entry['unit'].split('(')[1].split(')')[0]
    for subject in set(g.subjects(PM.module_id,Literal(module_id))):
        # Annotate the module object, not every equipment object carrying module_id.
        if any(g.subjects(PM.part_of,subject)):
            g.set((subject,PM.runtime_exergyDestructionPct,Literal(entry['Ed_pct'])))
queries={
 'Q1':'''SELECT ?device ?life WHERE { ?device pm:mech_hasPriority pm:mech_Priority_P1 ; pm:mech_combinedLifeFraction ?life . FILTER (?life > 0.5) } ORDER BY ?device''',
 'Q2':'''SELECT ?device ?status WHERE { ?device pm:mech_hasDataStatus ?status . } ORDER BY ?device''',
 'Q3':'''SELECT ?compressor ?turbine ?surge ?creep WHERE { VALUES ?compressor { pm:COMP-001 } VALUES ?turbine { pm:EXP-001 } ?compressor pm:part_of ?module ; pm:mech_surgeMarginPct ?surge . ?turbine pm:part_of ?module ; pm:mech_creepLifeFraction ?creep . }''',
 'Q4':'''SELECT ?observation ?value WHERE { ?observation pm:runtime_value ?value . } ORDER BY ?observation''',
 'Q5':'''SELECT ?unit ?rationale WHERE { ?unit pm:mech_hasDataStatus ?status ; pm:justified_by ?rationale . } ORDER BY ?unit ?rationale''',
 'Q6':'''SELECT DISTINCT ?module ?destructionPct ?device ?fault WHERE { ?module pm:runtime_exergyDestructionPct ?destructionPct . ?device pm:part_of ?module . OPTIONAL { ?device pm:has_fault ?fault . } } ORDER BY ?module ?device ?fault'''}
query_results={}
for name,body in queries.items():
    query='PREFIX pm: <http://plantmind.io/ontology/gtcc#>\n'+body
    (OUT/(name+'.rq')).write_text(query+'\n')
    rows=[{str(k):str(v) for k,v in row.asdict().items()} for row in g.query(query)]
    assert rows,name
    query_results[name]=rows
assert query_results['Q1']==[{'device':str(PM['COMB-001']),'life':'0.625'}]
assert len(query_results['Q2'])==6
save('queries.json',query_results);g.serialize(OUT/'query_graph.ttl',format='turtle')
# Turtle's compact float formatting can lose digits. N-Triples is authoritative
# for exact archived query replay; verify every binding after serialization.
g.serialize(OUT/'query_graph.nt',format='nt')
from rdflib import Graph
restored=Graph().parse(OUT/'query_graph.nt',format='nt')
for name in queries:
    replay=[{str(k):str(v) for k,v in row.asdict().items()} for row in restored.query((OUT/(name+'.rq')).read_text())]
    assert replay==query_results[name],name
archive=json.loads((ROOT/'data/archived/results.json').read_text())
failed=[x for x in archive['failures'] if x['kind']=='mc']
save('mc_failures.json',{'n':len(failed),'records':failed,'error_counts':dict(Counter(x.get('error','unspecified') for x in failed))})
summary={'paired_cases':len(cases),'valid':sum(x['expected_valid'] for x in cases),'invalid':sum(not x['expected_valid'] for x in cases),
 'all_paired_checks_passed':True,'lifecycle_checks':len(lifecycle),'all_lifecycle_checks_passed':True,
 'query_rows':{k:len(v) for k,v in query_results.items()},'reference_net_kW':reference['W_net'],
 'legacy_nominal_net_deviation_pct':100*(r0.W_net/LEGACY_DESIGN_REF['W_net']-1),
 'revised_nominal_net_deviation_pct':0.0,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
save('summary.json',summary);print(json.dumps(summary,indent=2))
