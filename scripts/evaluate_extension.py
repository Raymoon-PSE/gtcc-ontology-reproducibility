"""Predefined indicator-addition task with RDF and conventional configurations."""
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from dataclasses import asdict
import sys,json,shutil,warnings,hashlib
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from rdflib import Literal
from eklm.kas.legacy_bridge.graph import load_graph,PM
from eklm.kas.legacy_bridge.integrity import default_contract,graph_records
from eklm.kas.legacy_bridge.mech_bridge import _PROP_MAP
from eklm.kas.legacy_bridge.input_policy import resolve_parameters,validate_outputs
from eklm.vdt.mechanical.data_package import DeviceDataPackage,DataStatus
from eklm.vdt.mechanical.reference_db import ReferenceDatabase
from eklm.vdt.mechanical.model_router import ModelRouter
from eklm.kas.legacy_bridge.runtime import _CATALOG
from eklm.vdt.gui_adapter import run_gtcc
from eklm.kas.legacy_bridge.bayesian import _extract_observations,diagnose_bayesian
from conventional_control import check_records
from inspection_extension import TYPE,KEY,install
warnings.filterwarnings('ignore');O=R/'outputs/extension';O.mkdir(parents=True,exist_ok=True)
install();PROP=PM.mech_inspectionWindowRatio;_PROP_MAP[KEY]=PROP
protocol={'task':'Add a compressor inspection-window ratio to the existing mechanical interface and retrieve it with equipment identity, preserving other calculations.',
 'indicator':'conditional remaining_life_hr / declared inspection_window_hr; planning demonstration, not an operational recommendation',
 'expected_cases':{'nominal':2.5,'aged':1.5,'short_window':5.0,'inactive':None,'missing_window':'reject','wrong_type':'reject','missing_binding':'reject','invalid_window':'reject'},
 'shared':'unchanged process/physical models; one extension plugin; reference-schema/input policy; output validation',
 'conventional_control':'independent JSON adapter, explicit publication dictionary and direct query; contract validator independently implemented',
 'measures':['expected acceptance','indicator value','unchanged process outputs','non-target mechanical results','provenance completeness','query retrieval','absence after rejection','changed logical configuration fields'],
 'limits':'One declared extension and development cases; no developer-time, cross-plant portability, physical maintenance benefit, or RDF superiority claim.'}
(O/'protocol.json').write_text(json.dumps(protocol,indent=2))
query='PREFIX pm: <http://plantmind.io/ontology/gtcc#> SELECT ?device ?ratio WHERE { ?device pm:mech_inspectionWindowRatio ?ratio . }'
(O/'extension.rq').write_text(query+'\n')
records=[];base_contract=default_contract();base_rows=graph_records(load_graph());c=deepcopy(base_contract);c['devices'][str(PM['COMP-001'])]['model']=TYPE
changes={'common_artifacts':['inspection_extension.py: new wrapper model and registration','reference schema: add the derived model type and inspection_window_hr'],
 'rdf_changes':{'device_model_binding':1,'engineering_contract_model':1,'output_binding':1,'retrieval_query':1},
 'json_changes':{'device_model_binding':1,'engineering_contract_model':1,'output_binding':1,'retrieval_query':1},
 'definition':'Counts are changed named declarations for this task, not source lines or developer effort; shared plugin/reference data excluded from arm-specific totals.'}
