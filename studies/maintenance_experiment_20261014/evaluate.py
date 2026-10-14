#!/usr/bin/env python3
"""Checkpoint and execute procedurally held-out acceptance checks in separate processes."""
import os,sys,json,hashlib,shutil,subprocess,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True

def main():
 p=argparse.ArgumentParser();p.add_argument('--stage',required=True,choices=['change1','change2']);p.add_argument('--attempt',type=int,default=1);p.add_argument('--worker',choices=['rdf','json']);a=p.parse_args()
 if a.worker:
  import socket
  def deny(*args,**kw):raise RuntimeError('Network disabled')
  socket.socket.connect=deny
  cp=ROOT/'checkpoints'/f'{a.stage}_attempt{a.attempt}'/a.worker
  sys.path.insert(0,str(cp));sys.path.insert(1,str(ROOT/'evaluator'))
  import adapter,stores
  cls=stores.RDFStore if a.worker=='rdf' else stores.JSONStore
  from check_adapter import checks
  rows=checks(adapter,cls)
  if a.stage=='change2':
   from check_publication import checks as publication_checks
   rows.extend(publication_checks(adapter,cls))
   from check_physical import checks as physical_checks
   rows.extend(physical_checks(adapter,cls))
  print(json.dumps(rows,allow_nan=False));return
 folder=ROOT/'checkpoints'/f'{a.stage}_attempt{a.attempt}'
 if folder.exists():raise RuntimeError('Checkpoint exists; do not overwrite evidence')
 folder.mkdir(parents=True)
 for arm in ['rdf','json']:shutil.copytree(ROOT/'arms'/arm,folder/arm,ignore=shutil.ignore_patterns('__pycache__','._*'))
 # Freeze evaluator bytes before loading candidate code.
 hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in list((ROOT/'evaluator').glob('*.py'))+list((ROOT/'protocol').glob('*.txt'))+list((ROOT/'fixtures').glob('*.json'))+[Path(__file__).resolve()]}
 (folder/'evaluator_protocol_hashes.json').write_text(json.dumps(hashes,indent=2))
 results={}
 for arm in ['rdf','json']:
  command=[sys.executable,'-B',str(Path(__file__).resolve()),'--stage',a.stage,'--attempt',str(a.attempt),'--worker',arm]
  run=subprocess.run(command,text=True,capture_output=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHON_DOTENV_DISABLED':'1'},timeout=120)
  if run.returncode:results[arm]={'harness_failure':run.stderr,'stdout':run.stdout}
  else:results[arm]=json.loads(run.stdout)
 output=ROOT/'results'/f'{a.stage}_attempt{a.attempt}.json';output.write_text(json.dumps(results,indent=2)+'\n')
 for arm,rows in results.items():
  if isinstance(rows,list):print(arm,sum(r['passed'] for r in rows),'/',len(rows),'failures',[r for r in rows if not r['passed']])
  else:print(arm,rows)

if __name__=='__main__':main()
