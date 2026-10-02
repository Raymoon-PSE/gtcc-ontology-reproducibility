"""Failure-wide evidence and parameter-policy regressions; no field data."""
from pathlib import Path
import sys,json,warnings,math
from unittest.mock import patch
from contextlib import nullcontext
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from rdflib import Literal
from eklm.kas.legacy_bridge.graph import load_graph,PM
from eklm.kas.legacy_bridge.mech_bridge import _PROP_MAP
from eklm.vdt.gui_adapter import run_gtcc
from eklm.kas.legacy_bridge.input_policy import resolve_parameters
from eklm.vdt.mechanical.reference_db import ReferenceDatabase
from eklm.kas.legacy_bridge.bayesian import diagnose_bayesian
warnings.filterwarnings('ignore');O=R/'outputs/transaction';O.mkdir(parents=True,exist_ok=True)
props=[PM.stream_T,PM.stream_P,PM.stream_m_dot,PM.stream_h,PM.stream_s,PM.var_value,PM.kpi_value,PM.kpi_status]
def static(g):return set(t for p in props for t in g.triples((None,p,None)))
def fresh(g):return sum(len(list(g.triples((None,p,None)))) for p in [PM.runtime_state_updated,PM.runtime_value,PM.runtime_posterior,PM.runtime_ownedPredicate,PM.runtime_unboundedOutput,PM.runtime_censoredOutput,PM.runtime_exergyDestructionPct,*set(_PROP_MAP.values())])
scenarios=['missing_status','wrong_binding','FULL_missing','duplicate_map','duplicate_json','unknown_parameter','NaN','overflow','boolean','numeric_string','bad_efficiency','bad_geometry','zero_reference','bad_observation','physical_failure','late_diagnosis_failure','nonfinite_model_output']
records=[]
for name in scenarios:
 g=load_graph();baseline=static(g)
 d,r=run_gtcc({'ontology_runtime':True,'ontology_graph':g,'cumulative_hours':10000})
 g.set((PM['GT-001'],PM.runtime_exergyDestructionPct,Literal(39.0)))
 assert fresh(g)>0
 params={'ontology_runtime':True,'ontology_graph':g,'cumulative_hours':10000}
 device='COMP-001';required=None;optional=None;context=nullcontext()
 if name=='missing_status':g.remove((PM['HPSH-001'],PM.mech_hasDataStatus,None))
 if name=='wrong_binding':g.set((PM[device],PM.mech_unitId,Literal('WRONG')))
 if name=='FULL_missing':g.set((PM[device],PM.mech_hasDataStatus,PM.mech_DataStatus_FULL))
 if name=='duplicate_map':required={'surge_margin_design_pct':10};optional={'surge_margin_design_pct':12}
 if name=='duplicate_json':required='{"surge_margin_design_pct": 10, "surge_margin_design_pct": 12}'
 if name=='unknown_parameter':required={'typo_margin':10}
 if name=='NaN':required='{"polytropic_efficiency_design": NaN}'
 if name=='overflow':required='{"polytropic_efficiency_design": 1e309}'
 if name=='boolean':required={'pressure_ratio_design':True}
 if name=='numeric_string':required={'pressure_ratio_design':'18.1'}
 if name=='bad_efficiency':required={'polytropic_efficiency_design':1.1}
 if name=='bad_geometry':device='HPSH-001';required={'tube_wall_mm':30}
 if name=='zero_reference':params['diagnostic_reference']={'W_net':0}
 if name=='bad_observation':params['runtime_observation_overrides']={'W_net':float('nan')}
 if name=='physical_failure':
  a=json.loads((R/'data/archived/results.json').read_text());params.update(next(x['params'] for x in a['failures'] if x['kind']=='mc'))
 if name=='late_diagnosis_failure':context=patch('eklm.kas.legacy_bridge.runtime.diagnose_bayesian',side_effect=RuntimeError('Injected failure after process/mechanical publication in staged graph'))
 if name=='nonfinite_model_output':
  from eklm.vdt.mechanical.compressor_model import CompressorHybridModel
  real=CompressorHybridModel.run
  def invalid(self,op):
   out=real(self,op);out.outputs['mech_comp_efficiency_current']=float('inf');return out
  context=patch.object(CompressorHybridModel,'run',invalid)
 for key,value in [('mech_requiredParameters',required),('mech_optionalParameters',optional)]:
  if value is not None:g.set((PM[device],PM[key],Literal(value if isinstance(value,str) else json.dumps(value))))
 try:
  with context:run_gtcc(params)
 except Exception as exc:
  assert fresh(g)==0,(name,'current evidence remains')
  assert static(g)==baseline,(name,'static reference changed')
  assert str(g.value(PM.RuntimeExecution,PM.runtime_executionStatus))=='failed'
  records.append({'case':name,'rejected':True,'error_type':type(exc).__name__,'error':str(exc),'current_evidence':fresh(g),'static_reference_restored':True})
 else:raise AssertionError('Accepted invalid case: '+name)
