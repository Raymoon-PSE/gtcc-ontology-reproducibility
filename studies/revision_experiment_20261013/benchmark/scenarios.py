"""Fixed scenario definitions and independent acceptance/parity oracles."""
import copy
import math
from .contracts import base_facts,set_fact,BOUNDARIES,BoundaryAdapter,ContractError,validate_model,validate_hp_output,RevisionStore
from .stores import STORES
from .physics import run_physics,summarize
from .mechanics import make_default_params,run_mechanics

RTOL=1e-10
ATOL=1e-6
HPSH_OLD='mech_hpsh_hoop_stress_MPa'
HPSH_NEW='hpsh_hoop_stress_MPa_v2'
CONSUMERS=('process','operating_point','mechanics','rules','diagnosis','query')
EXPORT_CONSUMERS=('output_contract','publisher','query','warning_export')

def assert_equivalent(actual, expected, path='root'):
    if isinstance(expected, bool) or expected is None or isinstance(expected,str):
        assert type(actual)==type(expected) and actual==expected,(path,actual,expected)
    elif isinstance(expected,(int,float)):
        assert isinstance(actual,(int,float)) and not isinstance(actual,bool),(path,actual)
        assert math.isfinite(actual) and math.isfinite(expected),(path,'nonfinite')
        assert math.isclose(actual,expected,rel_tol=RTOL,abs_tol=ATOL),(path,actual,expected)
    elif isinstance(expected,dict):
        assert actual.keys()==expected.keys(),(path,'keys',actual.keys(),expected.keys())
        for k,v in expected.items():assert_equivalent(actual[k],v,path+'.'+k)
    elif isinstance(expected,(list,tuple)):
        assert len(actual)==len(expected),(path,'length')
        for i,(a,e) in enumerate(zip(actual,expected)):assert_equivalent(a,e,f'{path}[{i}]')
    else:raise TypeError(type(expected))


def assert_physical(summary):
    assert summary['converged'] and summary['iterations']>=2
    a=summary['cycle_water_audit']
    assert a['whole_cycle_closed']
    assert abs(a['external_mass_residual_kg_hr'])<1e-6
    assert abs(a['external_energy_residual_kW'])<.01
    assert summary['hrsg_local_balances_passed'] and summary['hrsg_endpoint_screen_passed']
    assert not summary['validation_scope']['field_validated']
    assert set(summary['boundary_calls'])==set(BOUNDARIES)
    assert all(n>=2 for n in summary['boundary_calls'].values())


def suite_cases():
    rows=[]
    def add(task,variant,expected='accept',error=None,ambient=15):
        rows.append(dict(id=f'{task}_{variant}_{ambient}',task=task,variant=variant,
                         ambient=ambient,expected=expected,error_contains=error))
    add('S1','compatible')
    add('S1','incompatible','reject','incompatible type')
    add('S1','ambiguous','reject','expected one value')
    add('S1','missing_ancestry','reject','incompatible type')
    add('S2','compatible')
    add('S2','missing_output','reject','missing required output')
    for ambient in [5,15,25]:
        add('S3','compatible',ambient=ambient)
        add('S4','compatible',ambient=ambient)
    for variant,error in [('missing_unit','missing or conflicting fields'),('wrong_dimension','inconsistent unit'),('conflicting_fields','missing or conflicting fields')]:
        add('S3',variant,'reject',error)
    for variant,error in [('wrong_source','source mismatch'),('swapped_reheat','boundary mismatch'),('missing_field','missing or conflicting fields'),('stale_version','version mismatch')]:
        add('S4',variant,'reject',error)
    add('S5','transition')
    add('S5','delayed_old','reject','previous revision')
    add('S5','mixed_consumer','reject','mixed consumer revisions')
    add('S5','failed_new','reject','missing required output')
    add('S6','compatible')
    for consumer in EXPORT_CONSUMERS:add('S6','stale_'+consumer,'reject',consumer+' version mismatch')
    return rows


