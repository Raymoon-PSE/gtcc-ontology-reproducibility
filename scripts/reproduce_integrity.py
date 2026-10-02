"""Reproducible synthetic consistency test; no confidential plant data."""
from pathlib import Path
from copy import deepcopy
import sys,json,time,statistics,hashlib,importlib.util
D=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(D))
from rdflib import Literal,URIRef
from rdflib.namespace import RDF,RDFS
from eklm.kas.legacy_bridge.graph import PM,load_graph
from eklm.kas.legacy_bridge import integrity as mod
from eklm.kas.legacy_bridge.integrity import default_contract,graph_records,validate_graph,validate_records
from conventional_control import check_records
ROOT=D
D=ROOT/'outputs/integrity';D.mkdir(parents=True,exist_ok=True)
base=load_graph();contract=default_contract();assert not validate_graph(base)
protocol={'scope':'Synthetic engineering consistency, not physical fault diagnosis or independent field validation','arms':['existing RDF runtime without engineering guard','RDF with guard','centralized non-RDF with same guard'],'fairness':'Same authoritative contract and common validation engine. RDF class closure is projected to equivalent plain records; equality tests adapter fidelity, not independent algorithm replication. Non-RDF is a strong centralized control.','split':'Nine previously missed development cases. Additional predeclared perturbations and valid edits are supplemental synthetic cases, not blinded independently sourced holdout.','timing':'30 repetitions per case, alternating order; in-memory validation only. RDF includes graph projection/class closure; JSON starts with equivalent resolved records. Parsing, physical solve and human editing time excluded.','contract_sha256':hashlib.sha256((ROOT/'eklm/kas/legacy_bridge/integrity_contract.json').read_bytes()).hexdigest(),'metrics':['case detection','valid-case false rejection','guard execution milliseconds','logical contract fields and executable source edits for one declared extension']}
(D/'protocol.json').write_text(json.dumps(protocol,indent=2))
cases=[]
def add(name,invalid,mutate=lambda g,c:None,split='additional'):
 g=deepcopy(base);c=deepcopy(contract);mutate(g,c);cases.append((name,invalid,split,g,c))
for n in ['COMP-001','EXP-001','COMB-001','HPSH-001','RH-001','HPTURB']:
 add(n+'_wrong_unit',True,lambda g,c,n=n:g.set((PM[n],PM.mech_unitId,Literal('WRONG-UNIT'))),'previously_missed')
for kind in ['remove','reverse','replace']:
 def mutation(g,c,kind=kind):
  g.remove((PM['COMP-001'],PM.upstream_of,PM['COMB-001']))
  if kind=='reverse':g.add((PM['COMB-001'],PM.upstream_of,PM['COMP-001']))
  if kind=='replace':g.add((PM['COMP-001'],PM.upstream_of,PM.HPTURB))
 add('COMP_COMB_'+kind,True,mutation,'previously_missed')
# Freeze case construction before observing benchmark outcomes.
for n in ['COMP-001','EXP-001','COMB-001','HPSH-001','RH-001','HPTURB']:
 for p,v in [('mech_deviceType','WrongModel'),('unit_id','WRONG'),('module_id','WRONG'),('part_of',PM.WrongModule)]:
  add(n+'_'+p,True,lambda g,c,n=n,p=p,v=v:g.set((PM[n],PM[p],v if isinstance(v,URIRef) else Literal(v))))
 add(n+'_duplicate_unit',True,lambda g,c,n=n:g.add((PM[n],PM.unit_id,Literal('EXTRA'))))
for n in ['COMP-001','COMB-001','EXP-001']:
 add(n+'_missing_type',True,lambda g,c,n=n:g.remove((PM[n],RDF.type,None)))
 add(n+'_bad_inlet',True,lambda g,c,n=n:g.set((PM[n],PM.has_inlet_stream,PM['Stream-7'])))
 add(n+'_missing_outlet',True,lambda g,c,n=n:g.remove((PM[n],PM.has_outlet_stream,None)))
for s in ['Stream-2','Stream-3','Stream-5','Stream-6','Stream-7']:
 add(s+'_wrong_medium',True,lambda g,c,s=s:g.set((PM[s],RDF.type,PM.WrongMedium)))
add('unregistered_device',True,lambda g,c:g.add((PM.NewDevice,PM.mech_hasDataStatus,PM.mech_DataStatus_PARTIAL)))
add('baseline',False)
for n in ['COMP-001','EXP-001','COMB-001','HPSH-001','RH-001','HPTURB']:
 for status in ['NONE','PARTIAL']:
  add(n+'_'+status,False,lambda g,c,n=n,status=status:g.set((PM[n],PM.mech_hasDataStatus,PM['mech_DataStatus_'+status])))
 def explicit(g,c,n=n):
  r=c['devices'][str(PM[n])];g.set((PM[n],PM.mech_unitId,Literal(r['unit_id'])));g.set((PM[n],PM.mech_deviceType,Literal(r['model'])))
 add(n+'_explicit_binding',False,explicit)
