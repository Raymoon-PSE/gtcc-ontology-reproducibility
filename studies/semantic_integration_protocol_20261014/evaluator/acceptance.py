"""Frozen-plan acceptance runner. Independent oracle, never imports an arm to build it."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
QKEY = {'temperature': 'T', 'pressure': 'P', 'mass_flow': 'm_dot'}
QUERY_IDS = {'EngineeringAsset': ['cold_reheat','condensate','gt_exhaust','hot_reheat','hp_steam','lp_steam','st_exhaust'], 'GasTurbine':['gt_exhaust'], 'HeatRecovery':['hot_reheat','hp_steam','lp_steam'], 'SteamExpansion':['cold_reheat','st_exhaust'], 'HeatSink':['condensate']}

def read(path):
    return json.loads((ROOT / path).read_text())

PLAN = read('protocol/CASE_PLAN.json')

def snapshot(v):
    return ([read(f'providers/provider_{p}_v{v}.json') for p in ('a','b')], read(f'providers/boundary_mapping_v{v}.json'), read('protocol/canonical_classes.json'))

def endpoint_meta(providers, endpoint):
    provider = next(p for p in providers if p['provider_id'] == endpoint['provider_id'])
    port = next(p for p in provider['ports'] if (p['namespace'],p['local_port_id']) == (endpoint['namespace'],endpoint['local_port_id']))
    return provider, port

def encode(value, unit):
    return {'degC':lambda x:x, 'K':lambda x:x+273.15, 'MPa':lambda x:x, 'bar':lambda x:x*10, 'Pa':lambda x:x*1000000, 'kg/h':lambda x:x, 'kg/s':lambda x:x/3600}[unit](value)

def base_inputs(v, ambient):
    providers, mapping, classes = snapshot(v)
    streams = read('fixtures/whole_cycle.json')[str(ambient)]['streams']
    payloads = []
    for b in mapping['boundaries']:
        stream = streams[b['canonical_boundary_id']]
        for role in ('producer','consumer'):
            endpoint = b[role]
            p, port = endpoint_meta(providers, endpoint)
            fields = {f['local_key']:encode(stream[QKEY[f['quantity']]], f['unit']) for f in p['field_sets'][port['field_set_id']]}
            payloads.append({'endpoint':copy.deepcopy(endpoint), 'schema_version':p['version'], 'fields':fields, 'composition':copy.deepcopy(stream['w'])})
    return [providers, mapping, classes, payloads, copy.deepcopy(mapping['provider_versions'])]

def expected_result(v, ambient):
    providers, mapping, classes = snapshot(v)
    streams = read('fixtures/whole_cycle.json')[str(ambient)]['streams']
    records = []
    for b in mapping['boundaries']:
        record = {'boundary_id':b['canonical_boundary_id']}
        record.update({k:copy.deepcopy(streams[record['boundary_id']][k]) for k in ('T','P','m_dot','w')})
        for role in ('producer','consumer'):
            p, port = endpoint_meta(providers, b[role])
            equip = next(e for e in p['equipment'] if e['local_equipment_id']==port['local_equipment_id'])
            parents = {t['local_type_id']:t['parent_type_id'] for t in p['types']}
            local, node = [], equip['local_type_id']
            while node is not None:
                if node in local: raise ValueError('oracle source cycle')
                local.append(node)
                node = parents[node]
            canonical = set()
            for fact in classes['provider_type_mappings']:
                if fact['provider']==p['provider_id'] and fact['local_type'] in local:
                    node = fact['canonical_type']
                    while node is not None:
                        canonical.add(node)
                        node = classes['canonical_parent'][node]
            descriptor = dict(b[role], schema_version=p['version'], local_equipment_id=equip['local_equipment_id'], local_type_id=equip['local_type_id'], local_ancestors=sorted(local), canonical_ancestors=sorted(canonical))
            descriptor['provenance'] = {QKEY[f['quantity']]:{'field':f['local_key'],'unit':f['unit']} for f in p['field_sets'][port['field_set_id']]}
            descriptor['provenance']['w'] = {'field':'composition','unit':'mass_fraction'}
            record[role] = descriptor
        record['canonical_ancestors'] = record['producer']['canonical_ancestors'][:]
        records.append(record)
    return {'status':'accepted','boundaries':sorted(records,key=lambda x:x['boundary_id'])}

def case_inputs(case, ambient):
    if isinstance(case,str): case = next(c for c in PLAN['case_families'] if c['id']==case)
    args = base_inputs(case['introduced_stage']+1, ambient)
    providers, mapping, classes, payloads, versions = args
    cid = case['id']
    a = next(p for p in providers if p['provider_id']=='A')
    def boundary(name): return next(b for b in mapping['boundaries'] if b['canonical_boundary_id']==name)
    def payload(name,role): return next(p for p in payloads if p['endpoint']==boundary(name)[role])
    def alias(p,quantity):
        native,port = endpoint_meta(providers,p['endpoint'])
        return next(f['local_key'] for f in native['field_sets'][port['field_set_id']] if f['quantity']==quantity)
    gt = payload('gt_exhaust','producer')
    if cid=='ORDER':
        providers.reverse(); payloads.reverse()
        for p in providers:
            for key in ('ports','types','equipment'): p[key].reverse()
            for fields in p['field_sets'].values(): fields.reverse()
        for key in ('boundaries','field_mappings','conversion_definitions'): mapping[key].reverse()
        classes['provider_type_mappings'].reverse()
    elif cid=='IDEMPOTENT':
        for key in ('boundaries','field_mappings'): mapping[key].append(copy.deepcopy(mapping[key][0]))
    elif cid=='MISSING_BOUNDARY': mapping['boundaries'].remove(boundary('condensate'))
    elif cid=='DUPLICATE_ENDPOINT': boundary('hot_reheat')['producer'] = copy.deepcopy(boundary('hp_steam')['producer'])
    elif cid=='BAD_UNIT':
        for fields in a['field_sets'].values():
            for f in fields:
                if f['quantity']=='temperature': f['unit']='kg/s'
        for f in mapping['field_mappings']:
            if f['provider_id']=='A' and f['canonical_quantity']=='temperature': f['declared_unit']='kg/s'
    elif cid=='FIELD_CONFLICT':
        next(f for f in mapping['field_mappings'] if f['provider_id']=='A' and f['canonical_quantity']=='pressure')['declared_unit']='MPa'
    elif cid=='NO_PAYLOAD': payloads.remove(gt)
    elif cid=='EXTRA_ALIAS': gt['fields']['undeclared_extra_alias']=1.0
    elif cid=='BOOL': gt['fields'][alias(gt,'temperature')]=True
    elif cid=='NONFINITE': gt['fields'][alias(gt,'pressure')]=float('nan')
    elif cid=='NEG_PRESSURE': gt['fields'][alias(gt,'pressure')]=-1
    elif cid=='BAD_COMPOSITION': gt['composition']={'N2':0.5}
    elif cid=='ENDPOINT_MISMATCH':
        p=payload('hp_steam','consumer'); p['fields'][alias(p,'temperature')]+=10
    elif cid=='WRONG_VERSION': versions['A']='99.0'
    elif cid=='CLASS_CYCLE': next(t for t in a['types'] if t['local_type_id']=='ThermalAsset')['parent_type_id']='HRSG'
    elif cid=='NO_ROOT_MAPPING': classes['provider_type_mappings']=[m for m in classes['provider_type_mappings'] if m['provider']!='A']
    elif cid=='OLD_ALIAS':
        key=alias(gt,'temperature'); gt['fields']['temp']=gt['fields'].pop(key)
    elif cid=='MIXED_VERSION': gt['schema_version']='1.0'
    elif cid=='V3_CONFLICT': args[1]=read('providers/variant_v3_conflicting_boundary_mapping.json')
    elif cid=='V3_PARENT': args[0][args[0].index(a)]=read('providers/variant_v3_missing_parent_provider_a.json')
    elif cid=='V3_NAMESPACE': args[1]=read('providers/variant_v3_unqualified_boundary_mapping.json')
    elif cid not in ('BASE','IMMUTABLE','V2_UPGRADE','TRANSITIVE','V3_QUALIFIED'): raise ValueError(cid)
    return args

def same(a,b):
    """Exact recursive input comparison; NaN is stable but bool is not numeric."""
    if type(a) is not type(b): return False
    if isinstance(a,float) and math.isnan(a): return math.isnan(b)
    if isinstance(a,dict): return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)): return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return a==b

def check_equal(actual, expected, path='result'):
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or not expected.keys() <= actual.keys(): raise AssertionError(f'{path}: required dictionary keys missing')
        if path.endswith('.w') and actual.keys()!=expected.keys(): raise AssertionError(f'{path}: composition species differ')
        for key,value in expected.items(): check_equal(actual[key],value,path+'.'+key)
    elif isinstance(expected,list):
        if not isinstance(actual,list) or len(actual)!=len(expected): raise AssertionError(f'{path}: list length/type differs')
        for i,(a,e) in enumerate(zip(actual,expected)): check_equal(a,e,f'{path}[{i}]')
    elif isinstance(expected,(int,float)) and not isinstance(expected,bool):
        if isinstance(actual,bool) or not isinstance(actual,(int,float)) or not math.isfinite(actual): raise AssertionError(f'{path}: not a finite number')
        composition = '.w.' in path
        if not math.isclose(actual,expected,rel_tol=0 if composition else 1e-10,abs_tol=1e-8 if composition else 1e-6): raise AssertionError(f'{path}: {actual!r} != {expected!r}')
    elif type(actual) is not type(expected) or actual!=expected: raise AssertionError(f'{path}: {actual!r} != {expected!r}')

def check_records(actual, expected, ordered=False):
    if not isinstance(actual,list): raise AssertionError('records must be a list')
    if not ordered:
        actual = sorted(actual,key=lambda r:r['boundary_id'])
    check_equal(actual,expected)

def check_rejected(result, code):
    if not isinstance(result,dict) or not {'status','error'} <= set(result) or 'boundaries' in result: raise AssertionError('rejection requires status/error and forbids boundaries')
    if result['status']!='rejected': raise AssertionError('expected rejection')
    error=result['error']
    if not isinstance(error,dict) or not {'code','detail'} <= set(error) or error['code']!=code or not isinstance(error['detail'],str) or not error['detail'].strip(): raise AssertionError(f'expected {code} and nonempty detail')

def checked_call(fn,*args):
    before=copy.deepcopy(args)
    try: return fn(*args)
    finally:
        if not same(args,before): raise AssertionError(f'{fn.__name__} mutated caller inputs')

def valid_checks(module, result, expected, versions, observations):
    if not isinstance(result,dict) or not {'status','boundaries'} <= set(result) or result['status']!='accepted': raise AssertionError('expected accepted result')
    check_records(result['boundaries'],expected['boundaries'])
    q=checked_call(module.query_all,result); observations['Q1']=copy.deepcopy(q)
    check_records(q,expected['boundaries'],ordered=True)
    observations['Q2']={}
    for ancestor,ids in QUERY_IDS.items():
        q=checked_call(module.query_by_ancestor,result,ancestor); observations['Q2'][ancestor]=copy.deepcopy(q)
        check_records(q,[r for r in expected['boundaries'] if r['boundary_id'] in ids])
    q=checked_call(module.query_returns,result,versions); observations['Q3']=copy.deepcopy(q)
    check_records(q,[r for r in expected['boundaries'] if r['boundary_id'] in ('cold_reheat','condensate')])
    bad=dict(versions,A='99.0')
    q=checked_call(module.query_returns,result,bad); observations['Q3_wrong_version']=copy.deepcopy(q)
    check_rejected(q,'VERSION_MISMATCH')

def json_safe(value):
    if isinstance(value,float) and not math.isfinite(value): return {'nonfinite':repr(value)}
    if isinstance(value,dict): return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [json_safe(v) for v in value]
    if value is None or isinstance(value,(str,int,float,bool)): return value
    return {'python_type':type(value).__name__,'repr':repr(value)}

def evaluate(module, stage):
    if type(stage) is not int or stage not in (0,1,2): raise ValueError('stage must be 0, 1, or 2')
    records=[]
    for case in PLAN['case_families']:
        if case['introduced_stage']>stage: continue
        for ambient in case['ambient_keys']:
            row={'case_id':case['id'],'ambient':ambient,'snapshot_version':f"{case['introduced_stage']+1}.0",'expected':case['expected'],'passed':False,'observed':{}}
            records.append(row)
            try:
                args=case_inputs(case,ambient)
                result=checked_call(module.integrate,*args)
                row['observed']['integrate']=copy.deepcopy(result)
                if case['expected']=='accepted': valid_checks(module,result,expected_result(case['introduced_stage']+1,ambient),args[4],row['observed'])
                else: check_rejected(result,case['expected'])
                row['passed']=True
            except Exception as exc: row['failure']={'type':type(exc).__name__,'detail':str(exc)}
    for i,example in enumerate(PLAN['conversion_oracles'],1):
        row={'case_id':f'CONVERSION_{i}','ambient':None,'expected':example,'passed':False}
        records.append(row)
        try:
            quantity={'degC':'temperature','MPa':'pressure','kg/h':'mass_flow'}[example['canonical_unit']]
            value=checked_call(module.normalize_quantity,quantity,example['input'],example['unit'])
            row['observed']=value; check_equal(value,example['output']); row['passed']=True
        except Exception as exc: row['failure']={'type':type(exc).__name__,'detail':str(exc)}
    return json_safe({'suite':'frozen-plan executable acceptance','stage':stage,'case_count':len(records),'passed':sum(r['passed'] for r in records),'records':records})

def load_candidate(path):
    path=Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix!='.py': raise ValueError('candidate must be a Python adapter file')
    # Only the specified candidate folder is added. This is not a security sandbox.
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('candidate_adapter',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--stage',type=int,choices=(0,1,2),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('output exists; refusal to overwrite prior evidence')
    module=load_candidate(args.candidate)
    report=evaluate(module,args.stage)
    report['candidate']={'path':str(args.candidate.resolve()),'sha256':hashlib.sha256(args.candidate.read_bytes()).hexdigest()}
    with args.output.open('x') as f: json.dump(report,f,indent=2,allow_nan=False); f.write('\n')
    print(f"{report['passed']}/{report['case_count']} passed")
    return 0 if report['passed']==report['case_count'] else 1

if __name__=='__main__': sys.exit(main())
