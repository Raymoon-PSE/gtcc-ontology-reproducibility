"""Verify the v0.4.0 derived release and rerun stored-fixture acceptance.
Does not rerun the physical solver or benchmark machine performance.
"""
import hashlib,json,math,statistics,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];ST=ROOT/'studies'
def read(p):return json.loads(p.read_text())
def run(*args):
 p=subprocess.run([sys.executable,'-B',*map(str,args)],check=True,capture_output=True,text=True)
 return json.loads(p.stdout)
def main():
 manifest=read(ST/'PUBLIC_DERIVATION.json')
 for row in manifest['files']:
  assert hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['public_sha256'],row['path']
 print('Public derived-file hashes verified:',len(manifest['files']))
 a=ST/'revision_experiment_20261013/results';rows=read(a/'main/case_summary.json');pairs=read(a/'main/paired_parity.json')
 assert len(rows)==56 and len(pairs)==28 and all(x['passed'] for x in rows) and all(x['parity'] for x in pairs)
 for arm in ['rdf','json']:
  rr=[x for x in rows if x['backend']==arm];assert len(rr)==28
  assert sum(x['outcome']=='accept' for x in rr)==10
  assert all(x['outcome']==x['expected'] for x in rr)
 raw=read(a/'performance/raw_timings.json');summary=read(a/'performance/summary.json');assert len(raw)==208
 for row in summary:
  for phase,n in [('cold',6),('warm',20)]:
   vals=[x['ns']/1e6 for x in raw if x['backend']==row['backend'] and x['scale']==row['scale'] and x['phase']==phase]
   assert len(vals)==n
   assert math.isclose(statistics.median(vals),row[phase+'_median_ms'],abs_tol=1e-10)
 print('Whole-process archived records: 28 pairs, 10 accepted + 18 rejected per arm; 208 raw timings reproduce reported medians.')
 p=ST/'semantic_integration_protocol_20261014'
 with tempfile.TemporaryDirectory() as td:
  for arm in ['rdf1','json1','rdf2','json2']:
   for stage in range(3):
    name=f'{arm}_stage{stage}_attempt1';out=Path(td)/(name+'.json')
    subprocess.run([sys.executable,'-B',str(p/'evaluator/acceptance.py'),'--candidate',str(p/'execution/checkpoints'/name/'adapter.py'),'--stage',str(stage),'--output',str(out)],check=True,capture_output=True)
    fresh=read(out);old=read(p/'execution/results'/(name+'.json'))
    assert fresh['records']==old['records'] and fresh['passed']==old['passed']==[40,48,56][stage]
 print('Provider integration: all 12 original checkpoints reproduced exactly (40, 48, 56 per replicate).')
 m=ST/'maintenance_experiment_20261014'
 for stage,attempt in [('change1',1),('change2',1),('change2',2)]:
  saved=read(m/'results'/f'{stage}_attempt{attempt}.json')
  for arm in ['rdf','json']:
   fresh=run(m/'evaluate.py','--stage',stage,'--attempt',attempt,'--worker',arm)
   assert fresh==saved[arm],(stage,attempt,arm)
 for checkpoint in ['change2_attempt1','change2_attempt2']:
  for arm in ['rdf','json']:
   fresh=run(m/'posthoc_check.py','--checkpoint',checkpoint,'--arm',arm)
   assert fresh['passed']==(checkpoint=='change2_attempt2' or arm=='json')
 print('Maintenance: original 29/46 and repaired 46 outcomes reproduced; original RDF post hoc failure and repaired success retained.')
 print('PASS. Stored-fixture computational reproduction only. No fresh physics, plant validation or human-effort measurement.')
if __name__=='__main__':main()
