"""Shared validators/converters. These are new experiment adapters, not existing ontology capabilities."""
from __future__ import annotations
import copy
import math
from dataclasses import replace
from .stores import ContractError

BOUNDARIES = {
 'gt_exhaust': ('GT','HRSG'),
 'hp_steam': ('HRSG','ST'),
 'hot_reheat': ('HRSG','ST'),
 'lp_steam': ('HRSG','ST'),
 'st_exhaust': ('ST','Condenser'),
 'cold_reheat': ('ST','HRSG'),
 'condensate': ('Condenser','HRSG'),
}
# canonical = external * multiplier + offset
UNITS = {'T': {'degC':(1.,0.),'K':(1.,-273.15)},
         'P': {'MPa':(1.,0.),'kPa':(.001,0.),'Pa':(1e-6,0.)},
         'm_dot': {'kg/hr':(1.,0.),'kg/s':(3600.,0.)},
         'h': {'J/kg':(1.,0.),'kJ/kg':(1000.,0.)}}
CANONICAL = {'T':'degC','P':'MPa','m_dot':'kg/hr','h':'J/kg'}

def base_facts():
    facts=[]
    for name,(source,target) in BOUNDARIES.items():
        facts.extend([(name,'source',source),(name,'target',target),(name,'version','1')])
        for field,unit in CANONICAL.items():
            facts.extend([(name,'unit_'+field,unit),(name,'field_'+field,field)])
    facts += [('EXP-001','type','GT_Turbine'),('GT_Turbine','subclass','MechanicalModel'),
              ('HP_ST','subclass','MechanicalModel'),('EXP-001','binding','GT_Turbine'),
              ('HPTURB','type','HP_ST'),('HPTURB','binding','HP_ST'),('HPTURB','version','1'),
              ('HPSH-output','field','mech_hpsh_hoop_stress_MPa'),('HPSH-output','version','1'),
              ('HPSH-output','unit','MPa'),('HPSH-query','version','1')]
    return sorted(facts)

def set_fact(facts,subject,predicate,value):
    return sorted([f for f in facts if f[:2]!=(subject,predicate)]+[(subject,predicate,str(value))])

def validate_manifest(store):
    for name,(source,target) in BOUNDARIES.items():
        if store.one(name,'source')!=source or store.one(name,'target')!=target:
            raise ContractError(f'{name}: source/target mismatch')
        if store.one(name,'version') not in {'1','2'}:
            raise ContractError(f'{name}: unsupported version')
        for field in CANONICAL:
            if store.one(name,'unit_'+field) not in UNITS[field]:
                raise ContractError(f'{name}.{field}: wrong unit dimension')
            store.one(name,'field_'+field)
        if len({store.one(name,'field_'+field) for field in CANONICAL}) != len(CANONICAL):
            raise ContractError(f'{name}: duplicate external field aliases')


def encode_stream(stream,name,store):
    payload={'boundary':name,'source':store.one(name,'source'), 'target':store.one(name,'target'),
             'version':store.one(name,'version'),'values':{},'units':{}}
    for field in CANONICAL:
        external_name=store.one(name,'field_'+field)
        if len({store.one(name,'field_'+field) for field in CANONICAL}) != len(CANONICAL):
            raise ContractError(f'{name}: duplicate external field aliases')
        unit=store.one(name,'unit_'+field)
        mul,offset=UNITS[field][unit]
        value=getattr(stream,field)
        payload['values'][external_name]=None if value is None else (value-offset)/mul
        payload['units'][external_name]=unit
    return payload


