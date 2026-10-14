"""Post hoc requirement check added after candidate inspection; not a preregistered case."""
import sys,json,argparse
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--checkpoint',default='change2_attempt1');p.add_argument('--arm',required=True,choices=['rdf','json']);a=p.parse_args()
sys.path.insert(0,str(ROOT/'checkpoints'/a.checkpoint/a.arm));sys.path.insert(1,str(ROOT/'evaluator'))
import adapter,stores
from check_adapter import facts,record,equivalent,canonical
cls=stores.RDFStore if a.arm=='rdf' else stores.JSONStore
ff=[(s,p,'' if p=='field_T' else o) for s,p,o in facts()];r=record()
for k in ['values','units']:r[k]['']=r[k].pop('temperature')
try:
 equivalent(adapter.adapt(r,cls(ff).dumps()),canonical());result={'passed':True,'error':None}
except Exception as e:result={'passed':False,'error':type(e).__name__+': '+str(e)}
result.update(id='PH01_empty_unique_wire_name',arm=a.arm,checkpoint=a.checkpoint,classification='post_hoc_code_review_requirement_check')
print(json.dumps(result))