def scenario_facts(case):
    f=base_facts();task=case['task'];v=case['variant']
    if task=='S1':
        f=set_fact(f,'EXP-001','type','AdvancedExpander')
        f += [('AdvancedExpander','subclass','IntermediateExpander'),('IntermediateExpander','subclass','GT_Turbine')]
        if v=='incompatible':f=set_fact(f,'IntermediateExpander','subclass','HP_ST')
        if v=='missing_ancestry':f=[x for x in f if x!=('IntermediateExpander','subclass','GT_Turbine')]
        if v=='ambiguous':f.append(('EXP-001','binding','HP_ST'))
    if task=='S2':f=set_fact(f,'HPTURB','version','2')
    if task=='S3':
        for field,unit in [('T','K'),('m_dot','kg/s'),('P','Pa')]:f=set_fact(f,'gt_exhaust','unit_'+field,unit)
        f=set_fact(f,'gt_exhaust','version','2')
        f=set_fact(f,'gt_exhaust','field_m_dot','mass_flow')
    if task=='S4':
        for name in BOUNDARIES:
            if name=='gt_exhaust':continue
            for field,unit in [('h','kJ/kg'),('P','kPa')]:f=set_fact(f,name,'unit_'+field,unit)
            f=set_fact(f,name,'version','2');f=set_fact(f,name,'field_h','specific_enthalpy')
    if task=='S5':f.extend([('scenario','revision','B'),('scenario','ambient','25')])
    if task=='S6':
        f=set_fact(f,'HPSH-output','field',HPSH_NEW);f=set_fact(f,'HPSH-output','version','2')
        for consumer in EXPORT_CONSUMERS:
            f=set_fact(f,'HPSH-'+consumer,'version','1' if v=='stale_'+consumer else '2')
    return sorted(f)


def mutation(case):
    task,v=case['task'],case['variant']
    if task not in {'S3','S4'} or v=='compatible':return None
    def mutate(name,payload):
        if task=='S3' and name=='gt_exhaust':
            if v=='missing_unit':payload['units'].pop('T')
            elif v=='wrong_dimension':payload['units']['T']='kg/s'
            elif v=='conflicting_fields':payload['values']['m_dot']=1.;payload['units']['m_dot']='kg/hr'
        if task=='S4' and name=='hot_reheat':
            if v=='wrong_source':payload['source']='Condenser'
            elif v=='swapped_reheat':payload['boundary']='cold_reheat'
            elif v=='missing_field':payload['values'].pop('specific_enthalpy')
            elif v=='stale_version':payload['version']='1'
        return payload
    return mutate


def evidence(output,result,backend,versions=None,aliases=None):
    params=make_default_params()
    if aliases:params['output_aliases']=aliases
    m=run_mechanics(result,params,backend,versions)
    return {'physical':summarize(output,result),'mechanical':m}


def without_migration_metadata(m):
    m=copy.deepcopy(m);m.pop('model_versions',None)
    for row in m['routing']:
        if row['model']=='VersionedModelAdapter':row['model']='__adapter__'
    return m


def validate_mechanical_parity(actual,baseline,task):
    a=copy.deepcopy(actual);b=copy.deepcopy(baseline)
    a.pop('model_versions',None);b.pop('model_versions',None)
    if task=='S2':
        for rows in (a['routing'],b['routing']):
            next(r for r in rows if r['device_id']=='HPTURB')['model']='same-kernel-adapter'
    if task=='S6':
        row=next(r for r in a['mechanics'] if r['device_id']=='HPSH-001')
        row['outputs'][HPSH_OLD]=row['outputs'].pop(HPSH_NEW)
    assert_equivalent(a,b)


def migrate_export(m,store):
    """Publication/query envelope: internal mechanical warning schema is unchanged."""
    version=store.one('HPSH-output','version');field=store.one('HPSH-output','field')
    if version!='2' or field!=HPSH_NEW or store.one('HPSH-output','unit')!='MPa':
        raise ContractError('export schema identity mismatch')
    for consumer in EXPORT_CONSUMERS:
        if store.one('HPSH-'+consumer,'version')!=version:
            raise ContractError(consumer+' version mismatch')
    row=next(r for r in m['mechanics'] if r['device_id']=='HPSH-001')
    if field not in row['outputs'] or HPSH_OLD in row['outputs']:
        raise ContractError('export output contract field mismatch')
    exported={'device':'HPSH-001','field':field,'unit':store.one('HPSH-output','unit'),
              'value':row['outputs'][field],'version':version,'warnings':row['warnings']}
    # Serialize through each native representation and retrieve complete envelope.
    native=type(store)([('published',k,str(v)) for k,v in exported.items() if k!='warnings'])
    retrieved={k:native.one('published',k) for k in exported if k!='warnings'}
    assert retrieved=={k:str(v) for k,v in exported.items() if k!='warnings'}
    return {'record':exported,'retrieved':retrieved,'consumers':list(EXPORT_CONSUMERS)}