# Same meaningful change in either explicit input map, with visible provenance.
overrides=[]
for source in ['required','optional']:
 for margin in [10,20]:
  g=load_graph();g.set((PM['COMP-001'],PM['mech_'+source+'Parameters'],Literal(json.dumps({'surge_margin_design_pct':margin}))))
  d,r=run_gtcc({'ontology_runtime':True,'ontology_graph':g,'cumulative_hours':10000})
  rr=next(x for x in d['mech_results'] if x.device_id=='COMP-001');trace=next(x for x in d['ontology_runtime']['routing'] if x['device_id']=='COMP-001')
  assert rr.outputs['mech_comp_surge_margin_pct']==margin
  assert 'surge_margin_design_pct' in trace['explicit_parameters'] and 'surge_margin_design_pct' not in trace['reference_parameters']
  overrides.append({'source':source,'margin_input':margin,'margin_output':rr.outputs['mech_comp_surge_margin_pct'],'provenance_correct':True})
# Known zero-rate model sentinel is explicit and never published as a numeric INF.
g=load_graph();g.set((PM['COMP-001'],PM.mech_requiredParameters,Literal('{"k_degradation_per_khr": 0}')))
d,r=run_gtcc({'ontology_runtime':True,'ontology_graph':g,'cumulative_hours':10000})
rr=next(x for x in d['mech_results'] if x.device_id=='COMP-001')
assert rr.outputs['mech_comp_remaining_life_hr']==math.inf
assert not list(g.objects(PM['COMP-001'],PM.mech_remainingLifeHr))
assert Literal('mech_comp_remaining_life_hr') in g.objects(PM['COMP-001'],PM.runtime_unboundedOutput)
# Reference-schema resolver is representation-neutral; independent expected outcomes.
defaults=ReferenceDatabase().get_defaults('Compressor')
plain=[]
for value,expected in [(10,True),(20,True),(float('nan'),False),(float('inf'),False),(True,False),('10',False),(-1,False)]:
 try:
  resolved,supplied=resolve_parameters(defaults,{}, {'surge_margin_design_pct':value},'PARTIAL');accepted=True
 except ValueError:accepted=False
 assert accepted==expected
 plain.append({'value':str(value),'expected':expected,'accepted':accepted})
summary={'failed_runs':len(records),'all_failures_clear_evidence_and_restore_static':True,'nondefault_overrides':len(overrides),'all_override_values_and_provenance_correct':True,'unbounded_lifetime_sentinel_labelled':True,'plain_input_policy_checks':len(plain),'scope':'Development regression, single-writer graph; two failures are deliberately injected to test late publication boundaries.'}
(O/'results.json').write_text(json.dumps({'summary':summary,'failures':records,'overrides':overrides,'plain_input_checks':plain},indent=2,allow_nan=False))
print(json.dumps(summary,indent=2))
