"""Export machine-readable tables from archived paper results; no new measurements."""
from pathlib import Path
import json,csv
ROOT=Path(__file__).resolve().parents[1];R=json.loads((ROOT/'data/archived/results.json').read_text());O=ROOT/'outputs/tables';O.mkdir(parents=True,exist_ok=True)
def write(name,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with (O/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
write('efficiency_scenarios.csv',[{'eta_comp':x['eta'],**x['kpis']} for x in R['scenarios']])
write('diagnostic_sensitivity.csv',[{'eta_comp':x['eta'],'case':tag,'surge_input':entry['surge_input'],**entry['posterior']} for x in R['scenarios'] for tag,entry in x['diagnosis'].items()])
for kind in ['mc','grid']:
 write(kind+'_successful.csv',[{'index':x.get('index',i),**x['params'],**x['kpis']} for i,x in enumerate(R[kind])])
 write(kind+'_failed.csv',[{'index':x.get('index',i),**x['params'],'error':x['error']} for i,x in enumerate(R['failures']) if x['kind']==kind])
print('CSV tables exported to outputs/tables.')
