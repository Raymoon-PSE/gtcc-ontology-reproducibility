"""Replay paper inputs and compare computed outputs with archived numerical evidence."""
from pathlib import Path
import sys,json,math,argparse,warnings
from dataclasses import asdict
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from eklm.vdt.gui_adapter import run_gtcc
from eklm.kas.legacy_bridge.bayesian import diagnose_bayesian, LEGACY_DESIGN_REF
warnings.filterwarnings('ignore')
parser=argparse.ArgumentParser();parser.add_argument('--quick',action='store_true');args=parser.parse_args()
archive=json.loads((ROOT/'data/archived/results.json').read_text());out=ROOT/'outputs/numerical';out.mkdir(parents=True,exist_ok=True)
records=[];errors=[];max_rel=0.0;diagnostic_changes=[]

def compare(actual,expected,label):
 global max_rel
 for k,v in expected.items():
  if not isinstance(v,(int,float)):continue
  if k not in actual:
   errors.append({'case':label,'key':k,'error':'missing output'});continue
  a=actual[k]
  if not isinstance(a,(int,float)):continue
  delta=abs(float(a)-float(v))/max(abs(float(v)),1.0);max_rel=max(max_rel,delta)
  if not math.isclose(float(a),float(v),rel_tol=1e-6,abs_tol=1e-5):errors.append({'case':label,'key':k,'expected':v,'actual':a})

def scalar(d):return {k:float(v) for k,v in d.items() if isinstance(v,(int,float))}
for s in archive['scenarios']:
 eta=s['eta'];d,r=run_gtcc({'eta_comp':eta,'sim_mode':'Mechanical','cumulative_hours':10000,'start_stop_count':200});label=f'eta_{eta}'
 compare(d,s['kpis'],label)
 diagnoses={}
 for tag,entry in s['diagnosis'].items():
  p={'eta_comp':eta,'eta_turb':.876}
  if entry['surge_input'] is not None:p['mech_comp_surge_margin_pct']=entry['surge_input']
  values={x.fault_id:x.posterior for x in diagnose_bayesian(r,params=p,reference=LEGACY_DESIGN_REF)}
  # Physical replay and intentional diagnostic-policy changes are separate.
  for fault,value in values.items():
   previous=entry['posterior'][fault]
   if not math.isclose(value,previous,rel_tol=1e-6,abs_tol=1e-5):
    diagnostic_changes.append({'case':label,'mode':tag,'fault':fault,'archived':previous,'current':value})
  diagnoses[tag]=values
 records.append({'case':label,'kpis':scalar(d),'mechanical':[asdict(x) for x in d['mech_results']],'diagnosis':diagnoses})
print('Scenarios checked',len(archive['scenarios']),flush=True)
if not args.quick:
 for kind in ['grid','mc']:
  cases=[(x,True) for x in archive[kind]]+[(x,False) for x in archive['failures'] if x['kind']==kind]
  successes=0;failures=0
  for i,(x,expected_success) in enumerate(cases):
   label=kind+'/'+str(x.get('index',i))
   try:
    d,r=run_gtcc(x['params']);successes+=1
    if not expected_success:errors.append({'case':label,'error':'Archived failure now succeeds'})
    else:compare(d,x['kpis'],label)
    records.append({'case':label,'parameters':x['params'],'kpis':scalar(d),'converged':bool(r.converged)})
   except Exception as exc:
    failures+=1;records.append({'case':label,'parameters':x['params'],'error':str(exc)})
    if expected_success:errors.append({'case':label,'error':str(exc)})
   if (i+1)%100==0:print(kind,i+1,flush=True)
  print(kind,'success',successes,'failure',failures,flush=True)
summary={'quick':args.quick,'records':len(records),'mismatch_count':len(errors),'maximum_scaled_numeric_difference':max_rel,'tolerance':{'rtol':1e-6,'atol':1e-5},'errors':errors,'comparison_scope':'Physical scalar outputs and success/failure outcomes; diagnostic differences from the explicit threshold-equality correction are reported separately.','diagnostic_changes':diagnostic_changes}
(out/'results.json').write_text(json.dumps({'summary':summary,'records':records},indent=2));print(json.dumps(summary,indent=2));sys.exit(bool(errors))