(O/'change_manifest.json').write_text(json.dumps(changes,indent=2))
with TemporaryDirectory() as tmp:
 refdir=Path(tmp)
 for path in (R/'data/reference').glob('*.json'):shutil.copyfile(path,refdir/path.name)
 ref=json.loads((refdir/'netl_case13.json').read_text());ref[TYPE]={**ref['Compressor'],'inspection_window_hr':10000};(refdir/'netl_case13.json').write_text(json.dumps(ref,indent=2));refdb=ReferenceDatabase(refdir)
 (O/'reference_extension.json').write_text(json.dumps(ref[TYPE],indent=2))
 for name,expected in protocol['expected_cases'].items():
  hours=20000 if name=='aged' else 10000
  baseline,_=run_gtcc({'ontology_runtime':True,'ontology_graph':load_graph(),'cumulative_hours':hours})
  g=load_graph();rows=deepcopy(base_rows);plain={n:{'type':t,'unit':u,'status':'PARTIAL','required':{},'optional':{}} for n,(t,u) in _CATALOG.items()}
  dtype='Compressor' if name=='wrong_type' else TYPE
  supplied=refdb.get_defaults(TYPE)
  if name=='short_window':supplied['inspection_window_hr']=5000
  if name=='missing_window':supplied.pop('inspection_window_hr')
  if name=='invalid_window':supplied['inspection_window_hr']=0
  status='NONE' if name=='inactive' else 'FULL'
  plain['COMP-001'].update(type=dtype,status=status,required=supplied)
  g.set((PM['COMP-001'],PM.mech_deviceType,Literal(dtype)));g.set((PM['COMP-001'],PM.mech_hasDataStatus,PM['mech_DataStatus_'+status]));g.set((PM['COMP-001'],PM.mech_requiredParameters,Literal(json.dumps(supplied))))
  rows[str(PM['COMP-001'])]['mech_deviceType']=[dtype];rows[str(PM['COMP-001'])]['mech_hasDataStatus']=[str(PM['mech_DataStatus_'+status])]
  # Start each arm with a valid published result, then change its configuration.
  prior=deepcopy(g);prior.set((PM['COMP-001'],PM.mech_deviceType,Literal(TYPE)));prior.set((PM['COMP-001'],PM.mech_requiredParameters,Literal(json.dumps(refdb.get_defaults(TYPE)))));prior.set((PM['COMP-001'],PM.mech_hasDataStatus,PM.mech_DataStatus_FULL))
  run_gtcc({'ontology_runtime':True,'ontology_graph':prior,'engineering_contract':c,'mechanical_reference_dir':refdir,'cumulative_hours':hours})
  for p in [PM.mech_deviceType,PM.mech_hasDataStatus,PM.mech_requiredParameters]:
   prior.remove((PM['COMP-001'],p,None))
   for value in g.objects(PM['COMP-001'],p):prior.add((PM['COMP-001'],p,value))
  g=prior
  folder=O/name;folder.mkdir(exist_ok=True);g.serialize(folder/'input.nt',format='nt');(folder/'input.json').write_text(json.dumps(plain,indent=2));(folder/'resolved_contract_input.json').write_text(json.dumps(rows,indent=2));(folder/'contract.json').write_text(json.dumps(c,indent=2))
  if name=='missing_binding':_PROP_MAP.pop(KEY)
  else:_PROP_MAP[KEY]=PROP
  result={'case':name,'expected':expected,'hours':hours}
  try:
   d,rr=run_gtcc({'ontology_runtime':True,'ontology_graph':g,'engineering_contract':c,'mechanical_reference_dir':refdir,'cumulative_hours':hours})
   bindings=[{'device':str(x.device),'ratio':float(x.ratio)} for x in g.query(query)]
   rdf={'valid':True,'mechanical':[asdict(x) for x in d['mech_results']],'trace':d['ontology_runtime']['routing'],'W_net':d['W_net'],'bindings':bindings}
  except ValueError as exc:rdf={'valid':False,'error':str(exc),'bindings':[]};assert not list(g.query(query))
  published={str(PM['COMP-001']):{KEY:2.5}};published.clear()
  try:
   if check_records(rows,c):raise ValueError('Conventional engineering contract rejected')
   packages=[]
   for device,x in sorted(plain.items()):
    defaults=refdb.get_defaults(x['type']);resolved,supply=resolve_parameters(defaults,x['required'],x['optional'],x['status'])
    pkg=DeviceDataPackage(device,x['type'],x['unit'],resolved,x['optional']);pkg.status=DataStatus(x['status']);packages.append((pkg,{'device_id':device,'declared_status':x['status'],'reference_parameters':sorted(set(defaults)-set(supply)) if x['status']=='PARTIAL' else [],'explicit_parameters':sorted(supply)}))
   _,op=run_gtcc({'cumulative_hours':hours});mech=[];trace=[];staged={};router=ModelRouter(refdb)
   for pkg,tr in packages:
    model=router.route(pkg);out=model.run(op.operating_point);validate_outputs(out,pkg);out.uncertain_params=sorted(set(out.uncertain_params)|set(tr['reference_parameters']));mech.append(out);tr.update(model=type(model).__name__,result_status=out.status);trace.append(tr);staged[str(PM[pkg.device_id])]=out.outputs
   published=staged
   bindings=[{'device':device,'ratio':out[KEY]} for device,out in published.items() if KEY in out]
   conventional={'valid':True,'mechanical':[asdict(x) for x in mech],'trace':trace,'W_net':op.W_net,'bindings':bindings}
  except ValueError as exc:conventional={'valid':False,'error':str(exc),'bindings':[]};assert not published
  assert rdf['valid']==conventional['valid']==(expected!='reject'),name
  if expected!='reject':
   assert rdf==conventional,name
   assert rdf['W_net']==baseline['W_net']
   for old in baseline['mech_results']:
    if old.device_id!='COMP-001':assert asdict(old)==next(x for x in rdf['mechanical'] if x['device_id']==old.device_id)
   assert rdf['bindings']==([] if expected is None else [{'device':str(PM['COMP-001']),'ratio':expected}])
  result.update(rdf=rdf,json=conventional);records.append(result);(folder/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
  _PROP_MAP[KEY]=PROP
summary={'cases':len(records),'valid':sum(x['rdf']['valid'] for x in records),'invalid':sum(not x['rdf']['valid'] for x in records),'all_expected_and_paired_checks_pass':True,'arm_specific_declaration_changes':{'rdf':4,'json':4},'shared_plugin_sha256':hashlib.sha256(Path(__file__).with_name('inspection_extension.py').read_bytes()).hexdigest(),'benefit_demonstrated':'Traceable propagation and failure handling for one declared indicator extension in both arms, not lower effort or representation superiority.'}
(O/'results.json').write_text(json.dumps({'summary':summary,'records':records,'protocol':protocol},indent=2));print(json.dumps(summary,indent=2))