def decode_stream(payload,name,template,store):
    source,target=BOUNDARIES[name]
    for key,expected in [('boundary',name),('source',source),('target',target),('version',store.one(name,'version'))]:
        if payload.get(key)!=expected:
            raise ContractError(f'{name}: {key} mismatch')
    expected_fields={store.one(name,'field_'+f) for f in CANONICAL}
    if set(payload.get('values',{}))!=expected_fields or set(payload.get('units',{}))!=expected_fields:
        raise ContractError(f'{name}: missing or conflicting fields')
    updates={}
    for field in CANONICAL:
        key=store.one(name,'field_'+field)
        if len({store.one(name,'field_'+field) for field in CANONICAL}) != len(CANONICAL):
            raise ContractError(f'{name}: duplicate external field aliases')
        unit=store.one(name,'unit_'+field)
        if key not in payload.get('values',{}) or payload.get('units',{}).get(key)!=unit:
            raise ContractError(f'{name}.{field}: missing field or inconsistent unit')
        value=payload['values'][key]
        if value is None and field=='h':
            updates[field]=None
            continue
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):
            raise ContractError(f'{name}.{field}: invalid numeric value')
        mul,offset=UNITS[field][unit]
        updates[field]=value*mul+offset
        if not math.isfinite(updates[field]):
            raise ContractError(f'{name}.{field}: conversion overflow')
    if updates['P']<=0 or updates['m_dot']<0 or updates['T']<=-273.15:
        raise ContractError(f'{name}: nonphysical canonical boundary')
    return replace(template,**updates)

class BoundaryAdapter:
    def __init__(self,store,mutator=None):
        validate_manifest(store)
        self.store,self.mutator=store,mutator
        self.calls={k:0 for k in BOUNDARIES}
        self.first_payloads={}
    def __call__(self,name,stream):
        self.calls[name]+=1
        payload=encode_stream(stream,name,self.store)
        if self.mutator:
            payload=self.mutator(name,copy.deepcopy(payload))
        self.first_payloads.setdefault(name,copy.deepcopy(payload))
        return decode_stream(payload,name,stream,self.store)


def validate_model(store,device,required_type):
    if not store.instance_of(device,required_type):
        raise ContractError(f'{device}: incompatible type, requires {required_type}')
    binding=store.one(device,'binding')
    if binding!=required_type:
        raise ContractError(f'{device}: binding incompatible with required kernel')
    return binding


def validate_hp_output(mechanics):
    outputs=next(row['outputs'] for row in mechanics['mechanics'] if row['device_id']=='HPTURB')
    required={'mech_hpst_erosion_rate_mm_khr','mech_hpst_erosion_depth_mm','mech_hpst_steam_velocity_m_s','mech_hpst_moisture_loss_pct','mech_hpst_remaining_life_hr'}
    missing=required-set(outputs)
    if missing:
        raise ContractError('HPTURB: missing required output '+','.join(sorted(missing)))

class RevisionStore:
    """Same revision transaction algorithm for each representation, whole-result commit."""
    def __init__(self,store_class,consumers=('process','operating_point','mechanics','rules','diagnosis','query')):
        self.required_consumers=set(consumers)
        self.cls=store_class; self.current=None; self.history={}; self.record=None
    def begin(self,revision):
        self.current=str(revision); self.record=None
        self.meta=self.cls([('run','revision',self.current),('run','state','pending')])
    def commit(self,revision,record):
        revision=str(revision)
        if revision!=self.meta.one('run','revision'):
            raise ContractError('delayed result belongs to a previous revision')
        # Verify every declared consumer carries this revision, not just envelope.
        if set(record.get('consumer_revisions',{}))!=self.required_consumers:
            raise ContractError('missing or unexpected consumer revisions')
        if any(str(v)!=revision for v in record['consumer_revisions'].values()):
            raise ContractError('mixed consumer revisions')
        self.record=copy.deepcopy(record); self.history[revision]=copy.deepcopy(record)
        self.meta=self.cls([('run','revision',revision),('run','state','accepted')])
    def fail(self,revision):
        if str(revision)!=self.current: raise ContractError('failure for obsolete revision')
        self.record=None
        self.meta=self.cls([('run','revision',self.current),('run','state','failed')])
    def read(self):
        if self.meta.one('run','state')!='accepted':
            raise ContractError('no accepted result for current revision')
        return copy.deepcopy(self.record)
