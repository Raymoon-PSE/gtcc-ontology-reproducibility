#!/usr/bin/env python3
"""Local-only reproducible comparison. Run from any working directory."""
import os
os.environ['PYTHON_DOTENV_DISABLED']='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
import sys
sys.dont_write_bytecode=True
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source_snapshot'));sys.path.insert(0,str(ROOT))
# This experiment never needs a network connection. Fail closed if a dependency tries.
import socket

def denied(*args,**kwargs):raise RuntimeError('Network disabled for isolated experiment')
socket.socket.connect=denied
socket.create_connection=denied
import json,time,hashlib,platform,traceback,importlib.metadata,copy
from benchmark.scenarios import suite_cases,scenario_facts,execute_case,evidence,assert_equivalent,assert_physical,RTOL,ATOL
from benchmark.stores import STORES,fact_delta
from benchmark.contracts import base_facts
from benchmark.physics import run_physics,summarize


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def verify_source():
    manifest=json.loads((ROOT/'source_manifest.json').read_text());mismatch=[]
    for item in manifest['files']:
        path=ROOT/'source_snapshot'/item['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:mismatch.append(item['path'])
    if mismatch:raise RuntimeError('Snapshot changed: '+str(mismatch))
    return len(manifest['files'])


def prepare():
    cases=suite_cases();fixture_hashes={}
    if (ROOT/'protocol/cases.json').exists():
        if json.loads((ROOT/'protocol/cases.json').read_text())!=cases:raise RuntimeError('Frozen case definitions changed; preserve old protocol before amendment')
        spec=json.loads((ROOT/'protocol/oracle_spec.json').read_text())
        if spec['rtol']!=RTOL or spec['atol']!=ATOL:raise RuntimeError('Frozen tolerances differ from implementation')
        hashes=json.loads((ROOT/'protocol/fixture_hashes.json').read_text())
        for path,digest in hashes.items():
            if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise RuntimeError('Frozen fixture changed: '+path)
        return cases
    for case in cases:
        folder=ROOT/'protocol/fixtures'/case['id'];folder.mkdir(parents=True,exist_ok=True)
        facts=scenario_facts(case)
        for backend,cls in STORES.items():
            ext='ttl' if backend=='rdf' else 'json'
            for state,ff in [('before',base_facts()),('after',facts)]:
                path=folder/(state+'.'+ext);path.write_text(cls(ff).dumps())
                fixture_hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
        save(folder/'logical_diff.json',fact_delta(base_facts(),facts))
    save(ROOT/'protocol/cases.json',cases)
    save(ROOT/'protocol/fixture_hashes.json',fixture_hashes)
    save(ROOT/'protocol/oracle_spec.json',{'rtol':RTOL,'atol':ATOL,'external_mass_atol_kg_hr':1e-6,
        'external_energy_atol_kW':.01,'physics':'linked','ambient_C':[5,15,25],
        'expected_case_count':len(cases),'failures_are_not_validation_rejections':True})
    return cases


def run():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');p.add_argument('--results',default='results/main');args=p.parse_args()
    source_count=verify_source();cases=prepare()
    print('Prepared',len(cases),'fixed cases; verified',source_count,'source files',flush=True)
    if args.prepare_only:return
    dest=ROOT/args.results
    if (dest/'summary.json').exists():raise RuntimeError('Completed results exist; choose a new --results folder to preserve them')
    dest.mkdir(parents=True,exist_ok=True)
    save(dest/'implementation_hashes.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'benchmark').glob('*.py'))+list((ROOT/'tests').glob('*.py'))+list(ROOT.glob('run_*.py'))})
    save(dest/'protocol_hashes.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'protocol').rglob('*') if p.is_file()})
    env={'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),
         'processor':platform.processor(),'source_files':source_count,'network':'socket connections disabled',
         'packages':{name:importlib.metadata.version(name) for name in ['numpy','scipy','CoolProp','cantera','rdflib','python-dotenv','pytest']}}
    save(dest/'environment.json',env)
    oracle={};repeatability=[]
    for ambient in [5,15,25]:
        o,r=run_physics(ambient);oracle[ambient]=evidence(o,r,'json');assert_physical(oracle[ambient]['physical'])
        o2,r2=run_physics(ambient);other=summarize(o2,r2)
        assert_equivalent(other,oracle[ambient]['physical'])
        repeatability.append({'ambient_C':ambient,'exact_repeat':other==oracle[ambient]['physical']})
    save(dest/'oracles.json',oracle);save(dest/'baseline_repeatability.json',repeatability)
    print('Independent unadapted linked-cycle references complete',flush=True)
    rows=[];pairs=[]
    for index,case in enumerate(cases):
        pair={}
        for backend in (['rdf','json'] if index%2==0 else ['json','rdf']):
            ext='ttl' if backend=='rdf' else 'json'
            path=ROOT/'protocol/fixtures'/case['id']/('after.'+ext)
            begin=time.perf_counter()
            try:
                store=STORES[backend].loads(path.read_text())
                observed=execute_case(case,store,backend,oracle)
                passed=observed['outcome']==case['expected']
                if case['expected']=='reject':passed=passed and case['error_contains'] in observed.get('reason','')
                observed['matches_frozen_oracle']=passed
            except Exception as exc:
                observed={'outcome':'HARNESS_FAILURE','matches_frozen_oracle':False,'exception_type':type(exc).__name__,
                          'reason':str(exc),'traceback':traceback.format_exc()}
            elapsed=time.perf_counter()-begin
            row={'case':case,'backend':backend,'wall_seconds_context_only':elapsed,'observed':observed}
            # Wall time includes asymmetric existing-runtime setup and is NOT performance comparison evidence.
            save(dest/'cases'/(case['id']+'_'+backend+'.json'),row)
            rows.append({'id':case['id'],'task':case['task'],'variant':case['variant'],'backend':backend,
                         'expected':case['expected'],'outcome':observed['outcome'],
                         'passed':observed['matches_frozen_oracle'],'stage':observed.get('stage'),
                         'reason':observed.get('reason'),'wall_seconds_context_only':elapsed})
            pair[backend]=observed
        parity=False;reason=None
        try:
            assert pair['rdf']['outcome']==pair['json']['outcome']
            if pair['rdf']['outcome']=='accept':assert_equivalent(pair['rdf']['evidence'],pair['json']['evidence'])
            elif pair['rdf']['outcome']=='reject':
                assert pair['rdf']['reason']==pair['json']['reason']
                assert pair['rdf']['current_result_published']==pair['json']['current_result_published']
            else:raise AssertionError('Neither arm completed')
            parity=True
        except Exception as exc:reason=str(exc)
        pairs.append({'id':case['id'],'parity':parity,'reason':reason})
        print(case['id'],[(b,pair[b]['outcome'],pair[b]['matches_frozen_oracle']) for b in pair],flush=True)
    save(dest/'case_summary.json',rows);save(dest/'paired_parity.json',pairs)
    summary={'case_definitions':len(cases),'arm_runs':len(rows),'oracle_passes':sum(r['passed'] for r in rows),
             'paired_parity_passes':sum(p['parity'] for p in pairs),
             'accepted_cases_per_arm':sum(c['expected']=='accept' for c in cases),
             'seeded_rejections_per_arm':sum(c['expected']=='reject' for c in cases),
             'all_passed':all(r['passed'] for r in rows) and all(p['parity'] for p in pairs),
             'source_files_verified_after_run':verify_source(),
             'ontology_superiority_established':False,
             'scope':'Controlled representation/adapter parity, no measured human maintenance effort or plant accuracy'}
    save(dest/'summary.json',summary);print(json.dumps(summary,indent=2),flush=True)
    if not summary['all_passed']:sys.exit(1)

if __name__=='__main__':run()