def execute_case(case,store,backend,oracle):
    """Unexpected exceptions are harness failures, never counted as rejections."""
    task=case['task'];variant=case['variant'];stage='configuration';record=None
    try:
        if task=='S1':validate_model(store,'EXP-001','GT_Turbine')
        if task=='S2':validate_model(store,'HPTURB','HP_ST')
        if task=='S5':return execute_lifecycle(case,store,backend,oracle)
        adapter=BoundaryAdapter(store,mutation(case))
        stage='physical_boundary';output,result=run_physics(case['ambient'],adapter)
        stage='mechanical_execution'
        versions={'HPTURB':'HPST-v'+store.one('HPTURB','version')} if task=='S2' else None
        aliases={HPSH_OLD:store.one('HPSH-output','field')} if task=='S6' else None
        ev=evidence(output,result,backend,versions,aliases)
        stage='output_contract'
        if task=='S2':
            if variant=='missing_output':
                next(r for r in ev['mechanical']['mechanics'] if r['device_id']=='HPTURB')['outputs'].pop('mech_hpst_remaining_life_hr')
            validate_hp_output(ev['mechanical'])
            assert ev['mechanical']['model_versions']==versions
            assert next(r for r in ev['mechanical']['routing'] if r['device_id']=='HPTURB')['model']=='VersionedModelAdapter'
        if task=='S6':ev['export']=migrate_export(ev['mechanical'],store)
        stage='independent_oracle'
        assert_physical(ev['physical'])
        assert_equivalent(ev['physical'],oracle[case['ambient']]['physical'])
        validate_mechanical_parity(ev['mechanical'],oracle[case['ambient']]['mechanical'],task)
        record=ev
        return {'outcome':'accept','stage':'published','evidence':record,'boundary_calls':adapter.calls,
                'first_payloads':adapter.first_payloads,'current_result_published':True}
    except ContractError as exc:
        return {'outcome':'reject','stage':stage,'reason':str(exc),'current_result_published':False}


def execute_lifecycle(case,store,backend,oracle):
    tx=RevisionStore(type(store));variant=case['variant'];stage='initial_A'
    new_revision=store.one('scenario','revision');new_ambient=float(store.one('scenario','ambient'))
    if new_revision!='B' or new_ambient!=25.:
        raise ContractError('scenario differs from frozen B input contract')
    def compute(ambient,rev):
        a=BoundaryAdapter(type(store)(base_facts()));o,r=run_physics(ambient,a)
        ev=evidence(o,r,backend)
        ev['consumer_revisions']={name:rev for name in CONSUMERS}
        return ev
    tx.begin('A');a=compute(15,'A');tx.commit('A',a)
    tx.begin(new_revision);b=compute(new_ambient,new_revision);stage='B_consumer_contract'
    try:
        if variant=='failed_new':
            next(r for r in b['mechanical']['mechanics'] if r['device_id']=='HPTURB')['outputs'].pop('mech_hpst_remaining_life_hr')
            validate_hp_output(b['mechanical'])
        if variant=='mixed_consumer':b['consumer_revisions']['diagnosis']='A'
        tx.commit('B',b)
        assert_equivalent(tx.read()['physical'],oracle[25]['physical'])
        assert_equivalent(tx.read()['mechanical'],oracle[25]['mechanical'])
        assert abs(b['physical']['W_net_kW']-a['physical']['W_net_kW'])>1.
        if variant=='delayed_old':stage='delayed_A_commit';tx.commit('A',a)
        return {'outcome':'accept','stage':'published','evidence':tx.read(),'history_revisions':sorted(tx.history),
                'current_result_published':True,'A_net_kW':a['physical']['W_net_kW']}
    except ContractError as exc:
        if variant=='delayed_old':
            assert tx.read()==b;current=True
        else:
            tx.fail('B');current=False
            try:tx.read()
            except ContractError:pass
            else:raise AssertionError('failed B visible')
        assert 'A' in tx.history and tx.history['A']==a
        return {'outcome':'reject','stage':stage,'reason':str(exc),'current_result_published':current,
                'current_revision':'B','history_revisions':sorted(tx.history),
                'preserved_B_after_delayed_A':variant=='delayed_old'}
