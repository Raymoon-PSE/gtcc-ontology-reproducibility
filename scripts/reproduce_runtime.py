"""Exercise the paper's governed calculation chain and DataStatus routing."""
from pathlib import Path
import sys,json
from dataclasses import asdict
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rdflib import Literal
from eklm.kas.legacy_bridge.graph import load_graph,PM
from eklm.vdt.gui_adapter import run_gtcc
from eklm.vdt.mechanical.reference_db import ReferenceDatabase
from eklm.kas.legacy_bridge.runtime import run_graph_mechanical
out=ROOT/'outputs/runtime';out.mkdir(parents=True,exist_ok=True);records=[]
for name,eta,status in [('baseline',.845,'PARTIAL'),('efficiency_degraded',.815,'PARTIAL'),('compressor_disabled',.815,'NONE')]:
 g=load_graph();g.set((PM['COMP-001'],PM.mech_hasDataStatus,PM['mech_DataStatus_'+status]))
 d,r=run_gtcc({'eta_comp':eta,'cumulative_hours':10000,'start_stop_count':200,'ontology_runtime':True,'ontology_graph':g})
 audit=d['ontology_runtime'];sm=audit['observations'].get('mech_comp_surge_margin_pct')
 assert sm==(None if status=='NONE' else 15.0)
 assert not any(f['rule_id']=='R-09' for f in audit['rule_findings'])
 records.append({'case':name,'net_power_kW':d['W_net'],'audit':audit,'mechanical':[asdict(x) for x in d['mech_results']]})
 g.serialize(out/(name+'.ttl'),format='turtle')
# Explicit FULL parameters distinguish complete data from a label-only change.
ref=ReferenceDatabase();g=load_graph();g.set((PM['HPSH-001'],PM.mech_hasDataStatus,PM.mech_DataStatus_FULL))
try:run_graph_mechanical(g,r.operating_point,ref)
except ValueError:pass
else:raise AssertionError('FULL without explicit parameters must fail')
g.set((PM['HPSH-001'],PM.mech_requiredParameters,Literal(json.dumps(ref.get_defaults('HRSG_Superheater')))))
results,trace=run_graph_mechanical(g,r.operating_point,ref)
assert next(x for x in trace if x['device_id']=='HPSH-001')['declared_status']=='FULL'
(out/'results.json').write_text(json.dumps({'cases':records,'full_requires_explicit_parameters':True},indent=2))
print('Three governed runs, margin/rule checks, and explicit FULL validation passed.')