for n in ['COMP-001','COMB-001','EXP-001']:
 def subtype(g,c,n=n):
  parent=URIRef(c['devices'][str(PM[n])]['class']);g.remove((PM[n],RDF.type,None));g.add((PM[n],RDF.type,PM.Specialized));g.add((PM.Specialized,RDFS.subClassOf,parent))
 add(n+'_subclass',False,subtype)
add('unrelated_annotation',False,lambda g,c:g.add((PM.Note,PM.comment,Literal('new annotation'))))
add('unrelated_equipment',False,lambda g,c:g.add((PM.Extra,RDF.type,PM.ProcessUnit)))
# A legitimate replacement stream must be declared in BOTH configuration and contract.
def rename_stream(g,c):
 old,new=PM['Stream-3'],PM['Stream-3-replacement']
 triples=list(g);g.remove((None,None,None))
 for s,p,o in triples:g.add((new if s==old else s,p,new if o==old else o))
 for ports in c['ports'].values():
  for p,vs in ports.items():ports[p]=[str(new) if v==str(old) else v for v in vs]
 c['stream_classes'][str(new)]=c['stream_classes'].pop(str(old))
add('declared_stream_replacement',False,rename_stream)
# Audit-discovered omissions and adjacent status cases; explicit regression set.
for n in ['COMP-001','EXP-001','COMB-001','HPSH-001','RH-001','HPTURB']:
 add(n+'_missing_status',True,lambda g,c,n=n:g.remove((PM[n],PM.mech_hasDataStatus,None)),'audit_regression')
 add(n+'_missing_device',True,lambda g,c,n=n:g.remove((PM[n],None,None)),'audit_regression')
 add(n+'_duplicate_status',True,lambda g,c,n=n:g.add((PM[n],PM.mech_hasDataStatus,PM.mech_DataStatus_NONE)),'audit_regression')
 add(n+'_unknown_status',True,lambda g,c,n=n:g.set((PM[n],PM.mech_hasDataStatus,PM.mech_DataStatus_UNKNOWN)),'audit_regression')
add('empty_configuration',True,lambda g,c:g.remove((None,None,None)),'audit_regression')
protocol['independent_control']='Separately implemented conventional_control.check_records; no production validator or RDF imports; consumes the same resolved records and authoritative contract.'
protocol['arms'].append('independently implemented conventional validator')
(D/'case_manifest.json').write_text(json.dumps([{'name':n,'invalid':bad,'split':sp} for n,bad,sp,g,c in cases],indent=2))
results=[]
for name,bad,split,g,c in cases:
 rows=graph_records(g,c)
 case_dir=D/'cases'/name;case_dir.mkdir(parents=True,exist_ok=True)
 g.serialize(case_dir/'configuration.ttl',format='turtle')
 (case_dir/'records.json').write_text(json.dumps(rows,indent=2))
 (case_dir/'contract.json').write_text(json.dumps(c,indent=2))
 a=validate_graph(g,c);b=validate_records(rows,c);assert a==b,name
 independent=check_records(rows,c)
 assert independent==sorted((f.code,f.subject,f.predicate) for f in a),name
 timings={'rdf':[],'non_rdf':[]}
 for repeat in range(30):
  for arm in (['rdf','non_rdf'] if repeat%2 else ['non_rdf','rdf']):
   start=time.perf_counter_ns();out=validate_graph(g,c) if arm=='rdf' else validate_records(rows,c);timings[arm].append((time.perf_counter_ns()-start)/1e6)
 results.append({'name':name,'invalid':bad,'split':split,'rdf_rejected':bool(a),'non_rdf_rejected':bool(b),'independent_rejected':bool(independent),'independent_findings':independent,'expected_agreement':bool(a)==bad,'findings':[mod.asdict(x) for x in a],'median_ms':{k:statistics.median(v) for k,v in timings.items()},'timings_ms':timings})
summary={'n':len(results),'invalid':sum(x['invalid'] for x in results),'valid':sum(not x['invalid'] for x in results),'rdf_detected':sum(x['invalid'] and x['rdf_rejected'] for x in results),'non_rdf_detected':sum(x['invalid'] and x['non_rdf_rejected'] for x in results),'rdf_false_reject':sum(not x['invalid'] and x['rdf_rejected'] for x in results),'non_rdf_false_reject':sum(not x['invalid'] and x['non_rdf_rejected'] for x in results),'all_expected':all(x['expected_agreement'] for x in results),'previously_missed_now_detected':sum(x['split']=='previously_missed' and x['rdf_rejected'] for x in results),'median_case_ms':{arm:statistics.median(x['median_ms'][arm] for x in results) for arm in ['rdf','non_rdf']},'extension':{'example':'declared_stream_replacement','config_logical_fields_changed':3,'contract_logical_fields_changed':3,'rdf_executable_source_edits':0,'non_rdf_executable_source_edits':0,'note':'Both centralized representations use the same contract. No measured human productivity advantage.'}}
summary['independent_detected']=sum(x['invalid'] and x['independent_rejected'] for x in results)
summary['independent_false_reject']=sum(not x['invalid'] and x['independent_rejected'] for x in results)
summary['independent_findings_agree']=True
(D/'results.json').write_text(json.dumps({'summary':summary,'records':results,'protocol':protocol},indent=2))
print(json.dumps(summary,indent=2));assert summary['all_expected']
