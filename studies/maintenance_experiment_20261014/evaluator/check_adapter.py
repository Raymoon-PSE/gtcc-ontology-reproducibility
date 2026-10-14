"""Requirement-based held-out checks authored without reading candidate code."""
import copy,math

def facts():
    rows=[('stream','version','2')]
    for field,name,unit in [('T','temperature','K'),('P','pressure','kPa'),('m_dot','flow','kg/s'),('h','enthalpy','kJ/kg')]:
        rows += [('stream','field_'+field,name),('stream','unit_'+field,unit)]
    return rows

def record():
    return {'version':'2','values':{'temperature':273.15,'pressure':1000.,'flow':1.,'enthalpy':1.},
            'units':{'temperature':'K','pressure':'kPa','flow':'kg/s','enthalpy':'kJ/kg'},'composition':{'H2O':1.}}

def canonical():return {'T':0.,'P':1.,'m_dot':3600.,'h':1000.,'w':{'H2O':1.}}

def equivalent(a,b):
    assert set(a)==set(b),(a,b)
    for k in b:
        if isinstance(b[k],dict):equivalent(a[k],b[k])
        else:assert math.isfinite(a[k]) and math.isclose(a[k],b[k],rel_tol=1e-12,abs_tol=1e-9),(k,a[k],b[k])

def checks(module,cls):
    results=[]
    def run(name,fn):
        try:fn();results.append({'id':name,'passed':True,'error':None})
        except Exception as e:results.append({'id':name,'passed':False,'error':type(e).__name__+': '+str(e)})
    def valid(rec=None,ff=None,expected=None):
        rec=record() if rec is None else rec;ff=facts() if ff is None else ff
        before=copy.deepcopy(rec);out=module.adapt(rec,cls(ff).dumps())
        equivalent(out,canonical() if expected is None else expected);assert rec==before
        out['w']['H2O']=.2;assert rec==before
    def invalid(rec=None,ff=None,payload=None):
        rec=record() if rec is None else rec;ff=facts() if ff is None else ff
        text=cls(ff).dumps() if payload is None else payload
        try:module.adapt(rec,text)
        except ValueError:return
        raise AssertionError('Invalid configuration or record accepted')
    run('A01_known_conversion',valid)
    def aliases():
        ff=facts();r=record()
        for field,old,new in [('T','temperature','unseenT'),('P','pressure','unseenP'),('m_dot','flow','unseenM'),('h','enthalpy','unseenH')]:
            ff=[(s,p,new if p=='field_'+field else o) for s,p,o in ff]
            for key in ['values','units']:r[key][new]=r[key].pop(old)
        valid(r,ff)
    run('A02_arbitrary_aliases',aliases)
    def canonical_units():
        ff=[('stream','version','2')];r={'version':'2','values':{},'units':{},'composition':{'N2':.7,'O2':.3}}
        for field,unit,value in [('T','degC',37.5),('P','MPa',2.3),('m_dot','kg/hr',0.),('h','J/kg',-50.)]:
            ff.extend([('stream','field_'+field,field),('stream','unit_'+field,unit)])
            r['values'][field]=value;r['units'][field]=unit
        valid(r,ff,{'T':37.5,'P':2.3,'m_dot':0.,'h':-50.,'w':{'N2':.7,'O2':.3}})
    run('A03_canonical_zero_flow_negative_h',canonical_units)
    mutations=[('A04_wrong_version',lambda r:r.update(version='1')),
      ('A05_numeric_version',lambda r:r.update(version=2)),
      ('A06_extra_top_key',lambda r:r.update(unexpected=1)),
      ('A07_missing_value',lambda r:r['values'].pop('flow')),
      ('A08_extra_value',lambda r:r['values'].update(extra=3)),
      ('A09_missing_unit',lambda r:r['units'].pop('flow')),
      ('A10_wrong_dimension',lambda r:r['units'].update(temperature='Pa')),
      ('A11_boolean_numeric',lambda r:r['values'].update(flow=True)),
      ('A12_nan',lambda r:r['values'].update(temperature=float('nan'))),
      ('A13_inf',lambda r:r['values'].update(enthalpy=float('inf'))),
      ('A14_conversion_overflow',lambda r:r['values'].update(flow=1e308)),
      ('A15_zero_pressure',lambda r:r['values'].update(pressure=0)),
      ('A16_negative_flow',lambda r:r['values'].update(flow=-1)),
      ('A17_absolute_zero',lambda r:r['values'].update(temperature=0)),
      ('A18_empty_composition',lambda r:r.update(composition={})),
      ('A19_bad_composition_sum',lambda r:r.update(composition={'H2O':.9})),
      ('A20_negative_fraction',lambda r:r.update(composition={'A':-1.,'B':2.})),
      ('A21_nan_fraction',lambda r:r.update(composition={'A':float('nan')})),
      ('A22_extra_unit',lambda r:r['units'].update(extra='K'))]
    for name,change in mutations:
        def action(change=change):r=record();change(r);invalid(r)
        run(name,action)
    run('A23_ambiguous_version',lambda:invalid(ff=facts()+[('stream','version','3')]))
    run('A24_ambiguous_unit',lambda:invalid(ff=facts()+[('stream','unit_T','degC')]))
    run('A25_wrong_schema_dimension',lambda:invalid(ff=[(s,p,'kg/s' if p=='unit_T' else o) for s,p,o in facts()]))
    run('A26_missing_schema_field',lambda:invalid(ff=[f for f in facts() if f[1]!='field_h']))
    run('A27_colliding_aliases',lambda:invalid(ff=[(s,p,'temperature' if p=='field_P' else o) for s,p,o in facts()]))
    run('A28_broken_native_serialization',lambda:invalid(payload='not a native configuration {'))
    def changing_config():
        valid();canonical_units();valid()
    run('A29_no_stale_configuration',changing_config)
    return results
